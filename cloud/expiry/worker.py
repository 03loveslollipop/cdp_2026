"""Allowlisted Jenkins teardown, embedded in a pinned Cloud Build task payload.

POLICY is injected as a literal by schedule.py. No project/resource names are
accepted from execution arguments. --dry-run performs inventory and IAM checks.
"""
import json
import subprocess
import ssl
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class API:
    def __init__(self):
        self.token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], text=True).strip()
        # This pinned image provides its CA bundle inside the SDK, rather than
        # /etc/ssl. Use that verified bundle and retain certificate validation.
        self.tls = ssl.create_default_context(cafile='/usr/lib/google-cloud-sdk/lib/third_party/certifi/cacert.pem')

    def request(self, method, url, body=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        try:
            with urlopen(Request(url, data=data, headers=headers, method=method), timeout=60, context=self.tls) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except HTTPError as error:
            if error.code == 404:
                return None
            raise RuntimeError(f'{method} {url}: HTTP {error.code}: {error.read().decode()}') from error

    def wait(self, operation, origin):
        if not operation:
            return
        if 'selfLink' in operation:
            url = operation['selfLink']
        elif operation.get('name') and '/operations/' in operation['name']:
            url = origin + ('/' if origin.endswith('/v2') else '/v1/') + operation['name']
        else:
            return
        for _ in range(200):
            if operation.get('status') == 'DONE' or operation.get('done'):
                if operation.get('error'):
                    raise RuntimeError(json.dumps(operation['error']))
                return
            time.sleep(3)
            operation = self.request('GET', url)
            if operation is None:
                return
        raise TimeoutError(f'Operation still pending: {url}')


def targets(policy):
    project, region, zone = policy['project'], policy['region'], policy['zone']
    compute = f'https://compute.googleapis.com/compute/v1/projects/{project}'
    workload = [
        ('vm', f'{compute}/zones/{zone}/instances/semester-jenkins', 'https://compute.googleapis.com'),
        ('disk', f'{compute}/zones/{zone}/disks/semester-jenkins', 'https://compute.googleapis.com'),
        ('firewall', f'{compute}/global/firewalls/semester-jenkins-iap', 'https://compute.googleapis.com'),
        ('subnet', f'{compute}/regions/{region}/subnetworks/semester-jenkins', 'https://compute.googleapis.com'),
        ('network', f'{compute}/global/networks/semester-jenkins', 'https://compute.googleapis.com'),
        ('images', f'https://artifactregistry.googleapis.com/v1/projects/{project}/locations/{region}/repositories/semester-jenkins', 'https://artifactregistry.googleapis.com'),
        ('admin_secret', f'https://secretmanager.googleapis.com/v1/projects/{project}/secrets/semester-jenkins-admin', ''),
        ('notify_secret', f'https://secretmanager.googleapis.com/v1/projects/{project}/secrets/semester-jenkins-notify', ''),
        ('controller_identity', f'https://iam.googleapis.com/v1/projects/{project}/serviceAccounts/semester-jenkins@{project}.iam.gserviceaccount.com', ''),
    ]
    if policy.get('webhook_enabled'):
        relay = {
            'relay_service': (f'https://run.googleapis.com/v2/projects/{project}/locations/{region}/services/semester-jenkins-webhook', 'https://run.googleapis.com/v2'),
            'relay_firewall': (f'{compute}/global/firewalls/semester-jenkins-webhook', 'https://compute.googleapis.com'),
            'relay_subnet': (f'{compute}/regions/{region}/subnetworks/semester-jenkins-webhook', 'https://compute.googleapis.com'),
            'relay_secret': (f'https://secretmanager.googleapis.com/v1/projects/{project}/secrets/semester-jenkins-webhook', ''),
            'relay_identity': (f'https://iam.googleapis.com/v1/projects/{project}/serviceAccounts/semester-jenkins-webhook@{project}.iam.gserviceaccount.com', ''),
        }
        # The Cloud Run revision must release its subnet before deleting the VPC.
        workload = [('relay_service', *relay['relay_service']), *workload]
        for before, kind in [('firewall', 'relay_firewall'), ('subnet', 'relay_subnet'),
                             ('admin_secret', 'relay_secret'), ('controller_identity', 'relay_identity')]:
            position = next(i for i, item in enumerate(workload) if item[0] == before)
            workload.insert(position, (kind, *relay[kind]))
    return workload


def run(policy, *, dry_run, api=None, now=None):
    now = now or datetime.now(timezone.utc)
    expires = datetime.fromisoformat(policy['expires_at'].replace('Z', '+00:00'))
    if policy['project'] != 'nb-core-dev-99d0' or policy['region'] != 'us-central1' or policy['zone'] != 'us-central1-a':
        raise ValueError('Refusing cleanup outside the verified Jenkins lab location')
    if not dry_run and now < expires:
        raise RuntimeError('Expiry has not arrived; refusing early deletion')
    api = api or API()
    inventory = []
    for kind, url, origin in targets(policy):
        resource = api.request('GET', url)
        if kind == 'vm' and resource is not None:
            if resource.get('labels', {}).get('purpose') != 'semester-lab' or resource.get('labels', {}).get('component') != 'jenkins':
                raise ValueError('VM labels do not match the approved lab')
        if kind == 'disk' and resource is not None:
            if any(not user.endswith('/instances/semester-jenkins') for user in resource.get('users', [])):
                raise ValueError('Lab disk is attached to an unrelated VM')
        inventory.append({'kind': kind, 'url': url, 'exists': resource is not None})
    print(json.dumps({'dry_run': dry_run, 'expires_at': policy['expires_at'], 'inventory': inventory}), flush=True)
    if dry_run:
        project = policy['project']
        permissions = policy['required_project_permissions']
        result = api.request('POST', f'https://cloudresourcemanager.googleapis.com/v1/projects/{project}:testIamPermissions', {'permissions': permissions})
        missing = set(permissions) - set((result or {}).get('permissions', []))
        if missing:
            raise RuntimeError(f'Cleanup worker lacks permissions: {sorted(missing)}')
        print('DRY RUN PASSED: all required deletion permissions and target reads verified; nothing deleted', flush=True)
        return inventory
    # Deleting the instance also stops its containers and releases its ephemeral
    # external IPv4. Explicit disk deletion covers an auto-delete setting change.
    for kind, url, origin in targets(policy):
        operation = api.request('DELETE', url)
        api.wait(operation, origin)
        if api.request('GET', url) is not None:
            raise RuntimeError(f'{kind} still exists after deletion')
        print(f'ABSENT: {kind} {url}', flush=True)
    project = policy['project']
    # Cancel all future fallback attempts only after every workload is absent.
    queue = f'https://cloudtasks.googleapis.com/v2/projects/{project}/locations/{policy["region"]}/queues/{policy["queue"]}'
    api.request('DELETE', queue)
    api.request('DELETE', f'https://iam.googleapis.com/v1/projects/{project}/serviceAccounts/semester-expiry-trigger@{project}.iam.gserviceaccount.com')
    for role in ['semesterJenkinsExpiryDispatch', 'semesterJenkinsCleanup']:
        api.request('DELETE', f'https://iam.googleapis.com/v1/projects/{project}/roles/{role}')
    # Independent self-resource IAM binding permits this final request after its
    # temporary project role has been deleted. No key is created at any point.
    api.request('DELETE', f'https://iam.googleapis.com/v1/projects/{project}/serviceAccounts/semester-jenkins-expiry@{project}.iam.gserviceaccount.com')
    print('CLEANUP COMPLETE: workload, queue and temporary identities removed', flush=True)
    return inventory


if __name__ == '__main__':
    run(POLICY, dry_run='--dry-run' in sys.argv)
