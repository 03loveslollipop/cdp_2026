"""Prepare secrets and an isolated Git snapshot without changing the working branch."""
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


def main():
    runtime = ROOT / '.jenkins'
    secret_dir = runtime / 'secrets'
    secret_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ('admin-password', 'notify-token'):
        path = secret_dir / name
        if not path.exists():
            path.write_text(secrets.token_urlsafe(32) + '\n')
            # Docker's unprivileged Jenkins UID needs to read this bind-mounted file.
            # The parent directory remains owner-only on the host.
            path.chmod(0o444)
    (runtime / 'receipts').mkdir(exist_ok=True)
    files = set(git('ls-files').splitlines())
    files.update({'Jenkinsfile', 'requirements-ci.txt', 'docker-compose.yml',
                  'tests/test_semester_ci.py', 'tests/test_github_webhook.py', 'tests/test_webhook_receiver.py'})
    for directory in ('ci', 'cloud', 'docs'):
        files.update(str(p.relative_to(ROOT)) for p in (ROOT / directory).rglob('*')
                     if p.is_file() and not {'__pycache__', '.terraform', 'plugins-cache'}.intersection(p.parts)
                     and not p.name.startswith('terraform.tfstate')
                     and p.suffix != '.tfplan'
                     and p.name not in {'config.local.json', 'pipeline.json', 'terraform.tfvars'})
    files = {p for p in files if (ROOT / p).is_file()}
    forbidden = {'.env', 'credentials.json', 'secrets.json'}
    if any(Path(p).name in forbidden or p.startswith('.jenkins/') for p in files):
        raise ValueError('Refusing to put secrets in the source snapshot')
    with tempfile.TemporaryDirectory(prefix='credit-ci-source-') as directory:
        temp = Path(directory)
        for name in sorted(files):
            target = temp / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        git('init', '-b', 'ci-review', cwd=temp)
        git('add', '--all', cwd=temp)
        git('-c', 'user.name=Local Jenkins Lab', '-c', 'user.email=jenkins@localhost',
            'commit', '-m', 'Local review snapshot of credit pipeline implementation', cwd=temp)
        mirror = runtime / 'source.git'
        if not mirror.exists():
            git('clone', '--bare', str(temp), str(mirror))
        else:
            git('--git-dir', str(mirror), 'fetch', str(temp),
                '+refs/heads/ci-review:refs/heads/ci-review')
        # Permit the container's unprivileged UID to traverse the read-only mirror.
        for path in mirror.rglob('*'):
            path.chmod(0o755 if path.is_dir() else 0o644)
    receipt = {'upstream': git('remote', 'get-url', 'origin'),
               'source_branch': git('branch', '--show-current'),
               'source_commit': git('rev-parse', 'HEAD'),
               'snapshot_commit': git('--git-dir', str(mirror), 'rev-parse', 'ci-review'),
               'snapshot_files': len(files), 'remote_pushed': False}
    (runtime / 'source-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    print('Ready: docker compose up -d --build; Jenkins: http://127.0.0.1:18081')


if __name__ == '__main__':
    main()
