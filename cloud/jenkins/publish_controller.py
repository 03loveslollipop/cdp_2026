"""Publish the tested Jenkins image and snapshot using isolated registry credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ACCOUNT = 'contact@02labs.me'
PROJECT = 'nb-core-dev-99d0'
REGISTRY = 'us-central1-docker.pkg.dev'
IMAGE = f'{REGISTRY}/{PROJECT}/semester-jenkins/controller'


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def main():
    for secret, filename in [('semester-jenkins-admin', 'admin-password'),
                             ('semester-jenkins-notify', 'notify-token')]:
        versions = run('gcloud', 'secrets', 'versions', 'list', secret,
                       '--project', PROJECT, '--account', ACCOUNT,
                       '--filter=state=ENABLED', '--format=value(name)')
        if not versions:
            subprocess.run(['gcloud', 'secrets', 'versions', 'add', secret,
                            '--project', PROJECT, '--account', ACCOUNT,
                            '--data-file', str(ROOT / '.jenkins/secrets' / filename)], check=True)
    snapshot = json.loads((ROOT / '.jenkins/source-receipt.json').read_text())
    tag = f'{IMAGE}:{snapshot["snapshot_commit"][:12]}'
    with tempfile.TemporaryDirectory(prefix='credit-jenkins-publish-') as directory:
        directory = Path(directory)
        shutil.copytree(ROOT / '.jenkins/source.git', directory / 'source.git')
        (directory / 'Dockerfile').write_text(
            'FROM credit-semester-jenkins:local\n'
            'USER root\nCOPY --chown=jenkins:jenkins source.git /opt/source\nUSER jenkins\n')
        subprocess.run(['docker', 'build', '-t', tag, str(directory)], check=True)
        token = run('gcloud', 'auth', 'print-access-token', '--account', ACCOUNT)
        docker_config = directory / 'docker-config'
        docker_config.mkdir(mode=0o700)
        env = {**os.environ, 'DOCKER_CONFIG': str(docker_config)}
        try:
            subprocess.run(['docker', 'login', '-u', 'oauth2accesstoken',
                            '--password-stdin', f'https://{REGISTRY}'], input=token,
                           text=True, check=True, env=env)
            subprocess.run(['docker', 'push', tag], check=True, env=env)
        finally:
            subprocess.run(['docker', 'logout', f'https://{REGISTRY}'], env=env, check=False)
    digests = json.loads(run('docker', 'image', 'inspect', tag, '--format={{json .RepoDigests}}'))
    image = next(digest for digest in digests if digest.startswith(IMAGE + '@sha256:'))
    receipt = {'project': PROJECT, 'account': ACCOUNT, 'image': image, **snapshot}
    (ROOT / '.jenkins/cloud-image.json').write_text(json.dumps(receipt, indent=2) + '\n')
    # No secrets in Terraform variables or state.
    (ROOT / 'cloud/jenkins/terraform.tfvars').write_text(
        f'project_id = "{PROJECT}"\ndeploy_controller = true\nimage = "{image}"\n')
    print(json.dumps(receipt, indent=2))
    print('Next: python3 cloud/jenkins/terraform.py plan -out=controller.tfplan')


if __name__ == '__main__':
    main()
