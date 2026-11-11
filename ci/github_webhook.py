"""Plan/install only this repository's GitHub push webhook using the active gh identity.

The HTTPS endpoint and matching Jenkins shared secret must already be configured.
No token or webhook secret is written to receipts or command output.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
from urllib.parse import urlsplit

REPOSITORY = '03loveslollipop/cdp_2026'


def gh(path, *, payload=None, method=None):
    command = ['gh', 'api', path]
    if method:
        command += ['--method', method]
    if payload is not None:
        command += ['--input', '-']
    result = subprocess.run(command, input=None if payload is None else json.dumps(payload),
                            capture_output=True, text=True)
    if result.returncode:
        # Do not echo payloads, tokens, or a remote response that might contain a secret.
        raise RuntimeError(f'GitHub API request failed: {method or "GET"} {path}. '
                           'Check the active gh account and repository-webhook permissions.')
    return json.loads(result.stdout) if result.stdout.strip() else None


def endpoint(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path != '/github-webhook/'
            or parsed.port not in {None, 443}):
        raise ValueError('Use a public HTTPS URL ending exactly in /github-webhook/ (no credentials/query).')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('GitHub cannot deliver to a loopback, private or reserved address.')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, type=endpoint)
    parser.add_argument('--secret-file', type=Path)
    parser.add_argument('--apply', action='store_true', help='Create/update after reviewing the default plan')
    parser.add_argument('--receipt', type=Path, default=Path('.jenkins/github-webhook-receipt.json'))
    args = parser.parse_args()
    user = gh('user')['login']
    repository = gh('repos/' + REPOSITORY)
    if not repository.get('permissions', {}).get('admin'):
        raise SystemExit(f'{user} lacks repository-admin access to {REPOSITORY}. '
                         'For this personal repository, authenticate its owner with gh auth login '
                         '--hostname github.com --web --git-protocol ssh --scopes admin:repo_hook.')
    hooks = gh(f'repos/{REPOSITORY}/hooks')
    matches = [hook for hook in hooks if hook.get('config', {}).get('url') == args.url]
    if len(matches) > 1:
        raise SystemExit('Multiple hooks match this endpoint; resolve the duplicate hooks first.')
    plan = {'repository': REPOSITORY, 'account': user, 'endpoint': args.url,
            'events': ['push'], 'active': True, 'operation': 'update' if matches else 'create',
            'applied': False}
    if not args.apply:
        print(json.dumps(plan, indent=2))
        return
    if not args.secret_file or args.secret_file.stat().st_mode & 0o077:
        raise SystemExit('Provide an owner-only --secret-file (chmod 600) matching Jenkins shared secret.')
    secret = args.secret_file.read_text().strip()
    if len(secret) < 32:
        raise SystemExit('Use a random webhook secret with at least 32 characters.')
    payload = {'name': 'web', 'active': True, 'events': ['push'],
               'config': {'url': args.url, 'content_type': 'json', 'insecure_ssl': '0', 'secret': secret}}
    path = f'repos/{REPOSITORY}/hooks' + (f'/{matches[0]["id"]}' if matches else '')
    hook = gh(path, payload=payload, method='PATCH' if matches else 'POST')
    # Read back to distinguish a successful write from a merely prepared plan.
    readback = gh(f'repos/{REPOSITORY}/hooks/{hook["id"]}')
    if (readback['config']['url'] != args.url or readback.get('events') != ['push']
            or not readback.get('active') or str(readback['config'].get('insecure_ssl')) != '0'):
        raise RuntimeError('Webhook read-back does not match the reviewed configuration.')
    plan.update(applied=True, hook_id=hook['id'],
                delivery_verified=False, note='Verify Recent Deliveries, matching SCM commit and Jenkins build.')
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
