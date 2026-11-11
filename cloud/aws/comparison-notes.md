# Datos para la comparación entre AWS, GCP y Azure

Fecha de observación: 9 de noviembre de 2026. Este documento reúne datos y fuentes para preparar la comparación; no sustituye la factura ni afirma que las capacidades teóricas se hayan probado. Azure es exclusivamente teórico.

## Alcance comparable

| Aspecto | AWS | GCP | Azure (teórico) |
|---|---|---|---|
| Flujo personalizado | SageMaker Pipelines con un paso Processing que ejecuta el código Python existente | Vertex AI Pipelines y CustomJob | Azure Machine Learning pipelines y trabajos de componentes |
| AutoML tabular | SageMaker Autopilot HPO; completado con dos candidatos y TEST evaluado localmente | Vertex AI AutoML; una ejecución completada | Azure Machine Learning AutoML; **no ejecutado** |
| Datos | Mismo archivo y verificación criptográfica del holdout temporal; 10.763 registros y TEST de 3.229 | Mismo archivo y holdout | Sin ejecución |
| Recursos | 1 `ml.m5.large`, 2 vCPU, 8 GiB, sin GPU; volumen 10 GB | 1 `e2-highmem-2`, 2 vCPU, 16 GiB, sin GPU; disco temporal 100 GB | Dependen de la VM elegida; no medidos |
| Despliegue de inferencia | Sin endpoint | Sin endpoint en el experimento de entrenamiento | Sin despliegue |

El job de AWS usa **Processing** para entrenar y evaluar dentro del contenedor: no es un trabajo nativo Training ni la ejecución de Autopilot, que se documenta por separado. Una ejecución por plataforma no permite comparar estabilidad entre reentrenamientos. Capacidad provisionada no equivale a utilización real: no se midieron porcentajes de CPU ni picos de memoria.

## Tiempos y facilidad de configuración

En AWS se reutilizó el código y la imagen construida para GCP; se definieron recursos mediante CloudFormation y el DAG en JSON usando CLI. La configuración incluye S3, ECR, el rol preexistente del laboratorio y SageMaker. El trabajo real de adaptación es menor por la reutilización; no es un tiempo desde cero comparable con GCP. La implementación se inició antes de las 08:23 UTC y el pipeline se lanzó a las 08:26:23 UTC; la hora inicial exacta y el trabajo anterior de construcción de la imagen no se cronometraron. El pipeline terminó a las 08:31:27 UTC: aproximadamente 304 s de pared. El job Processing registró 158,9 s (08:27:11–08:29:50 UTC) y el programa informó 108,57 s; cada tiempo mide un intervalo distinto. Los recibos están en `output/aws-credit/`.

En GCP el CustomJob ejecutó 212 s desde el inicio hasta el fin del worker; el pipeline completado tardó aproximadamente 10 minutos incluyendo provisión. Hubo dos envíos previos fallidos por acceso a la imagen, y su tiempo debe incluirse al evaluar la implementación completa. AutoML tardó 2 h 35 min 28 s de pared, con presupuesto de una hora-nodo; son unidades distintas. Ver `docs/gcp-execution.md`. No se cronometró todo el trabajo humano desde cero de forma comparable. No se ha inspeccionado la interfaz AWS para este experimento y no hay medida observada de aprendizaje ni configuración en Azure.

## Resultados de clasificación observados

| Métrica en el mismo TEST | AWS personalizado | GCP personalizado | GCP AutoML clase 0 |
|---|---:|---:|---:|
| Accuracy | 0,8250 | 0,8250 | 0,9625 |
| Precisión de incumplimiento | 0,0681 | 0,0681 | 0,2593 |
| Recall de incumplimiento | 0,3333 | 0,3333 | 0,0648 |
| F1 de incumplimiento | 0,1130 | 0,1130 | 0,1037 |
| ROC-AUC de incumplimiento | 0,6573 | 0,6573 | 0,6542 |

AWS reprodujo el mismo random forest y los hashes del conjunto y TEST de GCP; las métricas coinciden dentro de 1e-12. En AWS: TP=36, TN=2628, FP=493, FN=72. El umbral personalizado se calibró antes de TEST; AutoML usa 0,5. Esto y la diferencia de enfoques impiden atribuir las diferencias solo al proveedor. La validación temporal y las tres semillas del mismo entrenamiento no sustituyen reentrenamientos independientes en cada nube.

