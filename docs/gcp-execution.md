# Ejecución de GCP desde el dashboard

Inicio: 8 de noviembre de 2026. El usuario autorizó continuar la fase GCP y completó el inicio de sesión interactivo en la sesión persistente Playwright `semester-gcp`. Por instrucción expresa del usuario, **la consola se mantiene en japonés**; la documentación se escribe en español.

Cuenta comprobada en el menú del navegador: `contact@02labs.me`, administrada por `02labs.me`. Proyecto seleccionado: `novabank-riesgo-ml-dev`, ID `nb-risk-ml-dev-99d0`, número `727006212991`. La UI presenta Vertex AI como Agent Platform; el identificador API continúa siendo `aiplatform.googleapis.com`.

## Capturas iniciales

- [Plataforma y proyecto](../output/playwright/gcp/01-risk-project-overview-ja.png).
- [Información del proyecto](../output/playwright/gcp/02-project-dashboard-ja.png).
- [Cuenta y organización](../output/playwright/gcp/03-account-and-organization-ja.png).

El índice `output/playwright/gcp/index.json` conserva fecha UTC, URL sin parámetros de autenticación, acción, resultado y SHA-256. Estas capturas acreditan acceso/configuración; no se presentan como prueba de entrenamiento completado. El proyecto de Jenkins y sus tareas de retiro no se modifican por esta fase.

## Datos, API y preparación en consola

Se habilitó `aiplatform.googleapis.com` desde el dashboard (capturas 04–05). Se creó el bucket regional privado `nb-risk-ml-dev-99d0-credit-lab-20261108` en `us-central1`, Standard, acceso uniforme y prevención de acceso público. Se mantuvo el borrado recuperable de 7 días. Se subieron cuatro archivos: `raw.csv`, `automl.csv`, `holdout-features.csv` y `manifest.json` (capturas 06–11). Las etiquetas del holdout quedaron locales.

Se creó el dataset tabular `credit-classification-temporal-20261108`, ID `2799060011056103424` (capturas 12–13). El campo de importación incluye el prefijo `gs://`: el primer intento duplicó ese prefijo y fue rechazado (14); se corrigió introduciendo `bucket/automl.csv` (15). La fuente quedó asociada (16) y se solicitó generar estadísticas (17). Ese procesamiento no equivale a entrenar un modelo.

La exportación realmente subida es `output/cloud-data-gcp`; usa los valores oficiales `TRAIN`, `VALIDATE`, `TEST`, con 6.027, 1.507 y 3.229 filas. La huella de dataset y holdout permanece idéntica a la comparación local.

## Decisión de presupuesto y AutoML

El usuario indicó USD50 de créditos y un máximo aproximado de USD15 para esta demostración. Se revisó AutoML sobre Pipelines (18), que requiere Dataflow y factura infraestructura adicional. No se envió ese flujo. En la opción clásica se eligió `Pago_atiempo`, división manual `data_split` (19), y se probó un presupuesto de 0,7 horas-nodo sin enviarlo. El formulario lo rechazó: exige un número entre 1 y 72 (20). Una hora-nodo a tarifa pública estándar cuesta USD21,252, fuera del límite. Se canceló el formulario; **AutoML no se entrenó**. No hay métricas AutoML que comparar ni endpoint de inferencia creado.

