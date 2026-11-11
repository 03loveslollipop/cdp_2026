"""Package the compiled report, original evidence and reproducible LaTeX source."""
from pathlib import Path
import zipfile

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parent
OUTPUT = ROOT / 'output/pdf'


def build_bundle(pdf, markdown, assets):
    bundle = OUTPUT / 'Informe_unificado_Jenkins_GCP_ES.zip'
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(pdf, pdf.name)
        for path in [markdown, DIRECTORY / 'README.md', DIRECTORY / 'requirements.txt',
                     DIRECTORY / 'informe.json', DIRECTORY / 'evidencias.json',
                     DIRECTORY / 'github-verification.json', DIRECTORY / 'cleanup-verification.json',
                     DIRECTORY / 'gcp-verification.json',
                     DIRECTORY / 'build_report.py', DIRECTORY / 'bundle_report.py', DIRECTORY / 'latex-build.json', *sorted(assets.glob('*'))]:
            archive.write(path, str(Path('fuentes') / path.relative_to(DIRECTORY)))
        for path in sorted((DIRECTORY / 'latex').rglob('*')):
            if path.is_file() and path.suffix in {'.tex', '.cls', '.def', '.py', '.md'}:
                archive.write(path, str(Path('fuentes') / path.relative_to(DIRECTORY)))
        for path in ['docs/jenkins.md', 'docs/jenkins-execution.md', 'docs/model-results.md',
                     'docs/gcp-training.md', 'docs/gcp-execution.md', 'docs/github-webhook.md', 'docs/expiry-policy.md',
                     'output/jenkins-receipts/summary.json', 'output/playwright/index.json',
                     'output/playwright/gcp/index.json', 'output/training-runtime.json',
                     'output/credit-pipeline-dashboard.json']:
            archive.write(ROOT / path, 'anexos/' + path)
        # Keep the relative screenshot/chart links in the annex runbooks usable.
        for folder in ['output/playwright', 'output/local-baseline/figures', 'output/comparison',
                       'output/comparison-gcp', 'output/comparison-final']:
            for path in sorted((ROOT / folder).rglob('*.png')):
                archive.write(path, 'anexos/' + str(path.relative_to(ROOT)))
        archive.write(ROOT.parent / 'CLOUD_DEPLOYMENT_INVENTORY.md',
                      'anexos/CLOUD_DEPLOYMENT_INVENTORY.md')
        for path in sorted((ROOT / 'output/github-webhook').glob('*')):
            if path.is_file():
                archive.write(path, 'anexos/output/github-webhook/' + path.name)
        branch_evidence = ROOT / 'output/github-webhook/all-branches'
        for path in sorted(branch_evidence.glob('*')):
            if path.is_file() and (path.name in {'verification.json', 'push-probe.json'} or
                                  path.name.startswith(('master-', 'ci__webhook-all-branches-20261109-'))):
                archive.write(path, 'anexos/' + str(path.relative_to(ROOT)))
        for path in sorted((ROOT / 'output/github-webhook/japanese-validation').glob('*')):
            if path.is_file() and path.suffix in {'.json', '.txt'}:
                archive.write(path, 'anexos/' + str(path.relative_to(ROOT)))
        for path in sorted((ROOT / 'output/gcp-receipts').glob('*.json')):
            archive.write(path, 'anexos/output/gcp-receipts/' + path.name)
        for path in ['output/comparison-gcp/comparison.csv', 'output/comparison-gcp/README.md',
                     'output/vertex-custom/comparison.json', 'output/vertex-custom-normalized.json',
                     'output/vertex-automl-native.json', 'output/comparison-final/comparison.csv',
                     'output/comparison-final/README.md', 'cloud/native_evaluation.py',
                     'cloud/compare.py', 'output/cloud-data-gcp/manifest.json']:
            archive.write(ROOT / path, 'anexos/' + path)
        for path in ['Jenkinsfile', 'ci/configure_multibranch.py', 'ci/validate_structure.py',
                     'ci/jenkins/configure_multibranch.groovy', 'ci/jenkins/plugins.txt',
                     'ci/jenkins/plugins.lock.json', 'ci/jenkins/init.groovy.d/20-locale.groovy',
                     'cloud/webhook/receiver.py',
                     'cloud/webhook/main.tf', 'tests/test_branch_ci.py', 'tests/test_webhook_receiver.py']:
            archive.write(ROOT / path, 'anexos/' + path)
    return bundle
