# Informe unificado en español

Documento para compartir: `../output/pdf/Informe_unificado_Jenkins_GCP_ES.pdf`. El ZIP del mismo nombre incorpora PDF, fuente, imágenes originales y anexos. También se puede leer [INFORME_RESULTADOS_ES.md](INFORME_RESULTADOS_ES.md).

Fuente editable: `informe.json`. Las imágenes se copian sin modificación desde `output/`; `evidencias.json` conserva sus SHA-256. El informe diferencia builds históricos, preparación posterior del webhook y entrenamiento Vertex pendiente. No publicar resultados ni capturas de actividades no ejecutadas.

Desde la raíz del repositorio, en Linux con las fuentes DejaVu Sans instaladas:

```bash
python3 -m venv .jenkins/report-venv
.jenkins/report-venv/bin/pip install -r 04_jenkins_report/requirements.txt
.jenkins/report-venv/bin/python 04_jenkins_report/build_report.py
pdftoppm -scale-to 1100 -png output/pdf/Informe_unificado_Jenkins_GCP_ES.pdf tmp/pdfs/revision
```

Crear `tmp/pdfs/` antes del último comando y revisar las páginas renderizadas. El PDF es autocontenido y el ZIP puede enviarse sin contraseñas ni estado del navegador. No se envió el informe a terceros.
