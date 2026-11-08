"""Provision the webhook with the same verified identity and fixed lab deadline."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

DIRECTORY = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('jenkins_auth', DIRECTORY.parent / 'jenkins/terraform.py')
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)
if __name__ == '__main__':
    policy = json.loads((DIRECTORY.parent / 'expiry/policy.json').read_text())
    if len(sys.argv) > 1 and sys.argv[1] in {'plan', 'apply'} and '-destroy' not in sys.argv:
        if datetime.now(timezone.utc) >= datetime.fromisoformat(policy['expires_at'].replace('Z', '+00:00')):
            raise SystemExit('This Jenkins lab has expired; only cleanup is permitted.')
    sys.exit(subprocess.call(['terraform', *sys.argv[1:]], cwd=DIRECTORY, env=auth.environment()))
