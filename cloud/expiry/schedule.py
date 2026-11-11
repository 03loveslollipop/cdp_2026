"""Create a fixed five-day Cloud Tasks policy and exercise its read-only path."""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import quote

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[1]
ACCOUNT = 'contact@02labs.me'
PROJECT = 'nb-core-dev-99d0'


def stamp(value):
    return value.isoformat(timespec='seconds').replace('+00:00', 'Z')


def init_policy():
    path = DIRECTORY / 'policy.json'
    if path.exists():
        print(path.read_text())
        return
    created = datetime.now(timezone.utc).replace(microsecond=0)
    deadline = created + timedelta(days=5)
    descriptor = (ROOT / '.jenkins/expiry-runtime-image.txt').read_text()
    digest = re.search(r'^Digest:\s*(sha256:[0-9a-f]{64})', descriptor, re.MULTILINE)
    if not digest:
        raise ValueError('The official Cloud SDK runtime image digest has not been resolved')
    # Keep the permission test in sync with the actual custom role declaration.
    source = (DIRECTORY / 'main.tf').read_text()
    role = source.split('resource "google_project_iam_custom_role" "cleanup" {', 1)[1].split('\n}', 1)[0]
    permissions = re.findall(r'"([a-z][a-zA-Z0-9]+\.[a-zA-Z0-9.]+)"', role)
    policy = {
        'project': PROJECT, 'region': 'us-central1', 'zone': 'us-central1-a',
        'created_at': stamp(created), 'expires_at': stamp(deadline),
        'authorization_expires_at': stamp(deadline + timedelta(hours=48)),
        'queue': 'semester-jenkins-expiry-' + deadline.strftime('%Y%m%d'),
        'runtime_image': 'gcr.io/google.com/cloudsdktool/google-cloud-cli@' + digest.group(1),
        'runtime_python': '/usr/lib/google-cloud-sdk/platform/bundledpythonunix/bin/python3',
        'required_project_permissions': sorted(set(permissions)),
        'retry_attempts': 49, 'retry_interval_seconds': 1800,
        'scope': 'Only the named semester-jenkins lab resources; no project/billing/training deletion',
    }
    path.write_text(json.dumps(policy, indent=2) + '\n')
    print(path.read_text())


def build(policy, *, dry_run):
    worker = (DIRECTORY / 'worker.py').read_text()
    code = 'POLICY = ' + repr(policy) + '\n' + worker
    encoded = base64.b64encode(code.encode()).decode()
    # Cloud Build limits each individual argument to 10,000 characters.
    args = ['-c', "import base64,sys; exec(base64.b64decode(''.join(x for x in sys.argv[1:] if x != '--dry-run')))"]
    args.extend(encoded[index:index + 8000] for index in range(0, len(encoded), 8000))
    if dry_run:
        args.append('--dry-run')
    return {
        'serviceAccount': f'projects/{PROJECT}/serviceAccounts/semester-jenkins-expiry@{PROJECT}.iam.gserviceaccount.com',
        'steps': [{'name': policy['runtime_image'], 'entrypoint': policy.get('runtime_python', '/usr/lib/google-cloud-sdk/platform/bundledpythonunix/bin/python3'),
                   'args': args, 'id': 'read-only-expiry-check' if dry_run else 'delete-expired-jenkins-lab'}],
        'options': {'logging': 'CLOUD_LOGGING_ONLY'}, 'timeout': '1200s',
        'tags': ['semester-jenkins-expiry', 'dry-run' if dry_run else 'scheduled-cleanup'],
    }


def install(*, smoke=False):
    policy = json.loads((DIRECTORY / 'policy.json').read_text())
    deadline = datetime.fromisoformat(policy['expires_at'].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) >= deadline:
        raise RuntimeError('Policy has expired; refusing to schedule or extend it implicitly')
    token = subprocess.check_output(['gcloud', 'auth', 'print-access-token', '--account', ACCOUNT], text=True).strip()
    queue = f'projects/{PROJECT}/locations/{policy["region"]}/queues/{policy["queue"]}'
    base = 'https://cloudtasks.googleapis.com/v2/' + queue + '/tasks'
    http = {'httpMethod': 'POST', 'headers': {'Content-Type': 'application/json'},
            'oauthToken': {'serviceAccountEmail': f'semester-expiry-trigger@{PROJECT}.iam.gserviceaccount.com',
                           'scope': 'https://www.googleapis.com/auth/cloud-platform'}}
    tasks = []
    if smoke:
        body = build(policy, dry_run=True)
        smoke_name = 'verify-read-only-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        tasks.append((smoke_name, datetime.now(timezone.utc), {
            **http, 'url': f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/locations/us-central1/builds',
            'body': base64.b64encode(json.dumps(body).encode()).decode()}))
    else:
        tasks.append(('stop-vm-at-expiry', deadline, {
            **http, 'url': f'https://compute.googleapis.com/compute/v1/projects/{PROJECT}/zones/us-central1-a/instances/semester-jenkins/stop'}))
        body = build(policy, dry_run=False)
        (ROOT / '.jenkins/expiry-cloudbuild.json').write_text(json.dumps(body, indent=2) + '\n')
        for index in range(policy['retry_attempts']):
            when = deadline + timedelta(seconds=60 + policy['retry_interval_seconds'] * index)
            generation = 'cleanup-webhook' if policy.get('webhook_enabled') else 'cleanup'
            tasks.append((f'{generation}-{index:02d}', when, {
                **http, 'url': f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/locations/us-central1/builds',
                'body': base64.b64encode(json.dumps(body).encode()).decode()}))
    receipts = []
    for name, when, target in tasks:
        task = {'name': queue + '/tasks/' + name, 'scheduleTime': stamp(when),
                'httpRequest': target, 'dispatchDeadline': '180s'}
        request = Request(base, data=json.dumps({'task': task}).encode(),
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=60) as response:
                result = json.load(response)
        except HTTPError as error:
            if error.code != 409:
                raise RuntimeError(f'Create task failed: HTTP {error.code}: {error.read().decode()}') from error
            result = {'name': task['name'], 'scheduleTime': task['scheduleTime'], 'already_exists': True}
        receipts.append({k: result.get(k) for k in ['name', 'scheduleTime', 'createTime', 'already_exists']})
        print(name, stamp(when), flush=True)
    receipt = {'expires_at': policy['expires_at'],
               'worker_sha256': hashlib.sha256((DIRECTORY / 'worker.py').read_bytes()).hexdigest(),
               'build_payload_sha256': hashlib.sha256(json.dumps(build(policy, dry_run=smoke), sort_keys=True).encode()).hexdigest(),
               'tasks': receipts}
    output = ROOT / '.jenkins' / ('expiry-smoke-task.json' if smoke else 'expiry-task-receipt.json')
    output.write_text(json.dumps(receipt, indent=2) + '\n')


