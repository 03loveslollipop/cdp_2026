"""Emit completion to the exercise's private webhook and save a local receipt."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

job_path = '/'.join('job/' + quote(part, safe='') for part in os.environ['JOB_NAME'].split('/'))
build_path = f"{job_path}/{os.environ['BUILD_NUMBER']}/"
build_url = os.environ.get('BUILD_URL') or os.environ.get('JENKINS_URL', '/').rstrip('/') + '/' + build_path

payload = {
    'job': os.environ['JOB_NAME'], 'build': os.environ['BUILD_NUMBER'],
    'status': os.environ['PIPELINE_RESULT'], 'url': build_url,
    'commit': os.environ.get('GIT_COMMIT', ''),
}
Path('reports').mkdir(exist_ok=True)
Path('reports/notification.json').write_text(json.dumps(payload, indent=2) + '\n')
token = Path(os.environ['NOTIFY_TOKEN_FILE']).read_text().strip()
request = Request(
    os.environ['NOTIFY_URL'], data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
    method='POST',
)
with urlopen(request, timeout=15) as response:
    if response.status != 202:
        raise RuntimeError(f'Notification receiver returned {response.status}')
print(f"Completion notification delivered: {payload['status']} build {payload['build']}")
