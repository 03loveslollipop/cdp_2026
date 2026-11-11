"""Generate editable Tufte LaTeX from the existing Spanish report."""
import hashlib
import json
from pathlib import Path
import re
import shutil

LATEX = Path(__file__).resolve().parent
DIRECTORY = LATEX.parent
ROOT = DIRECTORY.parent


def plain(text):
    text = text.replace('完了 (completado)', 'completado').replace('完了', 'completado').replace('–', '-').replace('—', ' - ').replace('…', '...')
    mapping = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
               '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
               '^': r'\textasciicircum{}', '→': r'\(\rightarrow\)',
               '≥': r'\(\geq\)', '≤': r'\(\leq\)'}
    return ''.join(mapping.get(c, c) for c in text)


def tex(text):
    """Allow identifiers, paths, URLs and SHAs to wrap in the narrow column."""
    result = []
    for token in re.split(r'(\s+)', str(text)):
        if not token:
            continue
        if token.isspace():
            result.append(' ')
            continue
        tail = ''
        while token and token[-1] in '.,;:':
            tail = token[-1] + tail
            token = token[:-1]
        if re.fullmatch(r'[0-9a-f]{12,64}', token):
            rendered = r'\texttt{\seqsplit{' + token + '}}'
        elif token.startswith(('https://', 'http://')):
            rendered = r'\url{' + token + '}'
        elif ((any(c in token for c in '/_@') and re.fullmatch(r'[A-Za-z0-9_./@:*%?=+\-]+', token))
              or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.\-]{27,}', token)):
            rendered = r'\nolinkurl{' + token + '}'
        else:
            rendered = plain(token)
        result.append(rendered + plain(tail))
    return ''.join(result)


def table(block):
    rows = block['table']
    n = len(rows[0])
    ratios = block.get('widths', [1] * n)
    weights = [n * r / sum(ratios) for r in ratios]
    specs = [r'>{\hsize=' + f'{w:.5f}' + r'\hsize\linewidth=\hsize\RaggedRight\arraybackslash}X' for w in weights]
    lines = [r'\par\medskip\begin{fullwidth}\noindent', r'\begin{minipage}{\linewidth}\small',
             r'\setlength{\tabcolsep}{5pt}\renewcommand{\arraystretch}{1.24}',
             r'\begin{tabularx}{\linewidth}{@{}' + ''.join(specs) + r'@{}}', r'\toprule']
    for i, row in enumerate(rows):
        cells = [tex(v) for v in row]
        if i == 0:
            cells = [r'\textbf{' + c + '}' for c in cells]
        lines.append(' & '.join(cells) + r' \\')
        if i == 0:
            lines.append(r'\midrule')
    return '\n'.join(lines + [r'\bottomrule', r'\end{tabularx}', r'\end{minipage}', r'\end{fullwidth}\par\medskip'])


def generate():
    report = json.loads((DIRECTORY / 'informe.json').read_text())
    assets = DIRECTORY / 'assets'
    assets.mkdir(exist_ok=True)
    manifest, chunks = [], []
    markdown = ['# ' + report['title'] + '\n', report['subtitle'] + '\n']
    image_index = 0
    notes = {'7.': 'La clase de incumplimiento es Pago_atiempo=0. Una accuracy alta no garantiza detección de impagos.',
             '9.5.': 'Todas las ramas ejecutan pruebas. Master añade entrenamiento, puertas de calidad y aprobación.',
             '10.7.': 'Se compara la clase 0. PR-AUC nativo de AutoML y AP de scikit-learn son métricas distintas.',
             '11.': 'Los créditos son una observación de facturación con retardo, no una factura atribuible a un único job.'}
    for index, page in enumerate(report['pages']):
        title = page['title'].replace('\n', ' ')
        markdown.append('\n## ' + page['title'] + '\n')
        if index == 0:
            chunks += [r'\marginnote{Proyecto \nolinkurl{cdp_2026}. Evidencia académica de ejecución; corte del 9 de noviembre de 2026.}',
                       r'\section{Resumen de resultados}']
        else:
            chunks.append(r'\FloatBarrier')
            if title.startswith(('1. ', '9. ', '10. ', '11. ', '12. ')):
                chunks.append(r'\clearpage')
            else:
                chunks.append(r'\Needspace{10\baselineskip}')
            heading = 'subsection' if re.match(r'^\d+\.\d+\.', title) else 'section'
            chunks.append('\\' + heading + '{' + tex(title) + '}')
            key = re.match(r'^\d+(?:\.\d+)?\.', title)
            if key and key.group() in notes:
                chunks.append(r'\marginnote{' + tex(notes[key.group()]) + '}')
        for block in page['blocks']:
            if 'text' in block:
                chunks.append(tex(block['text']) + '\n')
                markdown.append(block['text'] + '\n')
            if 'table' in block:
                chunks.append(table(block))
                rows = block['table']
                markdown += ['| ' + ' | '.join(rows[0]) + ' |', '| ' + ' | '.join(['---'] * len(rows[0])) + ' |']
                markdown.extend('| ' + ' | '.join(map(str, row)) + ' |' for row in rows[1:])
                markdown.append('')
            if 'image' in block:
                image_index += 1
                source = ROOT / block['image']
                target = assets / source.name
                shutil.copyfile(source, target)
                record = {'file': 'assets/' + target.name, 'source': block['image'],
                          'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'caption': block['caption']}
                if record not in manifest:
                    manifest.append(record)
                caption = re.sub(r'^Figura \d+\.\s*', '', block['caption'])
                macro = 'wideevidence' if block['image'].startswith('output/playwright/') else 'reportfigure'
                chunks.append('\\' + macro + '{' + source.name + '}{' + tex(caption) + '}{fig:evidence-' + str(image_index) + '}')
                if macro == 'reportfigure':
                    chunks.append(r'\FloatBarrier')
                markdown.append('![' + block['caption'] + '](assets/' + target.name + ')\n')
    chunks += [r'\FloatBarrier\clearpage', r'\section{Referencias}', r'\begin{enumerate}\small']
    markdown.append('\n## Referencias\n')
    for ref in report['references']:
        chunks.append(r'\item \href{' + ref['url'] + '}{' + tex(ref['label']) + '}.')
        markdown.append('- [' + ref['label'] + '](' + ref['url'] + ')')
    chunks.append(r'\end{enumerate}')
    (LATEX / 'contenido.tex').write_text('\n\n'.join(chunks) + '\n')
    (LATEX / 'main.tex').write_text(r'''\documentclass[a4paper,nobib,notoc]{tufte-handout}
\input{style}
\title[Jenkins y clasificación crediticia]{Jenkins y clasificación crediticia:\\Informe unificado de resultados}
\author{Mateo Monsalve Valencia}
\date{9 de noviembre de 2026}
\begin{document}
\maketitle
\input{contenido}
\end{document}
''')
    (DIRECTORY / 'INFORME_RESULTADOS_ES.md').write_text('\n'.join(markdown) + '\n')
    (DIRECTORY / 'evidencias.json').write_text(json.dumps({'report_date': report['date'],
        'screenshots_are_originals': True, 'assets': manifest}, indent=2, ensure_ascii=False) + '\n')
    print(f'Generated Tufte LaTeX: {len(report["pages"])} sections, {image_index} original images')
    return manifest


if __name__ == '__main__':
    generate()
