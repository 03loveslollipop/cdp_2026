"""Build/publish the small relay and create its secret outside Terraform state."""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROJECT, ACCOUNT = 'nb-core-dev-99d0', 'contact@02labs.me'
REGISTRY = 'us-central1-docker.pkg.dev'
TAG = f'{REGISTRY}/{PROJECT}/semester-jenkins/webhook:lab-20261108'


def main():
    policy = json.loads((ROOT / 'cloud/expiry/policy.json').read_text())
    if datetime.now(timezone.utc) >= datetime.fromisoformat(policy['expires_at'].replace('Z', '+00:00')):
        raise SystemExit('The fixed lab deadline has passed')
    secret = ROOT / '.jenkins/secrets/github-webhook'
    if not secret.exists():
        secret.write_text(secrets.token_urlsafe(48) + '\n')
        secret.chmod(0o600)
    versions = subprocess.check_output(['gcloud', 'secrets', 'versions', 'list', 'semester-jenkins-webhook',
        '--project', PROJECT, '--account', ACCOUNT, '--format=value(name)'], text=True).strip()
    if not versions:
        subprocess.run(['gcloud', 'secrets', 'versions', 'add', 'semester-jenkins-webhook',
                        '--project', PROJECT, '--account', ACCOUNT, '--data-file', str(secret)], check=True)
    subprocess.run(['docker', 'build', '-t', TAG, str(ROOT / 'cloud/webhook')], check=True)
    token = subprocess.check_output(['gcloud', 'auth', 'print-access-token', '--account', ACCOUNT], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='jenkins-webhook-docker-') as directory:
        cli = ['docker', '--config', directory]
        subprocess.run([*cli, 'login', '-u', 'oauth2accesstoken', '--password-stdin', 'https://' + REGISTRY],
                       input=token, text=True, stdout=subprocess.DEVNULL, check=True)
        subprocess.run([*cli, 'push', TAG], check=True)
    descriptor = json.loads(subprocess.check_output(['docker', 'image', 'inspect', TAG], text=True))[0]
    image = next(d for d in descriptor['RepoDigests'] if d.startswith(TAG.split(':')[0] + '@'))
    (ROOT / 'cloud/webhook/terraform.tfvars').write_text(f'deploy_receiver = true\nimage = {json.dumps(image)}\n')
    (ROOT / '.jenkins/webhook-image.json').write_text(json.dumps({'image': image}, indent=2) + '\n')
    print('Immutable receiver image:', image)


if __name__ == '__main__':
    main()