def verify(*, retire_legacy=False):
    """Read back every future payload before retiring the earlier generation."""
    policy = json.loads((DIRECTORY / 'policy.json').read_text())
    token = subprocess.check_output(['gcloud', 'auth', 'print-access-token', '--account', ACCOUNT], text=True).strip()
    queue = f'projects/{PROJECT}/locations/{policy["region"]}/queues/{policy["queue"]}'
    base = 'https://cloudtasks.googleapis.com/v2/' + queue + '/tasks'
    headers = {'Authorization': 'Bearer ' + token}
    tasks, page_token = {}, ''
    while True:
        url = base + '?responseView=FULL&pageSize=1000'
        if page_token:
            url += '&pageToken=' + quote(page_token, safe='')
        with urlopen(Request(url, headers=headers), timeout=60) as response:
            result = json.load(response)
        tasks.update({task['name'].rsplit('/', 1)[-1]: task for task in result.get('tasks', [])})
        page_token = result.get('nextPageToken')
        if not page_token:
            break
    deadline = datetime.fromisoformat(policy['expires_at'].replace('Z', '+00:00'))
    stop = tasks['stop-vm-at-expiry']
    assert stop['scheduleTime'] == stamp(deadline)
    assert stop['httpRequest']['url'].endswith('/instances/semester-jenkins/stop')
    assert not stop['httpRequest'].get('body')
    expected_build = build(policy, dry_run=False)
    prefix = 'cleanup-webhook' if policy.get('webhook_enabled') else 'cleanup'
    verified = []
    for index in range(policy['retry_attempts']):
        name = f'{prefix}-{index:02d}'
        task = tasks[name]
        target = task['httpRequest']
        expected_time = deadline + timedelta(seconds=60 + policy['retry_interval_seconds'] * index)
        assert task['scheduleTime'] == stamp(expected_time), name
        assert target['httpMethod'] == 'POST', name
        assert target['url'] == f'https://cloudbuild.googleapis.com/v1/projects/{PROJECT}/locations/us-central1/builds', name
        assert target['oauthToken']['serviceAccountEmail'] == f'semester-expiry-trigger@{PROJECT}.iam.gserviceaccount.com', name
        assert json.loads(base64.b64decode(target['body'])) == expected_build, name
        verified.append(name)
    retired = []
    if retire_legacy:
        if not policy.get('webhook_enabled'):
            raise RuntimeError('Legacy retirement is only valid after webhook migration')
        for name in sorted(tasks):
            if re.fullmatch(r'cleanup-[0-9]{2}', name):
                with urlopen(Request(base + '/' + name, headers=headers, method='DELETE'), timeout=60):
                    pass
                retired.append(name)
    receipt = {'verified_at_utc': stamp(datetime.now(timezone.utc)),
               'expires_at': policy['expires_at'], 'stop_unchanged': True,
               'verified_cleanup_tasks': verified, 'retired_legacy_tasks': retired,
               'worker_sha256': hashlib.sha256((DIRECTORY / 'worker.py').read_bytes()).hexdigest(),
               'build_payload_sha256': hashlib.sha256(json.dumps(expected_build, sort_keys=True).encode()).hexdigest()}
    (ROOT / '.jenkins/expiry-webhook-verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'install', 'smoke', 'verify', 'retire-legacy'])
    args = parser.parse_args()
    if args.command == 'init':
        init_policy()
    elif args.command in {'verify', 'retire-legacy'}:
        verify(retire_legacy=args.command == 'retire-legacy')
    else:
        install(smoke=args.command == 'smoke')