Fuentes: [tarifas de entrenamiento](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing), [tarifas de Tabular Workflows](https://cloud.google.com/gemini-enterprise-agent-platform/tabular-workflows-pricing). El ejemplo público del workflow suma USD27,03 sin destilación; no representa una cotización de este dataset.

## Runtime personalizado

La infraestructura auxiliar se preparó con `cloud/prepare_runtime.py`; el script no envía entrenamientos. Se verificaron organización y número de proyecto del bucket mediante metadatos. Se creó el repositorio Docker `credit-semester-training` y la cuenta `credit-semester-pipeline@nb-risk-ml-dev-99d0.iam.gserviceaccount.com`. Recibe Vertex AI User en el proyecto, acceso a objetos/metadatos únicamente en el bucket del ejercicio y lectura del repositorio de imágenes. La cuenta del usuario puede actuar como esa identidad; no se generaron claves.

La imagen está fijada por digest y la especificación real se conserva en `output/credit-pipeline-dashboard.json`; el recibo de preparación es `output/training-runtime.json`. Se configuraron 2 CPU, memoria 8G, caché desactivada, cero reintentos y alarma de 600 segundos para el cuerpo de entrenamiento. La alarma limita el código de entrenamiento; no es un límite monetario ni incluye espera/provisión del servicio. El envío se realiza desde el dashboard.

### Parámetros y comprobación de permisos

Se cargó la especificación en **Pipelines → Crear ejecución → Subir archivo**, nombre `credit-cpu-demo-20261108`, región us-central1, una sola ejecución y SA dedicada (22). Se configuraron las dos huellas, `input_uri` y el directorio `gs://nb-risk-ml-dev-99d0-credit-lab-20261108/pipeline-root` (23), fallo inmediato y la política de caché de la especificación (desactivada).

El primer clic en Enviar detuvo el flujo en una comprobación previa (24) que pedía `storage.objects.get` y `storage.objects.create`. Se comprobó la política real del bucket y la definición oficial de `roles/storage.objectUser`: ambas operaciones ya estaban concedidas a la SA en ese bucket. Los recibos están en `output/gcp-receipts/bucket-iam.json` y `storage-object-user-role.json`. La UI advierte que sus diagnósticos pueden ser inexactos. Se utilizó su interruptor para omitir esa comprobación y reintentar, manteniendo los permisos acotados al bucket. Esto no garantiza el resultado del entrenamiento; se registra por separado el estado real del job.

### Primer envío y corrección del acceso a la imagen

El dashboard sí creó `projects/727006212991/locations/us-central1/pipelineJobs/credit-cpu-demo-20261108`, pero finalizó inmediatamente con `PIPELINE_STATE_FAILED`: al agente de servicio serverless `service-727006212991@gcp-sa-aiplatform-cc.iam.gserviceaccount.com` le faltaba acceso al repositorio Artifact Registry (25). No se presenta como entrenamiento completado. El recibo íntegro es `output/gcp-receipts/first-run-failure.json`.

Se añadió exclusivamente `roles/artifactregistry.reader` a ese agente en `credit-semester-training`; el permiso de la SA de ejecución no bastaba porque el plano de control descarga la imagen con otra identidad. Se conservó `image-repository-iam.json` y se clonó el job mediante el enlace del dashboard, con nombre `credit-cpu-demo-20261108-r2`. Esta segunda ejecución conserva imagen, parámetros y partición.

### Ejecución activa confirmada

El segundo envío falló igualmente antes de crear workers. La herramienta oficial IAM Policy Troubleshooter confirmó `CAN_ACCESS` al repositorio para el agente, sin una política de denegación (`image-access-troubleshoot.json`). Se habilitaron Policy Troubleshooter y Cloud Logging para diagnosticar y conservar logs. Tras esperar mientras se verificaban permisos y metadatos, el tercer envío desde la consola, `credit-cpu-demo-20261108-r3`, pasó a `PIPELINE_STATE_RUNNING` el **2026-11-08T09:52:33.424943Z** (26–28). La recuperación es compatible con propagación de permisos/identidades recién creados; esa causa no está demostrada de forma aislada.

El servicio creó el CustomJob `1394998308224630784`: una réplica `e2-highmem-2`, disco temporal pd-ssd de 100 GB, sin acelerador, SA dedicada y `disableRetries=true`. La especificación solicita 2 CPU y memoria 8G; Vertex selecciona la máquina compatible, que ofrece 16 GiB. El estado RUNNING del pipeline corresponde a la orquestación; se verifica por separado cuándo inicia y finaliza el worker. Los recibos son `output/gcp-receipts/pipelineJobs.json` y `customJobs.json`.

## Facturación observada en el navegador

Cuenta `Billing Account for Education`, `01ADCB-D56D56-B45DCC`, USD. En el reporte con todos los 6 proyectos seleccionados y período **1–8 de noviembre de 2026**, el dashboard mostró **USD0,00 netos**, incluyendo **USD0,06 de ahorros/créditos** (30). La página de créditos mostró la promoción **Ciencia de datos en producción**, valor inicial **USD50,00**, saldo **USD49,86**, vigente hasta el **6 de octubre de 2027** (31). El saldo implica USD0,14 utilizados desde la concesión; no tiene el mismo período que el reporte mensual.

Son valores reportados al momento de la consulta, no una liquidación final: el consumo reciente de Jenkins y del entrenamiento puede aparecer con retraso. No se interpreta USD0,00 como ausencia de consumo. `billing-observation.json` registra el alcance y las limitaciones. La estimación de lista de Jenkins y su retiro programado siguen siendo independientes de estos importes observados.

### Entrenamiento del worker

El CustomJob pasó a `JOB_STATE_RUNNING` con inicio **2026-11-08T09:58:45Z** (32), después de la provisión inicial. Los logs reales muestran la búsqueda de regresión logística, árbol y random forest con puntuaciones F1 temporales (33). Estas puntuaciones son de validación; no se confunden con el F1 final del holdout. La duración mostrada por el nodo incluye la espera de provisión y no equivale al tiempo puro de cómputo.

## Finalización y resultados verificados

El worker finalizó **SUCCEEDED a las 2026-11-08T10:02:17Z**, 212 segundos desde su inicio. El pipeline terminó **PIPELINE_STATE_SUCCEEDED a las 10:02:37.221247Z**, aproximadamente 10 minutos de orquestación incluyendo provisión (34). Se abrió el artefacto `metrics` en ML Metadata y se capturaron los valores reales en el dashboard japonés (35). El artefacto `results` contiene modelo, métricas, predicciones, tablas y figuras.

Se descargaron los resultados por lectura de Cloud Storage a `output/vertex-custom`; las huellas de cada archivo están en `downloaded-artifacts.json`. La descarga no envía un nuevo entrenamiento. El estado `complete` y el modelo seleccionado `random_forest` coinciden con los recibos de GCP. Se verificaron las dos huellas de datos y diferencias menores a 1e-12 en cuatro métricas clave frente al baseline local.

| Métrica del holdout de 3.229 filas | Python local | Vertex CPU |
|---|---:|---:|
| Accuracy | 0,825023 | 0,825023 |
| F1 incumplimiento | 0,113030 | 0,113030 |
| Recall incumplimiento | 0,333333 | 0,333333 |
| ROC-AUC | 0,657321 | 0,657321 |
| Average Precision | 0,099415 | 0,099415 |
| Desviación F1 entre folds temporales | 0,029162 | 0,029162 |
| Desviación F1 entre semillas | 0,011031 | 0,011031 |

Matriz de confusión (filas/columnas: incumplimiento, pago a tiempo): `[[36,72],[493,2628]]`. Se detectaron 36 de 108 incumplimientos y se omitieron 72. La coincidencia acredita reproducción del protocolo en cloud, no mejora de la calidad predictiva ni validación externa. La variación entre folds/semillas procede del protocolo dentro del entrenamiento; no son tres jobs cloud independientes. No se comparan métricas AutoML porque no se ejecutó.

Comparación reproducible, sin enviar jobs:

```bash
python -m cloud.compare local --run output/vertex-custom --output output/vertex-custom-normalized.json --origin vertex-custom
python -m cloud.compare report --inputs output/python-local.json output/vertex-custom-normalized.json --output output/comparison-gcp --language es
```

## Estimación de costo de esta demostración

Una sola réplica CPU completó el entrenamiento; los dos primeros envíos fallaron antes de crear workers. A tarifa pública USD0,103959618/h para e2-highmem-2, 212 segundos equivalen a unos USD0,0061. Contando conservadoramente USD0,03 por cada uno de los tres pipelines creados, el subtotal orientativo es **USD0,0961**, más SSD temporal de 100 GB, almacenamiento y operaciones. Se espera un costo de entrenamiento del orden de centavos, muy inferior a USD15; **no es una factura ni un tope monetario garantizado**. Jenkins se estima por separado. `cost-estimate.json` conserva fórmula y exclusiones.

Al terminar no quedan workers de entrenamiento activos ni endpoints creados por esta demostración. Se conservan el dataset, el bucket privado, el modelo como artefacto, la imagen y la SA para trazabilidad; su almacenamiento puede seguir generando cargos pequeños. El retiro programado de Jenkins no incluye estos recursos de riesgo.

Para la gráfica se calculan intervalos bootstrap condicionales a partir de las predicciones cloud descargadas. `vertex-custom-normalized.json` es un derivado de análisis, no una sustitución del `comparison.json` original; se verificó que conserva sus huellas y métricas. ML Metadata también coincide con la exportación (`metrics-artifact.json`).
