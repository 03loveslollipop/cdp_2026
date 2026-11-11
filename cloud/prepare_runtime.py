"""Prepare a small training runtime; never submit a pipeline or training job.

All training starts in the Japanese GCP dashboard. Uses the verified risk project,
short-lived user authentication and repository/bucket-scoped runtime grants.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'nb-risk-ml-dev-99d0'
ACCOUNT = 'contact@02labs.me'
REGION = 'us-central1'
BUCKET = PROJECT + '-credit-lab-20261108'
REPOSITORY = 'credit-semester-training'
SERVICE_ACCOUNT = f'credit-semester-pipeline@{PROJECT}.iam.gserviceaccount.com'


def gcloud(*args, capture=False):
    command = ['gcloud', *args, '--project', PROJECT, '--account', ACCOUNT, '--quiet']
    if capture:
        return subprocess.check_output(command, text=True).strip()
    subprocess.run(command, check=True)


def ensure(describe, create):
    result = subprocess.run(['gcloud', *describe, '--project', PROJECT, '--account', ACCOUNT,
                             '--format=json'], capture_output=True, text=True)
    if result.returncode:
        if 'NOT_FOUND' not in result.stderr:
            raise RuntimeError('Resource lookup failed; refusing to infer that it is absent')
        gcloud(*create)


def main():
    ancestors = gcloud('projects', 'get-ancestors', PROJECT, '--format=value(id)', capture=True)
    if '408308144073' not in ancestors.splitlines():
        raise RuntimeError('Training project is outside the verified 02labs organization')
    token = gcloud('auth', 'print-access-token', capture=True)
    request = urllib.request.Request('https://storage.googleapis.com/storage/v1/b/' + BUCKET,
                                     headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=30) as response:
        bucket = json.load(response)
    if str(bucket.get('projectNumber')) != '727006212991':
        raise RuntimeError('Training bucket is outside the verified risk project')
    gcloud('services', 'enable', 'artifactregistry.googleapis.com', 'compute.googleapis.com', 'iam.googleapis.com')
    ensure(['artifacts', 'repositories', 'describe', REPOSITORY, '--location', REGION],
           ['artifacts', 'repositories', 'create', REPOSITORY, '--location', REGION,
            '--repository-format=docker', '--description=CPU training image for the semester dashboard exercise'])
    ensure(['iam', 'service-accounts', 'describe', SERVICE_ACCOUNT],
           ['iam', 'service-accounts', 'create', 'credit-semester-pipeline',
            '--display-name=Semester CPU training pipeline'])
    member = 'serviceAccount:' + SERVICE_ACCOUNT
    gcloud('projects', 'add-iam-policy-binding', PROJECT, '--member', member,
           '--role=roles/aiplatform.user', '--condition=None', '--format=none')
    for role in ['roles/storage.objectUser', 'roles/storage.legacyBucketReader']:
        gcloud('storage', 'buckets', 'add-iam-policy-binding', 'gs://' + BUCKET,
               '--member', member, '--role', role, '--format=none')
    gcloud('artifacts', 'repositories', 'add-iam-policy-binding', REPOSITORY, '--location', REGION,
           '--member', member, '--role=roles/artifactregistry.reader', '--format=none')
    # The serverless pipeline control plane pulls the image with its own agent.
    gcloud('artifacts', 'repositories', 'add-iam-policy-binding', REPOSITORY, '--location', REGION,
           '--member=serviceAccount:service-727006212991@gcp-sa-aiplatform-cc.iam.gserviceaccount.com',
           '--role=roles/artifactregistry.reader', '--format=none')
    gcloud('iam', 'service-accounts', 'add-iam-policy-binding', SERVICE_ACCOUNT,
           '--member=user:' + ACCOUNT, '--role=roles/iam.serviceAccountUser', '--format=none')
    tag = f'{REGION}-docker.pkg.dev/{PROJECT}/{REPOSITORY}/trainer:dashboard-20261108'
    subprocess.run(['docker', 'build', '-f', 'cloud/Dockerfile', '-t', tag, '.'], cwd=ROOT, check=True)
    token = gcloud('auth', 'print-access-token', capture=True)
    with tempfile.TemporaryDirectory(prefix='credit-risk-training-docker-') as directory:
        cli = ['docker', '--config', directory]
        subprocess.run([*cli, 'login', '-u', 'oauth2accesstoken', '--password-stdin',
                        f'https://{REGION}-docker.pkg.dev'], input=token, text=True,
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run([*cli, 'push', tag], check=True)
    descriptor = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag], text=True))[0]
    image = next(d for d in descriptor['RepoDigests'] if d.startswith(tag.split(':')[0] + '@'))
    package = ROOT / 'output/credit-pipeline-dashboard.json'
    subprocess.run([str(ROOT / '.jenkins/cloud-venv/bin/python'), '-m', 'cloud.compile_pipeline',
                    '--image', image, '--output', str(package)], cwd=ROOT, check=True)
    receipt = {'project': PROJECT, 'region': REGION, 'bucket': BUCKET,
               'service_account': SERVICE_ACCOUNT, 'image': image, 'package': str(package.relative_to(ROOT)),
               'training_cpu_limit': 2, 'training_memory_limit': '8G', 'training_deadline_seconds': 600,
               'automatic_retries': 0, 'training_submitted': False,
               'native_automl_budget_cap_usd': 15}
    (ROOT / 'output/training-runtime.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
