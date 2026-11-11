"""Run this lab's Terraform with the explicitly verified gcloud user identity."""
import os
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

DIRECTORY = Path(__file__).resolve().parent
ACCOUNT = 'contact@02labs.me'
PROJECT = 'nb-core-dev-99d0'
ORGANIZATION = '408308144073'


def environment():
    ancestors = subprocess.check_output(
        ['gcloud', 'projects', 'get-ancestors', PROJECT, '--account', ACCOUNT,
         '--format=value(id)'], text=True).splitlines()
    if ORGANIZATION not in ancestors:
        raise RuntimeError('Jenkins project is outside the verified 02labs organization')
    token = subprocess.check_output(
        ['gcloud', 'auth', 'print-access-token', '--account', ACCOUNT], text=True).strip()
    return {**os.environ, 'GOOGLE_OAUTH_ACCESS_TOKEN': token, 'TF_VAR_project_id': PROJECT}


if __name__ == '__main__':
    policy_path = DIRECTORY.parent / 'expiry/policy.json'
    if policy_path.exists() and len(sys.argv) > 1 and sys.argv[1] in {'plan', 'apply'} and '-destroy' not in sys.argv:
        expiry = json.loads(policy_path.read_text())['expires_at']
        if datetime.now(timezone.utc) >= datetime.fromisoformat(expiry.replace('Z', '+00:00')):
            raise SystemExit('The Jenkins lab has expired. Refusing a plan/apply that could recreate it; destroy remains available.')
    sys.exit(subprocess.call(['terraform', *sys.argv[1:]], cwd=DIRECTORY, env=environment()))
