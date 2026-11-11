"""Cleanup safety and idempotence without deleting any cloud resource."""
from datetime import datetime, timedelta, timezone
import base64

import pytest

from cloud.expiry.worker import run
from cloud.expiry.schedule import build


NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
POLICY = {'project': 'nb-core-dev-99d0', 'region': 'us-central1',
          'zone': 'us-central1-a', 'expires_at': '2026-11-13T00:00:00Z',
          'queue': 'semester-jenkins-expiry-test',
          'required_project_permissions': ['compute.instances.delete']}


class FakeAPI:
    def __init__(self, vm=None, disk=None):
        self.calls, self.vm, self.disk = [], vm, disk

    def request(self, method, url, body=None):
        self.calls.append((method, url))
        if method == 'GET' and '/instances/' in url:
            return self.vm
        if method == 'GET' and '/disks/' in url:
            return self.disk
        if method == 'POST' and url.endswith(':testIamPermissions'):
            return {'permissions': POLICY['required_project_permissions']}
        return None

    def wait(self, operation, origin):
        pass


def test_early_cleanup_performs_no_requests():
    api = FakeAPI()
    with pytest.raises(RuntimeError, match='refusing early deletion'):
        run(POLICY, dry_run=False, api=api, now=NOW)
    assert not api.calls


def test_cloud_build_arguments_fit_the_api_limit_and_preserve_worker():
    config = build({**POLICY, 'runtime_image': 'example@sha256:test'}, dry_run=True)
    assert config['steps'][0]['entrypoint'].endswith('/bundledpythonunix/bin/python3')
    args = config['steps'][0]['args']
    assert all(len(arg) <= 10000 for arg in args)
    source = base64.b64decode(''.join(arg for arg in args[2:] if arg != '--dry-run')).decode()
    assert 'Expiry has not arrived; refusing early deletion' in source
    assert args[-1] == '--dry-run'


def test_dry_run_can_only_read_and_test_permissions():
    api = FakeAPI()
    run(POLICY, dry_run=True, api=api, now=NOW)
    assert all(method == 'GET' or url.endswith(':testIamPermissions') for method, url in api.calls)


def test_wrong_project_is_refused_before_any_request():
    api = FakeAPI()
    with pytest.raises(ValueError, match='outside the verified'):
        run({**POLICY, 'project': 'nb-risk-ml-dev-99d0'}, dry_run=False, api=api,
            now=NOW + timedelta(days=6))
    assert not api.calls


def test_unrelated_vm_or_disk_blocks_all_deletes():
    for api in [FakeAPI(vm={'labels': {'purpose': 'another-workload'}}),
                FakeAPI(disk={'users': ['projects/x/zones/x/instances/someone-else']})]:
        with pytest.raises(ValueError):
            run(POLICY, dry_run=False, api=api, now=NOW + timedelta(days=6))
        assert not any(method == 'DELETE' for method, _ in api.calls)


def test_missing_resources_are_idempotent_and_self_identity_is_last():
    api = FakeAPI()
    run(POLICY, dry_run=False, api=api, now=NOW + timedelta(days=6))
    deleted = [url for method, url in api.calls if method == 'DELETE']
    assert len(deleted) == 14
    assert deleted[0].endswith('/instances/semester-jenkins')
    assert '/queues/' in deleted[9]
    assert deleted[-1].endswith('semester-jenkins-expiry@nb-core-dev-99d0.iam.gserviceaccount.com')
    assert all('nb-core-dev-99d0' in url for url in deleted)


def test_relay_is_removed_before_the_shared_lab_network():
    api = FakeAPI()
    run({**POLICY, 'webhook_enabled': True}, dry_run=False, api=api, now=NOW + timedelta(days=6))
    deleted = [url for method, url in api.calls if method == 'DELETE']
    assert len(deleted) == 19
    assert deleted[0].endswith('/services/semester-jenkins-webhook')
    network = next(i for i, url in enumerate(deleted) if url.endswith('/networks/semester-jenkins'))
    subnet = next(i for i, url in enumerate(deleted) if url.endswith('/subnetworks/semester-jenkins-webhook'))
    assert subnet < network
