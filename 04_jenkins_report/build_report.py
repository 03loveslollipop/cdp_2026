"""Build the Spanish Tufte-LaTeX PDF and self-contained submission archives.

Requires Python with Pillow, plus latexmk/pdflatex and the TeX Live packages
listed in latex/README.md. The edited LaTeX files are authoritative; this
command compiles and packages them without regenerating or overwriting text.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from bundle_report import build_bundle

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parent
OUTPUT = ROOT / 'output/pdf'
LATEX = DIRECTORY / 'latex'


def build():
    for program in ['latexmk', 'pdflatex']:
        if not shutil.which(program):
            raise SystemExit(f'{program} is required; see latex/README.md')
    manifest = json.loads((DIRECTORY / 'evidencias.json').read_text())['assets']
    build_dir = ROOT / 'tmp/pdfs/latex-build'
    build_dir.mkdir(parents=True, exist_ok=True)
    command = ['latexmk', '-pdf', '-interaction=nonstopmode', '-halt-on-error',
               '-outdir=' + str(build_dir), 'main.tex']
    with (build_dir / 'compile.txt').open('w') as log:
        result = subprocess.run(command, cwd=LATEX, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(f'LaTeX failed; inspect {build_dir / "compile.txt"}')
    log = (build_dir / 'main.log').read_text(errors='replace')
    for issue in ['Overfull \\hbox', 'Overfull \\vbox', 'Missing character:']:
        if issue in log:
            raise SystemExit(f'{issue}: resolve layout warnings in {build_dir / "main.log"}')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pdf = OUTPUT / 'Informe_unificado_Jenkins_GCP_ES.pdf'
    shutil.copyfile(build_dir / 'main.pdf', pdf)
    shutil.copyfile(build_dir / 'main.pdf', LATEX / 'main.pdf')
    provenance = {
        'engine': 'pdfLaTeX', 'template': 'tufte-handout',
        'reference': '/home/zerotwo/vis/report',
        'upstream_commit': 'efb8c8e836890bad71fb5834acdd316ebde6db12',
        'original_images': len(manifest),
        'template_sha256': {name: hashlib.sha256((LATEX / name).read_bytes()).hexdigest()
                            for name in ['tufte-handout.cls', 'tufte-common.def']},
        'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
    }
    (DIRECTORY / 'latex-build.json').write_text(json.dumps(provenance, indent=2) + '\n')
    bundle = build_bundle(pdf, DIRECTORY / 'INFORME_RESULTADOS_ES.md', DIRECTORY / 'assets')
    sources = OUTPUT / 'Informe_unificado_Jenkins_GCP_ES_LaTeX_fuentes.zip'
    base = Path('Informe_Jenkins_GCP_LaTeX')
    with zipfile.ZipFile(sources, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(LATEX.rglob('*')):
            if path.is_file() and path.suffix in {'.tex', '.cls', '.def', '.py', '.md'}:
                archive.write(path, str(base / 'latex' / path.relative_to(LATEX)))
        for record in manifest:
            path = DIRECTORY / record['file']
            archive.write(path, str(base / record['file']))
        for name in ['informe.json', 'evidencias.json', 'latex-build.json']:
            archive.write(DIRECTORY / name, str(base / name))
    files = [pdf, bundle, sources]
    (OUTPUT / 'Informe_unificado_Jenkins_GCP_ES.sha256').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in files))
    print(f'PDF: {pdf}\nEvidence ZIP: {bundle}\nLaTeX source ZIP: {sources}')
    print(f'Original images: {len(manifest)}; compile log: {build_dir / "main.log"}')


if __name__ == '__main__':
    build()
