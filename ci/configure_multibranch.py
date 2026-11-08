"""Configure the scoped Jenkins multibranch project through its private tunnel."""
import argparse
import base64
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18083')
    parser.add_argument('--password-file', type=Path, default=Path('.jenkins/secrets/admin-password'))
    parser.add_argument('--ci-revision', required=True)
    parser.add_argument('--primary-branch', choices=['main', 'master'], required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path not in {'', '/'}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise SystemExit('Use the private loopback IAP tunnel URL')
    if not re.fullmatch(r'[a-f0-9]{40}', args.ci_revision):
        raise SystemExit('Pin CI code to a complete Git commit SHA')
    script = Path(__file__).with_name('jenkins').joinpath('configure_multibranch.groovy').read_text()
    script = script.replace('__CI_REVISION_JSON__', json.dumps(args.ci_revision))
    script = script.replace('__PRIMARY_BRANCH_JSON__', json.dumps(args.primary_branch))
    if not args.apply:
        print(script)
        return
    password = args.password_file.read_text().strip()
    headers = {'Authorization': 'Basic ' + base64.b64encode(('admin:' + password).encode()).decode()}
    base = args.url.rstrip('/')
    with urlopen(Request(base + '/crumbIssuer/api/json', headers=headers), timeout=20) as response:
        crumb = json.load(response)
        cookie = response.headers.get('Set-Cookie', '').split(';', 1)[0]
    headers[crumb['crumbRequestField']] = crumb['crumb']
    if cookie:
        headers['Cookie'] = cookie
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    with urlopen(Request(base + '/scriptText', headers=headers,
                         data=urlencode({'script': script}).encode()), timeout=180) as response:
        result = response.read().decode()
    if not result.strip().startswith('{'):
        raise RuntimeError('Jenkins configuration failed; inspect the private response without publishing credentials')
    print(json.dumps(json.loads(result), indent=2))


if __name__ == '__main__':
    main()
