# Implementación propuesta en Azure y estimación de costos entre nubes

Fecha de investigación y tarifas: 9 de noviembre de 2026. **Azure es una propuesta teórica:** no se consultó su suscripción, no se crearon recursos ni se ejecutaron trabajos. Los valores de AWS y GCP proceden de los recibos de los experimentos; los costos monetarios indicados son estimaciones de tarifa pública, salvo que se señale una observación de créditos. Ninguno es una factura desglosada.

## 1. Referencia común para la comparación

El proyecto clasifica créditos. La clase positiva es **incumplimiento (`Pago_atiempo=0`)**. Los datos contienen 10.763 filas y el TEST cronológico tiene 3.229 filas, de las cuales 108 son incumplimientos. Para AutoML se reservan las particiones anteriores al TEST: TRAIN 6.027 y VALIDATE 1.507. Los archivos preparados, su orden y las huellas se conservan en `output/cloud-data-gcp/manifest.json` y `output/aws-credit/autopilot-data/manifest.json`.

En el modelo personalizado se emplean los datos originales, la validación temporal y la calibración ya implementadas en el repositorio. Para AutoML se usarían las mismas variables y particiones preprocesadas de GCP y AWS, conservando el TEST fuera de la selección. Este TEST ya se observó durante análisis previos; no constituye una validación externa nueva.

## 2. Cómo se implementaría en Azure

### Infraestructura y datos

1. En una suscripción con saldo y cuota, preparar un grupo de recursos y un workspace de **Azure Machine Learning**. Asociar almacenamiento Blob para datos y artefactos, Key Vault, Application Insights y, si se requieren imágenes propias, Azure Container Registry. Usar identidades administradas y Azure RBAC para restringir lectura, ejecución y publicación. La infraestructura puede describirse con Bicep o Terraform; no se requiere un clúster de Kubernetes para esta demostración.
2. Registrar en Blob/MLTable los archivos TRAIN y VALIDATE idénticos a los usados en GCP y AWS. Conservar TEST por separado, con una copia de sus etiquetas para evaluación. Verificar número de filas, orden de columnas y SHA-256 antes de ejecutar. No incluir `data_split`, identificadores ni la variable objetivo entre los predictores.
3. Usar un clúster de cómputo administrado con **mínimo 0 y máximo 1 nodo**, con escala a cero tras la inactividad. Como punto de partida para un cálculo económico se usa Linux `Standard_D2s_v5` (2 vCPU, 8 GiB); se debe confirmar disponibilidad, cuota y memoria suficiente antes de usarlo. Una alternativa de 4 vCPU y 16 GiB es `Standard_D4s_v5`. No se solicita GPU. El tiempo de preparación de imagen y el intervalo antes de escala a cero pueden agregar consumo. [Clúster de Azure ML](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-attach-compute-cluster?view=azureml-api-2); [especificaciones Dsv5](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/dsv5-series).

### Pipeline personalizado

Adaptar el punto de entrada existente para leer el CSV desde una entrada de Azure ML y escribir resultados en una salida del job. Empaquetar el código y las versiones de Python/bibliotecas en una imagen fijada por digest o en un entorno registrado. El pipeline podría tener componentes de verificación de datos, entrenamiento/evaluación y publicación de métricas, reutilizando en lo posible el contenedor y la configuración del pipeline Python. El código actual de Vertex descarga desde `gs://` y utiliza rutas de contenedor propias, por lo que necesitaría un adaptador de entrada y salida para Azure; no se afirma que funcione sin cambios.

Conservar los hashes del dataset y TEST, parámetros, semillas, predicciones, modelo y métricas. Comparar accuracy, precisión, recall, F1, ROC-AUC, average precision y TP/TN/FP/FN con la clase 0 positiva. Registrar el modelo solo después de evaluar los resultados. Azure ML permite definir componentes y pipelines con SDK v2 o YAML/CLI; Jenkins, GitHub Actions o Azure DevOps podrían disparar el flujo y aplicar una aprobación antes de registrar o desplegar. Esto es un diseño propuesto, no una integración probada. [Azure ML pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines?view=azureml-api-2), [Azure DevOps MLOps](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-setup-mlops-azureml).

### AutoML

