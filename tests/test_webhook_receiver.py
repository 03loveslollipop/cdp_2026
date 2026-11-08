"""Signature, scope, expiry, redelivery and failed-upstream boundaries."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import uuid

import pytest

from cloud.webhook.receiver import Relay, REPOSITORY, REPOSITORY_ID

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
SECRET = 'test-secret-' * 5


def fixture_payload(**changes):
    payload = {'repository': {'id': REPOSITORY_ID, 'full_name': REPOSITORY},
               'ref': 'refs/heads/ci/jenkins-lab-20261108', 'after': 'a' * 40, 'deleted': False}
    payload.update(changes)
    body = json.dumps(payload).encode()
    headers = {'X-Hub-Signature-256': 'sha256=' + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest(),
               'X-GitHub-Delivery': str(uuid.uuid4()), 'X-GitHub-Event': 'push'}
    return headers, body


def relay():
    return Relay(SECRET, 'http://10.81.0.3:8080', '2026-11-13T02:41:05Z', ['ci/jenkins-lab-20261108'])


def test_valid_signature_and_duplicate_forward_once():
    r, calls = relay(), []
    headers, body = fixture_payload()
    def forward(h, b):
        calls.append(b)
        return 200
    assert r.handle(headers, body, forward=forward, now=NOW)[0] == 200
    assert r.handle(headers, body, forward=forward, now=NOW)[1] == {'duplicate': True}
    assert calls == [body]


def test_bad_signature_never_reaches_jenkins():
    headers, body = fixture_payload()
    headers['X-Hub-Signature-256'] = 'sha256=' + '0' * 64
    assert relay().handle(headers, body, forward=lambda *a: pytest.fail('unauthorized forward'), now=NOW)[0] == 403


@pytest.mark.parametrize('changes,status', [
    ({'repository': {'id': 1, 'full_name': 'other/repo'}}, 403),
    ({'ref': 'refs/heads/unrelated'}, 202), ({'ref': 'refs/tags/v1'}, 202),
    ({'deleted': True}, 202), ({'after': 'invalid'}, 400),
])
def test_ref_and_repository_allowlist(changes, status):
    headers, body = fixture_payload(**changes)
    assert relay().handle(headers, body, forward=lambda *a: pytest.fail('out-of-scope forward'), now=NOW)[0] == status


def test_failed_upstream_can_be_retried():
    r = relay()
    headers, body = fixture_payload()
    assert r.handle(headers, body, forward=lambda *a: 503, now=NOW)[0] == 502
    assert r.handle(headers, body, forward=lambda *a: 200, now=NOW)[0] == 200


def test_expired_policy_refuses_all_requests():
    headers, body = fixture_payload()
    assert relay().handle(headers, body, now=datetime(2026, 11, 14, tzinfo=timezone.utc))[0] == 410


def test_public_upstream_is_refused():
    with pytest.raises(ValueError):
        Relay(SECRET, 'http://example.com:8080', '2026-11-13T02:41:05Z', ['master'])
