"""Exercise webhook permission boundaries and mutations without calling GitHub."""
import importlib.util
import json
from pathlib import Path
import socket
import sys

import pytest

spec = importlib.util.spec_from_file_location(
    'github_webhook', Path(__file__).parents[1] / 'ci/github_webhook.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


@pytest.mark.parametrize('url', [
    'http://ci.example.com/github-webhook/',
    'https://admin:password@ci.example.com/github-webhook/',
    'https://ci.example.com/github-webhook/?token=secret',
    'https://ci.example.com/other/',
])
def test_rejects_insecure_or_unintended_endpoints(url):
    with pytest.raises(ValueError):
        hook.endpoint(url)


def test_rejects_private_dns_result(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
    with pytest.raises(ValueError, match='private'):
        hook.endpoint('https://ci.example.com/github-webhook/')


def test_non_admin_cannot_read_or_mutate_hooks(monkeypatch):
    calls = []

    def fake(path, **kwargs):
        calls.append(path)
        return {'login': 'writer'} if path == 'user' else {'permissions': {'admin': False}}

    monkeypatch.setattr(hook, 'gh', fake)
    monkeypatch.setattr(hook, 'endpoint', lambda value: value)
    monkeypatch.setattr(sys, 'argv', ['hook', '--url', 'https://ci.example.com/github-webhook/', '--apply'])
    with pytest.raises(SystemExit, match='lacks repository-admin'):
        hook.main()
    assert calls == ['user', 'repos/' + hook.REPOSITORY]


def test_plan_has_no_remote_mutation(monkeypatch, capsys):
    calls = []

    def fake(path, **kwargs):
        calls.append((path, kwargs))
        if path == 'user':
            return {'login': 'owner'}
        return [] if path.endswith('/hooks') else {'permissions': {'admin': True}}

    monkeypatch.setattr(hook, 'gh', fake)
    monkeypatch.setattr(hook, 'endpoint', lambda value: value)
    monkeypatch.setattr(sys, 'argv', ['hook', '--url', 'https://ci.example.com/github-webhook/'])
    hook.main()
    assert not json.loads(capsys.readouterr().out)['applied']
    assert all(not kwargs for _, kwargs in calls)


def test_apply_preserves_other_hooks_and_redacts_secret(monkeypatch, tmp_path, capsys):
    secret = tmp_path / 'secret'
    secret.write_text('private-webhook-secret-' * 3)
    secret.chmod(0o600)
    receipt = tmp_path / 'receipt.json'
    calls = []
    url = 'https://ci.example.com/github-webhook/'
    matched = {'id': 7, 'config': {'url': url, 'insecure_ssl': '0'}, 'active': True, 'events': ['push']}

    def fake(path, **kwargs):
        calls.append((path, kwargs))
        if path == 'user':
            return {'login': 'owner'}
        if path.endswith('/hooks'):
            return [{'id': 3, 'config': {'url': 'https://other.example.com/'}}, matched]
        if path.endswith('/hooks/7'):
            return matched
        return {'permissions': {'admin': True}}

    monkeypatch.setattr(hook, 'gh', fake)
    monkeypatch.setattr(hook, 'endpoint', lambda value: value)
    monkeypatch.setattr(sys, 'argv', ['hook', '--url', url, '--apply', '--secret-file', str(secret),
                                     '--receipt', str(receipt)])
    hook.main()
    writes = [(path, kwargs) for path, kwargs in calls if kwargs.get('method')]
    assert len(writes) == 1 and writes[0][0].endswith('/hooks/7')
    assert writes[0][1]['method'] == 'PATCH'
    assert writes[0][1]['payload']['config']['secret'] == secret.read_text()
    output = capsys.readouterr().out + receipt.read_text()
    assert secret.read_text() not in output
    assert json.loads(receipt.read_text())['delivery_verified'] is False


def plugin_fetcher():
    spec = importlib.util.spec_from_file_location(
        'plugin_fetcher', Path(__file__).parents[1] / 'ci/jenkins/fetch_plugins.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plugin_refresh_keeps_compatible_controller_pin(monkeypatch, tmp_path):
    fetcher = plugin_fetcher()
    runtime = tmp_path / '.jenkins'
    runtime.mkdir()
    (tmp_path / 'plugins.txt').write_text('junit\n')
    previous = {'junit': {'required_core': '2.555.3', 'version': 'compatible', 'sha256': 'known'}}
    lock = tmp_path / 'plugins.lock.json'
    lock.write_text(json.dumps(previous))
    (runtime / 'update-center.json').write_text(json.dumps({'plugins': {'junit': {
        'requiredCore': '2.589', 'gav': 'org.example:junit:incompatible',
        'sha256': 'new', 'dependencies': [],
    }}}))
    monkeypatch.setattr(fetcher, 'ROOT', tmp_path)
    monkeypatch.setattr(fetcher, 'DIRECTORY', tmp_path)
    monkeypatch.setattr(fetcher, 'LOCK', lock)
    fetcher.refresh()
    assert json.loads(lock.read_text()) == previous


def test_plugin_fetch_refuses_incompatible_lock_before_download(monkeypatch, tmp_path):
    fetcher = plugin_fetcher()
    lock = tmp_path / 'plugins.lock.json'
    lock.write_text(json.dumps({'junit': {'required_core': '2.589'}}))
    monkeypatch.setattr(fetcher, 'LOCK', lock)
    with pytest.raises(ValueError, match='newer controller'):
        fetcher.fetch()
