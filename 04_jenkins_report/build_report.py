"""Build a self-contained Spanish PDF, Markdown report and submission ZIP.

Run from the repository root with Python + reportlab + pillow. Input text lives
in informe.json; screenshots are copied byte-for-byte, never reconstructed.
"""
import hashlib
import json
from pathlib import Path
import shutil
from xml.sax.saxutils import escape
import zipfile

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                               Table, TableStyle, PageBreak, KeepTogether)

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parent
OUTPUT = ROOT / 'output/pdf'
WIDTH, HEIGHT = A4
MARGIN = 42
CONTENT_WIDTH = WIDTH - 2 * MARGIN


def build():
    report = json.loads((DIRECTORY / 'informe.json').read_text())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    assets = DIRECTORY / 'assets'
    assets.mkdir(exist_ok=True)
    font = Path('/usr/share/fonts/truetype/dejavu')
    pdfmetrics.registerFont(TTFont('Report', str(font / 'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('ReportBold', str(font / 'DejaVuSans-Bold.ttf')))
    pdfmetrics.registerFontFamily('Report', normal='Report', bold='ReportBold')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('TitleES', fontName='ReportBold', fontSize=24, leading=31,
                              textColor=colors.HexColor('#143653'), spaceAfter=18))
    styles.add(ParagraphStyle('SectionES', fontName='ReportBold', fontSize=17, leading=23,
                              textColor=colors.HexColor('#143653'), spaceAfter=13))
    styles.add(ParagraphStyle('BodyES', fontName='Report', fontSize=9.4, leading=14.1,
                              spaceAfter=10, alignment=TA_LEFT, splitLongWords=True))
    styles.add(ParagraphStyle('CaptionES', fontName='Report', fontSize=8, leading=11.5,
                              textColor=colors.HexColor('#42576a'), spaceBefore=7, spaceAfter=12))
    styles.add(ParagraphStyle('CellES', fontName='Report', fontSize=8, leading=11))
    styles.add(ParagraphStyle('CellHeadES', fontName='ReportBold', fontSize=8, leading=11,
                              textColor=colors.white))

    def paragraph(text, style='BodyES'):
        return Paragraph(escape(text).replace('\n', '<br/>'), styles[style])

    flow, md, manifest = [], [f'# {report["title"]}\n', report['subtitle'] + '\n'], []
    for index, page in enumerate(report['pages']):
        if index:
            flow.append(PageBreak())
        flow.append(paragraph(page['title'], 'TitleES' if index == 0 else 'SectionES'))
        md.append(f'\n## {page["title"]}\n')
        for block in page['blocks']:
            if 'text' in block:
                flow.append(paragraph(block['text']))
                md.append(block['text'] + '\n')
            if 'table' in block:
                rows = block['table']
                ratios = block.get('widths', [1] * len(rows[0]))
                widths = [CONTENT_WIDTH * ratio / sum(ratios) for ratio in ratios]
                cells = [[paragraph(str(value), 'CellHeadES' if row_index == 0 else 'CellES')
                          for value in row] for row_index, row in enumerate(rows)]
                table = Table(cells, colWidths=widths, repeatRows=1, hAlign='LEFT')
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#143653')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#eff4f7'), colors.white]),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                    ('TOPPADDING', (0, 0), (-1, -1), 7),
                    ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#2e8395')),
                ]))
                flow += [table, Spacer(1, 12)]
                md.append('| ' + ' | '.join(rows[0]) + ' |')
                md.append('| ' + ' | '.join(['---'] * len(rows[0])) + ' |')
                md.extend('| ' + ' | '.join(map(str, row)) + ' |' for row in rows[1:])
                md.append('')
            if 'image' in block:
                source = ROOT / block['image']
                target = assets / source.name
                shutil.copyfile(source, target)
                sha = hashlib.sha256(target.read_bytes()).hexdigest()
                record = {'file': f'assets/{target.name}', 'source': block['image'],
                          'sha256': sha, 'caption': block['caption']}
                if record not in manifest:
                    manifest.append(record)
                with PILImage.open(target) as picture:
                    width, height = picture.size
                image_width = CONTENT_WIDTH
                image_height = image_width * height / width
                # Entire originals remain in the bundle. The PDF uses exact,
                # aspect-preserving scaling, without cropping or retouching.
                maximum = block.get('max_height', 360)
                if image_height > maximum:
                    image_width *= maximum / image_height
                    image_height = maximum
                picture = Image(str(target), width=image_width, height=image_height)
                flow.append(KeepTogether([picture, paragraph(block['caption'], 'CaptionES')]))
                md.append(f'![{block["caption"]}](assets/{target.name})\n')

    md += ['\n## Referencias\n']
    flow += [PageBreak(), paragraph('Referencias', 'SectionES')]
    for reference in report['references']:
        label, url = reference['label'], reference['url']
        flow.append(Paragraph(f'<a href="{escape(url, {chr(34): "&quot;"})}" color="#246a8b">'
                              f'{escape(label)}</a>', styles['CaptionES']))
        md.append(f'- [{label}]({url})')

    markdown = DIRECTORY / 'INFORME_RESULTADOS_ES.md'
    markdown.write_text('\n'.join(md) + '\n')
    (DIRECTORY / 'evidencias.json').write_text(json.dumps({
        'report_date': report['date'], 'screenshots_are_originals': True, 'assets': manifest,
    }, indent=2, ensure_ascii=False) + '\n')
    pdf = OUTPUT / 'Informe_unificado_Jenkins_GCP_ES.pdf'

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#2e8395'))
        canvas.line(MARGIN, HEIGHT - 29, WIDTH - MARGIN, HEIGHT - 29)
        canvas.setFont('Report', 7)
        canvas.setFillColor(colors.HexColor('#42576a'))
        canvas.drawString(MARGIN, 24, 'cdp_2026 | Informe de resultados | ' + report['date'])
        canvas.drawRightString(WIDTH - MARGIN, 24, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(str(pdf), pagesize=A4, rightMargin=MARGIN, leftMargin=MARGIN,
                                 topMargin=46, bottomMargin=46,
                                 title=report['title'], author='Proyecto cdp_2026',
                                 subject='Jenkins, evaluación de modelos y estado de GCP')
    document.build(flow, onFirstPage=decorate, onLaterPages=decorate)
    bundle = OUTPUT / 'Informe_unificado_Jenkins_GCP_ES.zip'
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(pdf, pdf.name)
        for path in [markdown, DIRECTORY / 'README.md', DIRECTORY / 'requirements.txt',
                     DIRECTORY / 'informe.json', DIRECTORY / 'evidencias.json',
                     DIRECTORY / 'github-verification.json', DIRECTORY / 'cleanup-verification.json',
                     DIRECTORY / 'gcp-verification.json',
                     DIRECTORY / 'build_report.py', *sorted(assets.glob('*'))]:
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
        for path in sorted((ROOT / 'output/gcp-receipts').glob('*.json')):
            archive.write(path, 'anexos/output/gcp-receipts/' + path.name)
        for path in ['output/comparison-gcp/comparison.csv', 'output/comparison-gcp/README.md',
                     'output/vertex-custom/comparison.json', 'output/vertex-custom-normalized.json',
                     'output/vertex-automl-native.json', 'output/comparison-final/comparison.csv',
                     'output/comparison-final/README.md', 'cloud/native_evaluation.py',
                     'cloud/compare.py', 'output/cloud-data-gcp/manifest.json']:
            archive.write(ROOT / path, 'anexos/' + path)
    print(f'PDF: {pdf}\nMarkdown: {markdown}\nBundle: {bundle}\nOriginal images: {len(manifest)}')


if __name__ == '__main__':
    build()
