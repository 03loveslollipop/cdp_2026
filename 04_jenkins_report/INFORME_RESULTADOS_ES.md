# Informe unificado de resultados: Jenkins y entrenamiento de clasificación crediticia

Proyecto cdp_2026 · Evidencia de ejecución, modelos, integración GitHub y estado de GCP


## Jenkins y clasificación crediticia
Informe unificado de resultados

Proyecto cdp_2026 | Corte: 8 de noviembre de 2026. Este documento reúne la implementación, los resultados medidos y las capturas reales del navegador. Su alcance es académico y de prueba; no acredita un modelo listo para producción.

La primera validación local (#5) y cloud (#1 del job original) completó 165 pruebas, entrenamiento temporal, controles de calidad, aprobación de admin y notificación. Después se activó un segundo job desde GitHub para verificar push y merge reales. Las ejecuciones y sus revisiones se distinguen para no atribuir pruebas nuevas a capturas históricas.

| Entregable | Estado comprobado |
| --- | --- |
| Jenkins local y GCP | Histórico local #5 y cloud #1: SUCCESS, 165 tests. Integración posterior GitHub: job independiente con pruebas ampliadas. |
| Activación automática | Webhook GitHub activo. Push y merge reales en la rama de laboratorio; ver sección 9. |
| Comparación de modelos Python | Regresión logística, árbol, random forest y dos referencias evaluados con el mismo holdout. |
| Vertex AI y AutoML | Preparación técnica disponible. Entrenamiento en el dashboard pendiente de aprobación e inicio de sesión. |
| Control de costos y vencimiento | Parada programada el 13/11/2026 a las 02:41:05 UTC y limpieza desde un minuto después. |

El entrenamiento medido en Jenkins GCP se ejecutó con Python sobre una VM. El servicio Cloud Run actúa exclusivamente como receptor del webhook. No se lanzó entrenamiento AutoML ni Vertex AI; esa fase exige aprobación e inicio de sesión en el dashboard.

El PDF incorpora las imágenes. El paquete ZIP añade originales PNG, fuente editable, índices y anexos de operación. No incluye contraseñas, tokens, estado de Terraform ni registros individuales del conjunto de datos.


## 1. Entorno, cuentas y configuración

| Elemento | Configuración verificada |
| --- | --- |
| Repositorio | https://github.com/03loveslollipop/cdp_2026 | rama original: feat/bigquery-ingestion-pipeline |
| Organización / aprovisionamiento | 02labs.me (408308144073) | contact@02labs.me |
| Proyecto Jenkins | nb-core-dev-99d0 | VM semester-jenkins | us-central1-a |
| Cómputo y persistencia | e2-medium, 2 vCPU, 4 GB RAM; disco de arranque pd-balanced de 40 GB; volumen Docker persistente. |
| Controlador | Jenkins 2.580.2, Java 21, Python 3.13 CPU. Builds históricos con 71 plugins; integración GitHub con 76 plugins compatibles. |
| Acceso | Local: 127.0.0.1:18081. GCP: túnel IAP en 127.0.0.1:18083. Sin ingreso público a la consola. |
| Proyecto de entrenamiento | nb-risk-ml-dev-99d0. Separado del entorno Jenkins; no se inició entrenamiento Vertex. |
| Facturación | Billing Account for Education | 01ADCB-D56D56-B45DCC | USD. |

Terraform creó la infraestructura de Jenkins y una política independiente de vencimiento. La identidad del controlador solo lee su repositorio de imágenes y sus dos secretos; no recibe permisos de entrenamiento en Vertex. No se generaron claves de cuentas de servicio. El receptor webhook usa Cloud Run y conectividad VPC privada; la consola sigue detrás de IAP.

La VM se eligió por la persistencia y el trabajo continuo de Jenkins, incluidos polling y aprobaciones. Las credenciales y el estado del navegador se conservan fuera de la evidencia compartida. La configuración de cuentas y recursos se registra además en CLOUD_DEPLOYMENT_INVENTORY.md, en la raíz del workspace.

La actualización amplió el lock a 76 plugins compatibles. GitHub 1.47.0 y JUnit 1458.v38661c0638e2 están activos también en GCP. Los cinco plugins adicionales se cargaron dinámicamente comprobando hashes; la VM y su volumen no se reemplazaron y el historial anterior se conserva.


## 2. Procedimiento reproducible de Jenkins

1. Preparar un snapshot Git aislado y las credenciales locales con python3 ci/prepare_local.py. Descargar y verificar los plugins con python3 ci/jenkins/fetch_plugins.py. Levantar Jenkins y el receptor de notificaciones con docker compose up -d --build.

2. Abrir Jenkins, autenticarse y revisar el job credit-classification. En Configure → Pipeline se seleccionó Pipeline script from SCM, Git, file:///opt/source, rama */ci-review y archivo Jenkinsfile. El checkout pertenece al workspace del job y no requiere subir con dir("..").

| Etapa | Acción y criterio |
| --- | --- |
| Clone repository | Limpiar el workspace del job, clonar SCM y conservar el SHA efectivo del checkout. Es la primera etapa. |
| Validate structure | Comprobar archivos, configuraciones, objetivo y separación cronológica sin variables excluidas. |
| Repository tests | Ejecutar la suite real y producir JUnit XML; un fallo detiene la aprobación. |
| Train and evaluate | Entrenar y evaluar candidatos con cinco bloques temporales y semillas 42, 43 y 44. |
| Quality and stability | Aplicar umbrales de validación y estabilidad; publicar métricas y gráficos antes de pedir aprobación. |
| Approve model | Solicitar revisión a admin; tiempo máximo de espera de 20 minutos. |
| Record approval / Post | Registrar aprobador, URL y commit; publicar JUnit y artefactos agregados; enviar notificación autenticada. |

3. Pulsar Build Now, observar consola y etapas, revisar los artefactos y completar Approve model. Verificar por separado el resultado global, el reporte de pruebas, el recibo de aprobación y la recepción de la notificación.

La ejecución completa tiene un límite de 45 minutos, un executor, dos hilos de CPU y sin builds concurrentes del job. Se conservan diez ejecuciones. El despliegue en GCP usa Terraform, imagen fijada por digest, Secret Manager y el mismo flujo de verificación en el navegador.


## 3. Evidencia: pipeline en ejecución

Desde el navegador se inició el build cloud #1 y se observaron la consola y Stage View mientras ejecutaba trabajo. Las imágenes siguientes son capturas originales de Playwright; no son recreaciones del resultado.

![Figura 1. Consola del build de Jenkins alojado en GCP durante su ejecución.](assets/20-cloud-running-console.png)

![Figura 2. Etapas observadas mientras el pipeline cloud seguía ejecutándose.](assets/21-cloud-running-stages.png)

Para reproducir: abrir credit-classification, seleccionar el número de build y entrar a Console Output / Stage View. El archivo index.json de evidencia conserva URL, fecha de captura UTC y SHA-256 de las capturas originales.


## 4. Evidencia: calidad y aprobación humana

Los controles se aplican al modelo seleccionado con validación temporal, antes de utilizar el holdout como auditoría. La evidencia agregada está disponible para el revisor durante la pausa de aprobación.

| Control | Valor medido | Política | Resultado |
| --- | --- | --- | --- |
| F1 medio de validación | 0,1871 | ≥ 0,10 | Cumple |
| ROC-AUC medio de validación | 0,6650 | ≥ 0,50 | Cumple |
| Desviación F1 temporal | 0,0292 | ≤ 0,15 | Cumple |
| Desviación F1 entre semillas | 0,0110 | ≤ 0,05 | Cumple |

![Figura 3. Solicitud real de aprobación de admin después de superar las puertas de calidad.](assets/22-cloud-approval.png)

La autorización se registra con identidad, URL del build y SHA de origen. Estos umbrales son reglas versionadas del ejercicio; superarlos no equivale a una certificación de riesgo de modelos para producción.


## 5. Evidencia: pruebas y cierre del proceso

![Figura 4. Reporte JUnit cloud: 165 pruebas aprobadas, cero fallidas y cero omitidas.](assets/23-cloud-165-tests.png)

![Figura 5. El receptor privado aceptó la notificación SUCCESS de finalización del build cloud.](assets/25-cloud-notification-delivered.png)

| Entorno / build | Estado | Pruebas | Duración total |
| --- | --- | --- | --- |
| Local #5 | SUCCESS | 165 / 0 / 0 | 193,02 s |
| GCP #1 | SUCCESS | 165 / 0 / 0 | 247,30 s |

Las duraciones incluyen la espera de aprobación. La notificación es un webhook hacia el receptor privado del laboratorio; no es un correo ni un mensaje enviado a un servicio externo. El recibo de aceptación acredita entrega y se revisó junto con el resultado final de Jenkins.


## 6. Evidencia: resultado final y automatización

![Figura 6. Todas las etapas del build cloud #1 terminaron correctamente.](assets/24-cloud-completed-stages.png)

![Figura 7. Evidencia histórica local: build iniciado por un cambio SCM detectado automáticamente.](assets/08-local-scm-triggered.png)

El polling H/2 * * * * observa la rama configurada cada dos minutos aproximadamente y solo ejecuta cuando encuentra cambios. El build local #5 se originó por SCM; el cloud #1 fue iniciado por admin.

La evidencia histórica de polling se obtuvo sobre un snapshot aislado. Posteriormente se publicó la implementación en GitHub y se verificaron pushes reales, incluido el de un merge, con el nuevo job credit-classification-github. Sus capturas y recibos se presentan en la sección 9.


## 7. Resultados de clasificación crediticia

Conjunto de 10.763 registros: 7.534 para entrenamiento y 3.229 para holdout cronológico. Incumplimiento corresponde a Pago_atiempo=0. El random forest fue seleccionado con validación previa al holdout; no se cambió el ganador al inspeccionar resultados de prueba.

| Modelo Python | Accuracy | F1 impago | Recall impago | ROC-AUC | AP |
| --- | --- | --- | --- | --- | --- |
| Regresión logística | 0,9080 | 0,1134 | 0,1759 | 0,6278 | 0,0652 |
| Árbol de decisión | 0,9297 | 0,1498 | 0,1852 | 0,6084 | 0,0591 |
| Random forest seleccionado | 0,8250 | 0,1130 | 0,3333 | 0,6573 | 0,0994 |
| Referencia heurística | 0,7928 | 0,0798 | 0,2685 | 0,6241 | 0,0858 |
| Dummy mayoritario | 0,9666 | 0,0000 | 0,0000 | 0,5000 | 0,0334 |

![Figura 8. Comparación medida del holdout; intervalos de muestreo donde están disponibles. Las etiquetas técnicas originales se conservan.](assets/comparison.png)

La exactitud aislada resulta engañosa: el dummy logra 96,66 % sin identificar un solo incumplimiento. El bosque detecta 36 de 108 incumplimientos y genera 493 falsos positivos. Su F1 bajo y el costo operativo de esas alertas requieren revisión antes de cualquier uso real.

AP significa average precision de scikit-learn; no debe mezclarse sin aclaración con auPrc nativo de AutoML. RMSE no es la métrica principal de este problema de clasificación binaria.


## 8. Estabilidad, incertidumbre y límites

Para el bosque seleccionado, F1 medio en validación temporal = 0,1871; desviación entre bloques = 0,0292; desviación entre semillas 42/43/44 = 0,0110. La evaluación emplea cinco bloques cronológicos. El umbral de incumplimiento fijado con validación es aproximadamente 0,08828.

![Figura 9. Variación del F1 en las ventanas temporales de evaluación.](assets/temporal_f1.png)

| Indicador del bosque en holdout | Estimación | IC bootstrap 95 % |
| --- | --- | --- |
| Accuracy | 0,8250 | [0,8132; 0,8365] |
| F1 de incumplimiento | 0,1130 | [0,0845; 0,1413] |
| ROC-AUC | 0,6573 | [0,6073; 0,7108] |

Los intervalos usan 200 remuestreos estratificados y describen incertidumbre del holdout observado, no consistencia de reentrenamiento. La prevalencia de incumplimiento baja de 5,35 % en entrenamiento a 3,34 % en holdout; la caída de F1 obliga a estudiar deriva temporal, calibración y costos de error.

Las coincidencias local/GCP prueban reproducibilidad para la imagen, datos y protocolo ensayados. El holdout ya había sido inspeccionado en el EDA anterior; hace falta una muestra externa nueva para sostener una conclusión independiente de generalización. La disponibilidad de predictores en el momento de decisión sigue siendo un supuesto del contrato de datos.


## 9. GitHub: webhook desplegado

La cuenta propietaria 03loveslollipop quedó autenticada con ADMIN. Se publicó la implementación en ci/jenkins-lab-20261108 y se creó el webhook 708866067, activo, para el evento push. No se modificó master ni se activaron sus despliegues Heroku.

| Configuración | Valor desplegado |
| --- | --- |
| Receptor HTTPS | https://semester-jenkins-webhook-tcwenm7hba-uc.a.run.app/github-webhook/ |
| Cloud Run / proyecto | semester-jenkins-webhook / nb-core-dev-99d0 / us-central1 |
| Capacidad | 1 vCPU, 256 MiB; mínimo 1 y máximo 1; CPU limitada en inactividad. |
| Red privada | Direct VPC egress, 10.81.1.0/26 → Jenkins 10.81.0.3:8080. |
| Firma y secreto | HMAC SHA-256 validado en relay y Jenkins; secreto en Secret Manager y credencial SYSTEM. |
| Job / fuente | credit-classification-github / GitHub HTTPS / */ci/jenkins-lab-20261108 |
| Trigger | githubPush(); polling H/2 como respaldo. |
| Vencimiento | 13/11/2026 02:41:05 UTC; no se amplió el plazo. |

El receptor rechaza firmas inválidas (403), repositorios distintos y referencias fuera del alcance; solo reenvía el webhook autorizado. La raíz responde 404 y la consola Jenkins no se expone. Antes de cada prueba de trigger se pausó el cron SCM: el build quedó atribuido a Started by GitHub push by 03loveslollipop.

La activación solo cubre la rama vigilada del laboratorio. Los checks de PR previos al merge en Jenkins requerirían Multibranch/GitHub Branch Source; el repositorio ya tiene un workflow GitHub Actions separado. La recepción HTTP no sustituye la comprobación de SHA, pruebas y finalización.


## 9.1. Evidencia del trigger y del checkout

GitHub entregó el push directo y el push de integración con HTTP 200. Jenkins registró GitHubPushCause, con el cron SCM temporalmente vacío antes de cada evento. Se verificó igualdad entre SHA del evento, revisión SCM y recibo de aprobación. El Jenkinsfile restauró después el polling H/2.

![Figura 10. Log real del hook en Jenkins: evento recibido por la red privada y nueva revisión de la rama destino.](assets/35-jenkins-github-hook-log.png)

![Figura 11. Consola en ejecución del build #3: Started by GitHub push y checkout del commit de merge 501952de…](assets/36-github-merge-console-running.png)

Las capturas pueden mostrar la zona horaria del navegador; el índice y los recibos conservan UTC. No se utilizó una captura de consola todavía vacía como prueba de ejecución.


## 9.2. Merge real y casos de entrega

![Figura 12. GitHub público: PR #16 integrado en ci/jenkins-lab-20261108; master no fue modificado.](assets/31-github-pr-16-merged.png)

| Caso observado | HTTP / efecto |
| --- | --- |
| Push 7775c845… | 200; inicia build #2 del job GitHub. |
| Merge PR #16 → 501952de… | 200; inicia build #3. |
| Push a la rama del PR | 202; ignorado por el job de laboratorio. |
| Reentrega del push original | 200, duplicate: true; no se inicia un build extra. |
| Firma inválida / ruta raíz | 403 / 404; no expone la consola. |

Estos resultados se verificaron con la API real de entregas de GitHub y los recibos Jenkins. Abrir o actualizar un PR todavía no ejecuta este job de rama única antes del merge. El workflow GitHub Actions del repositorio es independiente y su resultado no se confunde con el de Jenkins.


## 9.3. Resultado de los builds GitHub

| Build / origen | Resultado | Pruebas P/F/O | Duración total |
| --- | --- | --- | --- |
| #1 / bootstrap | SUCCESS | 185/0/0 | 305.03 s |
| #2 / push | SUCCESS | 186/0/0 | 229.81 s |
| #3 / merge | SUCCESS | 186/0/0 | 246.33 s |

![Figura 13. Las tres ejecuciones GitHub completaron todas sus etapas. El bootstrap no se atribuye al webhook.](assets/39-github-push-merge-completed-stages.png)

![Figura 14. JUnit del build de merge: 186 aprobadas, cero fallos y cero omisiones.](assets/38-github-merge-186-tests.png)

Las dos ejecuciones automáticas superaron las puertas del modelo y fueron aprobadas por admin. Las métricas del bosque coinciden con la evaluación original a tolerancia 1e-12. Los 186 casos incluyen las regresiones del hook y del receptor; no se atribuyen retrospectivamente a los builds históricos de 165 pruebas.


## 9.4. Notificaciones y trazabilidad GitHub

![Figura 15. Receptor privado: SUCCESS y SHA exacto de los builds #1, #2 y #3 del nuevo job.](assets/40-github-completion-notifications.png)

Push directo: 7775c84526afb3836b272f6595ee30cddbfb3207. Merge: 501952de01570ea5e29b04cf230c7f886dad387b. Cada recibo incluye URL del build, estado, revisión y hora UTC de aceptación.

La documentación conserva el ping inicial HTTP 403, la corrección del secreto y el ping reentregado con HTTP 200. El PR de ensayo también mostró un fallo del workflow GitHub Actions por un import pytest sin uso en una prueba BigQuery anterior; se retiró ese import y Ruff pasó en la revisión final. Ese fallo histórico no se presenta como si el workflow hubiese pasado.

Fuentes de evidencia: github-verification.json, cleanup-verification.json y anexos de output/github-webhook/. Los JSON publicados contienen métricas agregadas y metadatos de ejecución; no incluyen tokens, contraseñas ni predicciones individuales.


## 10. Entrenamiento en GCP: comparación pendiente

La segunda fase se ejecutará desde el dashboard de GCP, previa aprobación e inicio de sesión del usuario en la sesión persistente de Playwright. Esta entrega no inició AutoML, Vertex AI Pipelines ni despliegues de endpoints.

| Método | Evidencia actual | Resultado |
| --- | --- | --- |
| Python local | Entrenamiento y holdout medidos | Tabla de la sección 7. |
| Python en Jenkins GCP | Ejecución CPU en VM y métricas coincidentes | Reproducibilidad del baseline. |
| Vertex AI Pipelines personalizado | Código de entrenamiento y compilación offline preparados | Pendiente de ejecución real en dashboard. |
| AutoML Tabular | Datos con splits fijos preparados | Pendiente de entrenamiento y evaluación en dashboard. |

Secuencia prevista: seleccionar nb-risk-ml-dev-99d0 y comprobar facturación; habilitar Vertex AI; importar datos tabulares con splits fijos; lanzar AutoML con presupuesto acotado; registrar métricas y exportar predicciones; compilar y subir una especificación con imagen real fijada por digest; ejecutar el pipeline personalizado desde el dashboard y descargar sus artefactos.

Se prepararon 6.027 filas TRAIN, 1.507 VALIDATION y 3.229 TEST para AutoML, con imputación ajustada exclusivamente en entrenamiento. La especificación compilada de demostración contiene un digest de imagen de ceros: no es un pipeline listo para ejecutar ni prueba de un job enviado.

La comparación usará las mismas huellas de datos y holdout, probabilidades de la clase de incumplimiento e identificadores únicos. Se mostrarán accuracy, F1, recall, ROC-AUC, AP y umbrales. No se sustituirán resultados cloud faltantes por los de Python.

El entrenamiento manual ofrece control sobre folds temporales, variables, calibración, umbrales y semillas. AutoML reduce búsqueda e integración manual a cambio de presupuesto administrado y menor visibilidad de la búsqueda. Su superioridad y consistencia deberán medirse; una única ejecución no demuestra estabilidad de reentrenamiento.


## 11. Costos y eliminación automática

Cuenta de facturación verificada: Billing Account for Education, 01ADCB-D56D56-B45DCC, en USD. El total efectivamente facturado y el saldo de créditos educativos no se verificaron desde el dashboard; los valores siguientes son una estimación de lista del entorno Jenkins.

| Componente | Estimación por 730 horas |
| --- | --- |
| VM e2-medium | USD 24,46 |
| Disco pd-balanced de 40 GB | USD 4,00 |
| IPv4 externa efímera | USD 3,65 |
| Artifact Registry, aproximadamente 1,407 GiB | USD 0,14 |
| Total orientativo | USD 32,25 al mes; aproximadamente USD 1,06 al día. |

El receptor caliente añade aproximadamente USD 0,27/día (USD 1,35 por cinco días completos) de CPU/memoria en inactividad, antes de franquicias y créditos, más actividad y almacenamiento. La base Jenkins de USD 1,06/día pasa a unos USD 1,33/día con ese supuesto; no es factura consolidada. Se mantiene caliente para atender GitHub sin el retraso posible de un arranque Direct VPC.

Valores antes de créditos, descuentos, impuestos, tráfico y futuras ejecuciones. No representan una factura consolidada de todos los proyectos ni el costo de AutoML. A las 02:32 UTC del 8/11, el período de la VM actual sumaba aproximadamente 2,476 horas, unos USD 0,11 brutos; esa observación no incluye una VM anterior reemplazada.

| Hito de la política | Fecha / alcance |
| --- | --- |
| Parada de la VM | 13/11/2026 02:41:05 UTC = 11:41:05 JST. |
| Primera limpieza | 13/11/2026 02:42:05 UTC. La finalización depende de las APIs. |
| Reintentos | 49 envíos de limpieza cada 30 minutos, hasta 14/11/2026 02:42:05 UTC. |
| Recursos objetivo | VM, disco, IP efímera, red/subred/firewall dedicados, imágenes, secretos e identidades; también servicio Run, subred, firewall, secreto e identidad del relay. |
| Recursos preservados | Proyectos compartidos, cuenta de facturación y entorno de entrenamiento de riesgo. |

Se verificaron por lectura FULL los 49 nuevos payloads cleanup-webhook y la parada original; se retiró la generación anterior sin cambiar horarios. Los Cloud Builds de solo lectura validaron los 29 permisos de limpieza, incluido el servicio Run. La eliminación real sigue programada para el futuro; no se ejecutó anticipadamente.


## 12. Trazabilidad, incidencias y próximos pasos

Origen de las ejecuciones finales: snapshot Git aislado 242e2edf71981a4ea10dd8bb8756d0b614c569b6, construido sobre HEAD original b5c51c7b92c99364cab1857ea1a972a5b838e79f. Los cambios preparados del webhook pertenecen a una revisión posterior; las capturas históricas no se atribuyen a esa nueva versión.

Incidencias resueltas: el primer build terminó UNSTABLE por faltar BUILD_URL al notificar; se configuró la URL y un fallback probado. También se corrigió la inclusión de cinco pruebas nuevas en el snapshot. Los builds anteriores de 160 pruebas no se presentan como si contuvieran 165. En la preparación del webhook se detectó un JUnit incompatible con Jenkins 2.580.2; se restauró la versión compatible y se incorporaron dos pruebas y un guard de versión de plugins. El primer ping GitHub reveló un salto de línea en el secreto; se normalizó, se probó y la reentrega pasó a HTTP 200. El PR de verificación también expuso un import pytest sin uso, previo a Jenkins, en las pruebas BigQuery; se retiró en la revisión final y se verificó Ruff.

Dataset SHA-256:
48e34610b823055a5f4e7a107142e25b08ba40920848eab1a68ff6396eb26927
Holdout SHA-256:
f0f8ec775541328cfcaf07fa5a8455a089b2f3832549c583de35804f5216329a

Artefactos de soporte: output/jenkins-receipts/summary.json; output/playwright/index.json; docs/jenkins-execution.md; docs/model-results.md; docs/expiry-policy.md; docs/github-webhook.md; docs/gcp-training.md y el inventario de cuentas de la raíz. evidencias.json identifica cada imagen incorporada con su SHA-256. La evidencia nueva del webhook y las notificaciones se encuentra en output/github-webhook/ y en las fuentes JSON de este informe.

Prioridades restantes: revisar el PR de implementación antes de integrar en otras ramas; obtener aprobación para el entrenamiento desde el dashboard; incorporar resultados reales AutoML y Vertex al mismo informe; verificar el retiro automático en la fecha fijada y conservar evidencia local. El job activo vigila la rama de laboratorio; master no fue modificado.

Conclusión: el laboratorio acredita clonación, pruebas, entrenamiento, puertas de calidad, aprobación y notificación en local y GCP, más activación real por webhook al hacer push y merge en una rama de laboratorio. La detección de incumplimiento sigue siendo limitada. La comparación con AutoML y Vertex permanece pendiente de ejecución aprobada en el dashboard.


## Referencias

- [GitHub Docs: creación de webhooks y permisos requeridos](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks)
- [Jenkins: plugin GitHub y trigger de push](https://plugins.jenkins.io/github/)
- [Jenkins: sintaxis de pipelines, triggers y post actions](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Google Cloud: precios de Compute Engine](https://cloud.google.com/products/compute/pricing/general-purpose?hl=en)
- [Google Cloud: discos, red y Artifact Registry](https://cloud.google.com/compute/disks-image-pricing)
- [Google Cloud: precios de IPv4 externa](https://cloud.google.com/vpc/network-pricing)
- [Google Cloud: precios de Artifact Registry](https://cloud.google.com/artifact-registry/pricing)
- [Google Cloud: precio de instancia mínima Cloud Run](https://cloud.google.com/run/pricing)
- [GitHub: PR #16 integrado en la rama de laboratorio](https://github.com/03loveslollipop/cdp_2026/pull/16)