## Precios y límites de la comparación

- AWS Pipelines no tiene un cargo adicional de orquestación según las [preguntas frecuentes oficiales](https://aws.amazon.com/sagemaker/ai/faqs/); se cobran los recursos usados. [SageMaker AI precios](https://aws.amazon.com/sagemaker/ai/pricing/) detalla el cómputo por tipo de tarea, discos y servicios relacionados. El runtime limitado a 600 s no es un tope monetario de cuenta ni incluye necesariamente todos los servicios. El [catálogo público de AWS para us-east-1](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonSageMaker/current/us-east-1/index.json) indica USD 0,115/h para `USE1-Processing:ml.m5.large` (vigencia publicada 1/11/2026). Los 158,907 s registrados equivalen a unos USD 0,0051 de cómputo, antes de volumen, S3, ECR, logs e impuestos. No es el importe facturado; recibo `output/aws-credit/aws-price.json`.
- Vertex Pipelines figura a USD 0,03 por ejecución en el [ejemplo oficial de precios de flujos tabulares](https://cloud.google.com/gemini-enterprise-agent-platform/tabular-workflows-pricing). Para el CustomJob de GCP se estimaron USD 0,0061 de cómputo por 212 s, más orquestación, disco y almacenamiento; es una estimación, no factura. El AutoML clásico se configuró con un presupuesto de 1 hora-nodo estimado en USD 21,25; el consumo de la cuenta de créditos observado fue USD 21,99 y no está atribuido íntegramente al job.
- Azure Machine Learning no añade una tarifa por uso del servicio; se cobran VM y servicios como Blob Storage, Key Vault, Container Registry y Application Insights ([precios oficiales](https://azure.microsoft.com/en-us/pricing/details/machine-learning/)). La [API pública de precios de Azure](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) devolvió USD 0,096/h para D2 v3 Linux de 2 vCPU y 8 GiB en East US, pago por uso; 158,907 s hipotéticos equivalen a USD 0,0042 solo de cómputo. Es un escenario teórico, no una ejecución ni precio contractual; recibo `output/aws-credit/azure-retail-price.json`.
- Para comparar AutoML hay que sumar los recursos de búsqueda, candidatos, preprocesamiento y almacenamiento. Una hora-nodo de Vertex no equivale a una hora de pared de Autopilot o de Azure AutoML; elegir región, hardware, duración, número de candidatos, operaciones y transferencias antes de cotizar. El costo de cómputo de Autopilot en AWS es una estimación detallada abajo; no hay factura atribuida ni costo medido de Azure.
- Almacenamiento equivalente: S3 Standard, Cloud Storage Standard regional y Blob Hot con redundancia comparable; comparar GB-mes, lecturas, escrituras, transferencia y retención, consultando las [tarifas S3](https://aws.amazon.com/s3/pricing/), [Cloud Storage](https://cloud.google.com/storage/pricing) y [Blob](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/). No asumir igual disponibilidad o redundancia por el nombre.
- Ningún proveedor desplegó un endpoint para este experimento. El costo real de inferencia permanece sin medir; estimarlo con el tamaño, número de instancias, horas activas y tráfico equivalentes.

La consulta AWS Cost Explorer del 1 al 9 de noviembre devolvió USD 0 estimados pese al gasto aproximado de USD 10 comunicado por el usuario; no demuestra que el saldo disponible sea USD 50. La API de precios de AWS denegó acceso. Confirmar el saldo en el panel de Learner Lab y conciliar facturación posterior.

## Capacidades para investigar

| Criterio | AWS | GCP | Azure |
|---|---|---|---|
| Interfaz | SageMaker Studio, Pipeline Designer y Canvas/Autopilot | Vertex AI Studio, Pipelines y AutoML | Azure ML Studio, diseñador y AutoML |
| CI/CD y automatización | API/CLI/SDK y Jenkins o CodePipeline; registro/aprobación mediante Model Registry | Vertex Pipelines/API con Jenkins o Cloud Build; Model Registry | Azure ML SDK/CLI con Azure DevOps o GitHub Actions; registro de modelos |
| Monitoreo | CloudWatch; SageMaker Model Monitor y Clarify | Cloud Logging/Monitoring; Vertex Model Monitoring | Azure Monitor y Azure ML model monitoring |
| Versiones y gobierno | SageMaker Model Registry, linaje, aprobación, IAM, CloudTrail | Vertex Model Registry, IAM, Cloud Audit Logs | Azure ML model registry/MLflow, Azure RBAC, Azure Policy y registros de auditoría |
| Equipos y roles | IAM y separación de cuentas/roles | IAM, proyectos y cuentas de servicio | Entra ID/RBAC, suscripciones, grupos y workspaces |

Estas son capacidades documentadas, no una evaluación práctica de todas ellas. El `LabRole` es compartido y amplio; no demuestra mínimo privilegio ni separación empresarial. La disponibilidad de una herramienta o certificación no demuestra cumplimiento normativo: depende de configuración, controles, región y proceso de auditoría.

Fuentes: [AWS Pipelines](https://docs.aws.amazon.com/sagemaker/latest/dg/pipelines-overview.html), [AWS Model Registry](https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry.html), [AWS gobernanza de ML](https://docs.aws.amazon.com/pdfs/whitepapers/latest/build-secure-enterprise-ml-platform/build-secure-enterprise-ml-platform.pdf), [GCP seguridad y linaje](https://cloud.google.com/architecture/framework/perspectives/ai-ml/security), [Azure pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/concept-ml-pipelines?view=azureml-api-2), [Azure MLOps](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-setup-mlops-azureml), [Azure Policy](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-integrate-azure-policy?view=azureml-api-2), [Azure model monitoring](https://learn.microsoft.com/en-us/azure/machine-learning/concept-model-monitoring?view=azureml-api-2).

## Recursos retenidos y uso observado

Al finalizar no había jobs Processing activos ni endpoints SageMaker en la cuenta. El bucket del ejercicio contenía 25 objetos con 3,9 MiB en total; ECR informó una imagen de aproximadamente 205 MB comprimidos, además de los manifiestos. Las políticas expiran objetos e imágenes después de siete días, pero no eliminan el bucket, repositorio ni definición del pipeline. Los logs descargados están en `output/aws-credit/log-events.json`. El grupo compartido `/aws/sagemaker/ProcessingJobs` tiene retención de siete días: al intentar restaurar la retención indefinida, la política de la organización denegó `logs:DeleteRetentionPolicy`. Esa configuración se aplica también a futuros jobs Processing en esta cuenta y región.

## Resultado de Autopilot de AWS

El intento inicial de ensamblado `credit-auto-temporal-20261109` lanzó diez jobs `ml.r5.16xlarge` simultáneos (64 vCPU y 512 GiB cada uno) y se detuvo por el riesgo para el presupuesto. Todos quedaron `Stopped`. La suma de sus tiempos registrados de instancia equivale a aproximadamente **USD 1,2003** de cómputo al precio público, sin incluir otros cargos. No produjo un modelo.

El segundo intento, `credit-auto-hpo-20261109`, terminó **Completed** el 9/11/2026 a las 10:02:31 UTC. Tardó 26 min 5,8 s desde la creación; probó dos candidatos con objetivo ROC-AUC y eligió XGBoost. La métrica del mejor candidato en validación fue ROC-AUC 0,67979; no es la métrica TEST. Los jobs de preparación y entrenamiento usaron instancias entre `ml.m5.2xlarge` y `ml.m5.12xlarge`; los informes emplearon hasta dos `ml.m5.4xlarge`. La suma estimada del cómputo de este intento es **USD 0,5703** y la de ambos intentos **USD 1,7706**, a tarifa pública de `us-east-1`, sin EBS, S3, ECR, CloudWatch, impuestos ni otra actividad. No es una factura ni un saldo confirmado; cálculo por job y precios en `output/aws-credit/autopilot-compute-cost-estimate.json`.

Los canales de entrada reutilizaron exactamente el TRAIN (6.027), VALIDATE (1.507) y TEST (3.229) de GCP y las mismas variables. Los logs muestran que Autopilot inspeccionó las 7.534 filas de TRAIN y VALIDATE para evaluar procesadores; sus validaciones internas por pliegues no son idénticas al procedimiento de GCP. El TEST se mantuvo separado de la selección. El objetivo AWS fue ROC-AUC porque Autopilot no ofrecía PR-AUC como objetivo en la API; el objetivo de GCP era PR-AUC. Se limitaron a dos candidatos y 900 s por candidato frente al presupuesto GCP de una hora-nodo. No son presupuestos ni búsquedas equivalentes.

La política explícita del Learner Lab denegó `sagemaker:CreateTransformJob` antes de iniciar inferencia administrada. Se descargaron los artefactos del candidato seleccionado y se ejecutó localmente la cadena de tres contenedores oficiales de inferencia de SageMaker; no se creó un endpoint. Los 3.229 resultados conservaron el orden de entrada y se verificaron las etiquetas y probabilidades. En TEST, con incumplimiento como clase positiva y umbral 0,5: accuracy **0,630845**, precisión **0,049834**, recall **0,555556**, F1 **0,091463**, ROC-AUC **0,647682**, TP=60, TN=1977, FP=1144 y FN=48. Average precision sklearn fue **0,084814**; no se compara numéricamente como si fuera el PR-AUC nativo de GCP. Resultados y recibos: `output/aws-credit/autopilot-test-metrics.json`, `autopilot-test-predictions.csv`, `autopilot-hpo-completed.json` y definición `autopilot-hpo-job.json`.

En el mismo TEST y umbral de 0,5, el AutoML de GCP obtuvo accuracy 0,962527, F1 0,103704, recall 0,064815 y ROC-AUC 0,654208. Las diferencias de objetivo, selección, presupuesto y validación interna limitan la atribución de diferencias al proveedor. Inferencia y costos de despliegue administrados de AWS no quedaron medidos. No hay jobs Processing, Training o Transform activos ni endpoint. El modelo temporal usado para preparar el intento de Batch Transform se eliminó; se conservan la definición y los artefactos del candidato.

Investigación detallada de Azure y tabla de costos para las tres nubes: [comparación Azure y costos](../../docs/comparacion_azure_costos.md).

## Búsqueda Autopilot ampliada a diez candidatos

El usuario autorizó una segunda búsqueda HPO más amplia. El trabajo `credit-auto-hpo10-20261109` finalizó **Completed**, con 10 candidatos exitosos, límite de 900 s por candidato y 7200 s para el job completo. Usó las mismas particiones y objetivo AUC de la búsqueda anterior. Duración de pared **30 min 33 s**; candidato elegido por validación `credit-auto-hpo10-20261109w8lNTU-001-2e6283cb`, XGBoost, AUC de validación **0,685440** (frente a 0,679790 con dos candidatos). La selección se hizo antes de la evaluación TEST.

| Métrica en TEST, clase 0 | AWS 2 candidatos | AWS 10 candidatos | GCP AutoML |
|---|---:|---:|---:|
| Accuracy | 0,630845 | 0,695881 | 0,962527 |
| Precisión | 0,049834 | 0,054990 | 0,259259 |
| Recall | 0,555556 | 0,500000 | 0,064815 |
| F1 | 0,091463 | 0,099083 | 0,103704 |
| ROC-AUC | 0,647682 | 0,627683 | 0,654208 |

Con umbral 0,5, el nuevo modelo registró **TP=54, TN=2193, FP=928 y FN=54**. Su average precision sklearn es 0,080844; no equivale directamente al PR-AUC nativo de GCP. Como en el primer ensayo, el Learner Lab bloquea Batch Transform: la inferencia del candidato exportado se hizo localmente con los tres contenedores SageMaker. Se validaron 3.229 filas, etiquetas, probabilidades y hashes; no se creó un endpoint. El mejor valor de validación aumentó, pero el ROC-AUC TEST disminuyó. Son resultados exploratorios: el TEST se ha observado en varios experimentos y no constituye una prueba independiente para decidir nuevos cambios.

El cómputo estimado a tarifa pública de los **24 jobs** de esta búsqueda es **USD 1,9199**, más EBS, S3, ECR, logs, impuestos y otros cargos; no es una factura. El estimado del intento exitoso anterior de dos candidatos fue USD 0,5703 y el intento inicial de ensemble detenido USD 1,2003; la suma de los tres es ≈USD 3,6905 solo de cómputo estimado. Las definiciones, candidatos, hashes, resultados, recibos por job y cálculo están en `output/aws-credit/hpo10/`. El watchdog local detuvo su seguimiento después de verificar que el trabajo y los jobs habían finalizado; su umbral de USD 12 no era un límite de facturación de AWS.