1. Crear dos activos **MLTable** independientes para TRAIN y VALIDATE, con el mismo esquema y `Pago_atiempo` como objetivo. Proporcionar ambos explícitamente: si se omite VALIDATE, Azure ML aplica una división o validación cruzada automática que no preserva necesariamente el corte temporal. El TEST se conserva aparte y se evalúa solo después de elegir el modelo. [Entradas y pipeline AutoML](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-configure-auto-train?view=azureml-api-2).
2. Configurar clasificación binaria, un único nodo y un ensayo concurrente; como demostración limitada, hasta dos ensayos, 15 minutos por ensayo, 60 minutos de experimento y terminación temprana. Son parámetros propuestos: podrían no dejar tiempo para completar un modelo y **no garantizan un tope monetario**, pues el almacenamiento, la preparación y el tiempo de recursos asignados pueden generar cargos adicionales. [Límites de AutoML](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-automated-ml-for-ml-models?view=azureml-api-2).
3. Para comparar con GCP, `average_precision_score_weighted` es una opción de objetivo relacionada con precisión-recall, pero pondera ambas clases y **no es equivalente** al PR-AUC de la clase 0 de GCP. Para comparar el objetivo con AWS, se podría elegir `AUC_weighted`, aclarando también su agregación. El SDK v2 documenta estas opciones como métricas principales; el mejor modelo puede variar según la elección. [Métricas principales admitidas](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.automl.classificationprimarymetrics?view=azure-python).
4. Evaluar el mejor modelo con las mismas 3.229 filas de TEST y definir la clase positiva como `0`. Obtener probabilidades por clase, calcular métricas al umbral 0,5 y presentar TP (verdaderos positivos), TN (verdaderos negativos), FP (falsos positivos) y FN (falsos negativos). Mantener por separado la *average precision* de sklearn y el PR-AUC nativo cuando su cálculo difiera. Azure documenta `positive_label` para las métricas binarias y permite evaluarlas en Studio. La función de test automático mediante dataset independiente se documenta como vista previa en la API; una evaluación posterior por componente es una alternativa a comprobar cuando haya suscripción. [Métricas y clase positiva](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-understand-automated-ml), [API de clasificación](https://learn.microsoft.com/en-us/python/api/azure-ai-ml/azure.ai.ml.automl.classificationjob).

El registro de modelo, el monitoreo y el despliegue continuo podrían usar Azure ML Model Registry, Azure Monitor y Azure Policy. Para inferencia de una sola prueba, un componente o endpoint batch evita mantener un endpoint en línea; para uso continuo, un endpoint administrado necesita cómputo aprovisionado y red. La disponibilidad de estas funciones no demuestra por sí sola cumplimiento normativo. [Monitoreo de modelos](https://learn.microsoft.com/en-us/azure/machine-learning/concept-model-monitoring?view=azureml-api-2), [endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/concept-endpoints?view=azureml-api-2), [Azure Policy](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-integrate-azure-policy?view=azureml-api-2).

## 3. Costos de los experimentos personalizados

USD, tarifas públicas sin aplicar créditos, descuentos, impuestos ni precios contractuales. Las regiones no son idénticas: AWS `us-east-1`, GCP `us-central1` y Azure teórico `eastus`. El cómputo y tiempo medidos son intervalos distintos; ninguna cifra siguiente incluye todo el costo de implementación.

| Concepto | AWS: observado y estimado | GCP: observado y estimado | Azure: escenario teórico |
|---|---|---|---|
| Servicio | SageMaker Pipelines + Processing | Vertex AI Pipelines + CustomJob | Azure ML pipeline + componente command |
| CPU / RAM | `ml.m5.large`, 2 vCPU / 8 GiB | `e2-highmem-2`, 2 vCPU / 16 GiB | `D2s_v5`, 2 vCPU / 8 GiB, sujeto a disponibilidad |
| Job y duración | Processing: 158,907 s; pipeline ≈304 s | Worker: 212 s; pipeline ≈10 min | No ejecutado; hipótesis de 212 s de VM aprovisionada |
| Cómputo | 158,907/3600 × USD 0,115/h = **USD 0,0051** | 212/3600 × USD 0,103959618/h = **USD 0,0061** | 212/3600 × USD 0,096/h = **USD 0,0057** hipotéticos |
| Orquestación | AWS indica que Pipelines no tiene cargo adicional; se cobran servicios usados | Tarifa orientativa USD 0,03 por ejecución: ≈USD 0,0361 por cómputo del worker más una ejecución; el registro previo estimó ≈USD 0,0961 al contar conservadoramente los tres envíos | Azure ML no tiene cargo adicional por el servicio; se cobran VM y servicios auxiliares |
| Fuera del cálculo | Volumen, S3, ECR, logs, solicitudes y otros | SSD temporal, GCS, imágenes, logs y otros | Disco/Blob, registry, logs, red, preparación y tiempo de escala a cero |

Fuentes: [tarifas SageMaker](https://aws.amazon.com/sagemaker/ai/pricing/), [preguntas frecuentes de Pipelines](https://aws.amazon.com/sagemaker/ai/faqs/), [tarifas de Vertex Pipelines](https://cloud.google.com/gemini-enterprise-agent-platform/tabular-workflows-pricing), [tarifas de Azure ML](https://azure.microsoft.com/en-us/pricing/details/machine-learning/). Tarifas y duraciones de las ejecuciones realizadas: `output/aws-credit/aws-price.json`, `output/aws-credit/processing-job.json`, `output/gcp-receipts/cost-estimate.json`. Se contaron las dos ejecuciones fallidas de GCP conservadoramente; no se verificó su cargo individual. El tiempo de máquina facturado puede diferir del intervalo observado.

## 4. Costos AutoML

| Concepto | AWS Autopilot | GCP Vertex AutoML clásico | Azure ML AutoML: ejemplo teórico |
|---|---|---|---|
| Ejecución | HPO completado, 2 candidatos; 26 min 6 s de pared | Completado; 2 h 35 min 28 s de pared | No ejecutado; 2 ensayos y hasta 60 min de experimento propuestos |
| Cómputo | ≈**USD 0,5703** para el HPO exitoso, calculado por cada job; el intento de ensemble detenido añade ≈**USD 1,2003**. Total ambos ≈**USD 1,7706** | Presupuesto configurado de 1 hora-nodo a tarifa observada de USD 21,252/hora-nodo: **hasta ≈USD 21,25 de entrenamiento** para esa configuración; no es un cargo final desglosado | Si un solo `D2s_v5` permaneciera aprovisionado exactamente 1 hora: **USD 0,096** de VM. Dos horas: **USD 0,192**. Es aritmética de ejemplo, no predicción de runtime ni cotización completa |
| Otros gastos | Volúmenes, S3, ECR, CloudWatch y otros; inferencia final local debido a restricción del lab | Almacenamiento y servicios adicionales; no se ejecutó inferencia batch | Blob, discos, registry, logs, red y cómputo por arranque/escala; una ejecución más larga o más nodos aumenta el costo |
| Facturación observada | Cost Explorer mostró USD 0 estimados, incompatible con el gasto previo aproximado reportado; el saldo no se confirmó desde la API | El panel de créditos mostró USD 28,01 restantes de USD 50; USD 21,99 consumidos desde la concesión por servicios elegibles de toda la cuenta, no exclusivamente este job | No hay observación ni cargos porque no se ejecutó |

La duración de pared de GCP no equivale a horas-nodo facturables. Tampoco existe una equivalencia directa entre una hora-nodo de Vertex, una hora de Autopilot y una hora de VM Azure. La comparación de calidad también cambia por objetivos, algoritmos, búsqueda, validación interna y recursos. `output/aws-credit/autopilot-compute-cost-estimate.json` desglosa los jobs y conserva las tarifas usadas; `output/gcp-receipts/billing-after-automl.json` conserva la observación de créditos. Las tarifas de Google deben revisarse en la [página oficial](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing); el valor USD 21,252 es el registrado para el entrenamiento tabular clásico de este experimento.

## Resultados de clasificación disponibles

Las cifras son del mismo TEST, con `Pago_atiempo=0` como clase positiva. Azure no tiene resultados medidos. Los modelos personalizados utilizan un umbral calibrado en validación anterior al TEST; los dos AutoML se comparan al umbral 0,5.

| Métrica | AWS personalizado | GCP personalizado | AWS AutoML | GCP AutoML | Azure |
|---|---:|---:|---:|---:|---|
| Accuracy | 0,8250 | 0,8250 | 0,6308 | 0,9625 | No ejecutado |
| Precisión clase 0 | 0,0681 | 0,0681 | 0,0498 | 0,2593 | No ejecutado |
| Recall clase 0 | 0,3333 | 0,3333 | 0,5556 | 0,0648 | No ejecutado |
| F1 clase 0 | 0,1130 | 0,1130 | 0,0915 | 0,1037 | No ejecutado |
| ROC-AUC clase 0 | 0,6573 | 0,6573 | 0,6477 | 0,6542 | No ejecutado |

La inferencia del AutoML AWS se realizó localmente con sus contenedores oficiales porque el laboratorio denegó Batch Transform; la evaluación GCP es nativa. Conservar esta diferencia y las limitaciones de la sección anterior al interpretar el resultado.

## 5. Almacenamiento y despliegue

Ejemplo de **1 unidad de almacenamiento durante un mes**, primer tramo, datos en reposo. Las clases y garantías de replicación no son idénticas; se excluyen solicitudes, transferencias, versiones, retención e impuestos.

| Servicio y región | Tarifa pública aproximada |
|---|---:|
| S3 Standard, `us-east-1`, primeros 50 TB | USD 0,023 por GB-mes según el catálogo de AWS |
| Cloud Storage Standard regional, `us-central1` | USD 0,000027397 por GiB-hora; ≈USD 0,020 por GiB para 730 h |
| Azure Blob Storage Hot LRS, `eastus`, primer tramo | USD 0,0208 por GB-mes según Azure Retail Prices |

S3 Standard replica en varias zonas de disponibilidad; Azure LRS mantiene copias localmente dentro de un centro de datos y Cloud Storage regional tiene su propia política regional. No deben tratarse como niveles idénticos de resiliencia. [S3](https://aws.amazon.com/s3/pricing/), [Cloud Storage](https://cloud.google.com/storage/pricing), [Azure Blob](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/). Los datos de respaldo en Azure y AWS están en `output/cloud-comparison/`.

No hubo endpoint en línea en ninguno de los dos experimentos reales, por lo que **no hay costo de despliegue medido**. Como referencia puramente aritmética, una VM Azure `D2s_v5` a USD 0,096/h durante 24 h cuesta USD 2,304 de cómputo; un endpoint real podría requerir una SKU distinta y añade servicios y red. Una predicción batch requiere una instancia durante su ejecución. La restricción del Learner Lab impidió medir Batch Transform en AWS. [Precio Azure ML](https://azure.microsoft.com/en-us/pricing/details/machine-learning/), [costos de endpoints](https://learn.microsoft.com/en-us/azure/machine-learning/concept-endpoints-online?view=azureml-api-2).

## 6. Lectura para la comparación

- **Configuración e interfaz:** GCP se ejecutó mediante consola; AWS mediante IaC/CLI y sus contenedores de inferencia. Azure ML Studio y SDK/CLI están documentados pero no se probaron. No se midió objetivamente la curva de aprendizaje ni el tiempo humano total desde cero.
- **Automatización:** los tres admiten definir pipelines y conectarlos a CI/CD; solo se probó la implementación GCP/Jenkins y el pipeline personalizado de AWS. Autopilot se lanzó como job independiente, no como etapa de CI/CD.
- **Recursos y tiempo:** AWS HPO usa varios jobs e instancias, no una sola VM equivalente a las del pipeline personalizado. GCP AutoML y AWS AutoML son un solo entrenamiento cada uno; no se midió variación entre reentrenamientos en ninguna plataforma. Azure no tiene valores de runtime ni CPU utilizados observados.
- **Seguridad y equipos:** Azure RBAC/Entra ID, identidades administradas, Policy, registros de auditoría y workspaces permiten separar funciones; AWS ofrece IAM/CloudTrail y GCP IAM/Audit Logs. El `LabRole` de AWS utilizado es amplio y no demuestra mínimo privilegio. La conformidad regulatoria depende de controles, configuración, región y auditoría concretos.
- **Presupuesto:** las tarifas de ejemplo no fijan un límite de gasto. Revisar cuota y saldo del laboratorio, límites de concurrencia y tiempo, monitoreo, almacenamiento persistente y cobros tardíos antes de una ejecución futura.

## Actualización: búsqueda de AWS ampliada

Se ejecutó además un Autopilot HPO de **10 candidatos**, completado en **30 min 33 s**. El mejor ROC-AUC de validación fue **0,685440**, frente a 0,679790 con dos candidatos. Al evaluar el candidato seleccionado sobre el mismo TEST y con umbral 0,5 se obtuvo accuracy **0,695881**, precisión **0,054990**, recall **0,500000**, F1 **0,099083** y ROC-AUC **0,627683**; TP=54, TN=2193, FP=928, FN=54. La inferencia se ejecutó localmente porque el laboratorio denegó Batch Transform. Una búsqueda mayor elevó el valor de validación, pero no el ROC-AUC de este TEST; las comparaciones son exploratorias porque el TEST se ha consultado repetidamente.

El cómputo estimado de la nueva búsqueda fue **USD 1,9199**, además de los ≈USD 1,7706 de los dos intentos previos. El total de los tres es ≈**USD 3,6905** de cómputo a tarifa pública, sin almacenamiento ni otros cargos y sin factura atribuida. Recibos: `output/aws-credit/hpo10/compute-cost-estimate.json`, `completed.json`, `candidates.json` y `test-metrics.json`. Las cifras AWS de la tabla anterior corresponden a la ejecución de dos candidatos, no a esta nueva búsqueda.
