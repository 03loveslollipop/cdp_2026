"""Fetch locked Jenkins plugins from official Maven, checking update-center hashes."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[1]
LOCK = DIRECTORY / 'plugins.lock.json'
JENKINS_CORE = '2.580.2'


def supports_core(item):
    return tuple(map(int, item['required_core'].split('.'))) <= tuple(map(int, JENKINS_CORE.split('.')))


def refresh():
    metadata = ROOT / '.jenkins/update-center.json'
    if not metadata.exists():
        request = Request('https://archives.jenkins.io/updates/dynamic-stable-2.580.2/update-center.actual.json',
                          headers={'Accept-Encoding': 'gzip'})
        with urlopen(request, timeout=60) as response:
            data = response.read()
            if response.headers.get('Content-Encoding') == 'gzip':
                data = gzip.decompress(data)
        metadata.parent.mkdir(exist_ok=True)
        metadata.write_bytes(data)
    plugins = json.loads(metadata.read_text())['plugins']
    previous = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    required = set((DIRECTORY / 'plugins.txt').read_text().split())
    pending = list(required)
    while pending:
        name = pending.pop()
        for dependency in plugins[name]['dependencies']:
            if not dependency['optional'] and dependency['name'] not in required:
                required.add(dependency['name'])
                pending.append(dependency['name'])
    locked = {}
    for name in sorted(required):
        item = plugins[name]
        group, artifact, version = item['gav'].split(':')
        url = f'https://repo.jenkins-ci.org/public/{group.replace(".", "/")}/{artifact}/{version}/{artifact}-{version}.hpi'
        locked[name] = {'version': version, 'sha256': item['sha256'], 'url': url,
                        'required_core': item['requiredCore']}
        # Even a version-specific update-center snapshot can contain a plugin
        # requiring a newer controller. Keep a verified compatible pin instead
        # of producing a lock that breaks JUnit on the running lab controller.
        if not supports_core(locked[name]):
            if name not in previous or not supports_core(previous[name]):
                raise ValueError(f'{name}: no compatible pin for Jenkins {JENKINS_CORE}')
            locked[name] = previous[name]
    LOCK.write_text(json.dumps(locked, indent=2) + '\n')
    print(f'Locked {len(locked)} plugins from the official Jenkins 2.580.2 update center', flush=True)


def fetch():
    locked = json.loads(LOCK.read_text())
    incompatible = [name for name, item in locked.items() if not supports_core(item)]
    if incompatible:
        raise ValueError(f'Plugins require a newer controller than {JENKINS_CORE}: {incompatible}')
    destination = DIRECTORY / 'plugins-cache'
    destination.mkdir(exist_ok=True)

    def download(pair):
        name, item = pair
        path = destination / f'{name}.jpi'

        def valid(data):
            return base64.b64encode(hashlib.sha256(data).digest()).decode() == item['sha256']

        if path.exists() and valid(path.read_bytes()):
            return
        for attempt in range(3):
            try:
                with urlopen(item['url'], timeout=60) as response:
                    data = response.read()
                if not valid(data):
                    raise ValueError(f'{name}: checksum does not match official metadata')
                path.write_bytes(data)
                print(f'Verified {name}:{item["version"]}', flush=True)
                return
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(download, locked.items()))
    for path in destination.glob('*.jpi'):
        if path.stem not in locked:
            path.unlink()
    print(f'All {len(locked)} plugins verified', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-lock', action='store_true')
    args = parser.parse_args()
    if args.refresh_lock or not LOCK.exists():
        refresh()
    fetch()
