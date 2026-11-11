# Fuentes LaTeX del reporte de resultados

`main.tex` conserva el título y autor editados. `contenido.tex` contiene el
informe de resultados y el anexo de evidencia. `style.tex` define las extensiones
de la plantilla Tufte de `/home/zerotwo/vis/report`. Los archivos de clase
y definición originales se conservaron sin cambios.

Desde esta carpeta:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

El resultado es `main.pdf`. El ZIP de fuentes mantiene esta estructura y las
imágenes en `../assets/`; puede compilarse sin el repositorio ni cuentas cloud.

Dependencias: `latexmk`, pdfLaTeX y TeX Live con Tufte-LaTeX, `babel-spanish`,
`mathpazo`, `graphicx`, `booktabs`, `xcolor`, `tabularx`, `xurl`, `seqsplit`,
`capt-of` y `needspace`. En Debian/Ubuntu suelen estar en `latexmk`,
`texlive-latex-extra`, `texlive-fonts-recommended` y `texlive-lang-spanish`.

Para actualizar los entregables desde la raíz del repositorio:

```bash
python3 04_jenkins_report/build_report.py
```

El comando utiliza el LaTeX editado y no sobrescribe su contenido. El JSON y el
Markdown son exportaciones de la última revisión editorial. El conversor
`generate.py` pertenece a la versión previa y no debe ejecutarse sobre esta
edición. Las imágenes originales y sus hashes se registran en `../evidencias.json`.

Los avisos de licencia y procedencia de la plantilla están en `template/`.
