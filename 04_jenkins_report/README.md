# Reporte de resultados en español - LaTeX

Documento final: `../output/pdf/Informe_unificado_Jenkins_GCP_ES.pdf`.
El ZIP del mismo nombre contiene el PDF, las fuentes y las evidencias.
`Informe_unificado_Jenkins_GCP_ES_LaTeX_fuentes.zip` permite compilar el informe
por separado.

## Edición y compilación

Las fuentes editables son `latex/main.tex` (título, autor y estructura),
`latex/contenido.tex` (texto, tablas y figuras) y `latex/style.tex` (formato).
**Los archivos LaTeX son la versión editorial principal.**

Desde `latex/`:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Para actualizar el PDF de entrega y ambos ZIP desde la raíz del repositorio:

```bash
python3 04_jenkins_report/build_report.py
```

Este comando compila y empaqueta el LaTeX existente; no regenera ni sobrescribe
el texto editado. Las dependencias están en `latex/README.md`.

## Organización del informe

El informe presenta resultados de Jenkins, desempeño de Python, entrenamiento
en GCP, comparación de modelos, estabilidad y conclusiones. Las capturas de
configuración, ejecución y validación se integran en las secciones correspondientes.
No se incluye un anexo ni una sección de costos. Se conservan 33 imágenes.

`informe.json` y `INFORME_RESULTADOS_ES.md` son exportaciones estructurada y
legible de la revisión editorial. Si se vuelve a editar directamente el `.tex`,
esas exportaciones deben sincronizarse por separado. `latex/generate.py` es el
conversor de la versión anterior; no debe usarse para regenerar esta edición.

Las imágenes no se modificaron; `evidencias.json` conserva procedencia y hashes.
La plantilla Tufte original y su licencia se mantienen en `latex/template/`.
La evidencia y los recibos reflejan el corte del 9 de noviembre de 2026.
