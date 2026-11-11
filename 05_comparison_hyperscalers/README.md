# Comparación de proveedores de nube

Borrador editable en español, preparado con la misma clase y estilo Tufte que el informe de Jenkins y GCP.

- `main.tex`: título, autor y documento principal.
- `contenido.tex`: texto y tablas de la comparación.
- `referencias.tex`: referencias bibliográficas citadas en el texto.
- `style.tex`, `tufte-handout.cls`, `tufte-common.def`: estilo local y clase del informe original.
- `main.pdf`: vista compilada del borrador.

Para compilar desde esta carpeta: `latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex`. La investigación de respaldo está en `../docs/comparacion_azure_costos.md` y `../cloud/aws/comparison-notes.md`. Azure es una propuesta teórica; los costos indicados son estimaciones, no facturas.

Los gráficos vectoriales y sus versiones PNG están en `figuras/`. Para regenerarlos a partir de los recibos del proyecto, ejecuta `python3 generar_graficos.py` desde esta carpeta y vuelve a compilar el documento.
