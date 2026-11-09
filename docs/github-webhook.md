# GitHub → Jenkins: todas las ramas y pipeline completo en master

## Configuración actual (9 de noviembre de 2026 JST)

El usuario confirmó utilizar **`master`**, la rama principal existente. El webhook **708866067** permanece activo para el evento `push`, con HTTPS, verificación TLS y firma HMAC SHA-256. GitHub ya envía los pushes de todo el repositorio; el filtro anterior estaba en el relay y en el job. Ahora el relay acepta cualquier referencia válida `refs/heads/*` de `03loveslollipop/cdp_2026`, sin aceptar tags ni borrados.

| Caso | Comportamiento actual |
|---|---|
| Push a una rama existente distinta de master | Clonar esa revisión, validar estructura de pruebas, ejecutar pytest, publicar JUnit y notificar; sin búsqueda completa de modelos ni aprobación. |
| Push o merge a master | Pruebas, entrenamiento CPU, controles de calidad/estabilidad, aprobación admin, artefactos y notificación. |
| Rama nueva sin Jenkinsfile | El proyecto multibranch la descubre mediante Git y utiliza la definición compartida; el escaneo periódico es de un minuto. |
| PR de una rama del repositorio | Su push ejecuta tests de esa rama. GitHub Actions sigue proporcionando sus checks de PR por separado. |
| Tag, borrado o repositorio ajeno | Se ignora o rechaza; no ejecuta modelos. |
| Reentrega idéntica | Se deduplica; no solicita otro build para el mismo evento. |

Proyecto Jenkins **`credit-classification-branches`**. `Git SCMSource` descubre todas las ramas del origen y Remote Jenkinsfile Provider carga un Jenkinsfile compartido, fijado a un SHA completo de la rama de implementación. Así no se exige copiar un Jenkinsfile a cada rama. La variable `SEMESTER_PRIMARY_BRANCH=master` controla las etapas completas; `SEMESTER_CI_REVISION` fija herramientas y definición. El job histórico `credit-classification-github` está deshabilitado y conserva builds y artefactos.

Cada hijo registra `githubPush()`. La revisión del código se fija antes de esperar al ejecutor. El webhook y el escaneo de respaldo pueden encolar builds de la misma revisión durante una transición; los recibos distinguen las causas. La deduplicación de entregas del relay solo se refiere al mismo ID de evento GitHub. El escaneo de Git cada minuto cubre ramas nuevas y funciona como respaldo, sin consumir la cuota REST anónima de GitHub. Se conservan 79 plugins compatibles en el controlador. En la validación inicial se detectaron y corrigieron dos problemas: el chequeo de features exigía el layout moderno a ramas antiguas `src/`, y el origen GitHub SCM agotaba su cuota anónima. El origen actual usa Git directamente y el chequeo de features admite ambos layouts; la validación completa de master sigue siendo estricta.

La configuración reproducible está en `ci/jenkins/configure_multibranch.groovy` y su cliente:

```bash
# Revisar primero el script renderizado, con el SHA real publicado.
python3 ci/configure_multibranch.py --ci-revision <SHA_COMPLETO> --primary-branch master
python3 ci/configure_multibranch.py --ci-revision <SHA_COMPLETO> --primary-branch master --apply
```

El cliente usa el túnel privado y credenciales locales que no se incluyen en el informe. La actualización Terraform del relay modificó solo su imagen y `BRANCHES=*`: 0 recursos añadidos, 1 actualizado, 0 destruidos. Se conserva el vencimiento **13/11/2026 02:41:05 UTC**. No se repitió AutoML ni se creó infraestructura de entrenamiento.

## Por qué el acceso web dice localhost

Jenkins se ejecuta en la VM **`semester-jenkins`**, proyecto GCP **`nb-core-dev-99d0`**, zona **`us-central1-a`**. El navegador abre `http://127.0.0.1:18083`, extremo local de un túnel autenticado IAP hacia **`10.81.0.3:8080`** dentro de GCP. El puerto local solo funciona mientras el túnel esté abierto en esa computadora. La URL no implica que el controlador esté ejecutándose en Docker local. El entorno Docker local histórico usa el puerto 18081.

```bash
gcloud compute start-iap-tunnel semester-jenkins 8080 \
  --project=nb-core-dev-99d0 --zone=us-central1-a \
  --local-host-port=127.0.0.1:18083
```

GitHub utiliza el receptor público **`https://semester-jenkins-webhook-tcwenm7hba-uc.a.run.app/github-webhook/`**. Cloud Run valida la firma y reenvía el evento por VPC privada al mismo Jenkins GCP. La consola administrativa permanece detrás de IAP. Las capturas GCP 53–54 muestran la VM real en la consola japonesa; el mensaje del controlador se corrigió para indicar explícitamente GCP y persiste tras un reinicio.

Los recibos actuales y la causa de los builds están en `output/github-webhook/all-branches/verification.json`. La siguiente sección conserva la configuración inicial y los builds #2/#3 como evidencia histórica; no define el alcance actual.

---

La cuenta propietaria `03loveslollipop` está activa y tiene ADMIN en `03loveslollipop/cdp_2026`. Se publicó la implementación en **`ci/jenkins-lab-20261108`** y se instaló el webhook **708866067**, activo, para `push`, con TLS verificado y secreto HMAC SHA-256. La rama `master` no se modificó.

## Configuración inicial en la rama de laboratorio (histórica)

| Elemento | Valor |
|---|---|
| Receptor HTTPS | `https://semester-jenkins-webhook-tcwenm7hba-uc.a.run.app/github-webhook/` |
| Servicio Cloud Run | `semester-jenkins-webhook`, proyecto `nb-core-dev-99d0`, región `us-central1` |
| Capacidad | 1 vCPU, 256 MiB; una instancia mínima y máxima; CPU fuera de solicitudes limitada |
| Red | Direct VPC egress, subred dedicada `10.81.1.0/26`; acceso privado a `10.81.0.3:8080` |
| Seguridad | Firma SHA-256; repo ID 1311514433; allowlist de ramas; límite 2 MiB; sin proxy de otras rutas Jenkins |
| Identidad y secreto | `semester-jenkins-webhook@nb-core-dev-99d0.iam.gserviceaccount.com`; acceso solo a su secreto homónimo |
| Jenkins | Job `credit-classification-github`, SCM HTTPS público, rama `*/ci/jenkins-lab-20261108`, `Jenkinsfile` |
| Trigger | `githubPush()`; `pollSCM('H/2 * * * *')` como respaldo |
| Vencimiento | **13/11/2026 02:41:05 UTC**, idéntico al de la VM |

Cloud Run termina TLS. El receptor solo reenvía solicitudes `POST /github-webhook/` firmadas y autorizadas; `/` devuelve 404 y una firma inválida devuelve 403. `GET /healthz` comprueba conectividad privada para el arranque. La consola de Jenkins sigue protegida por IAP y autenticación.

Se mantiene una instancia pequeña caliente porque Direct VPC puede tardar más que el plazo de respuesta de GitHub al arrancar desde cero. Su costo orientativo de inactividad es USD 0,27/día antes de créditos/franquicias, más solicitudes activas, almacenamiento y secretos. No es una lectura de la factura. Fuente: [precios Cloud Run](https://cloud.google.com/run/pricing).

## Procedimiento inicial de instalación del hook

1. Aplicar la base Terraform de `cloud/webhook` sin el servicio (`deploy_receiver=false`). Crea API Run, cuenta de servicio, contenedor Secret Manager, binding de lectura, subred y firewall privado.
2. Ejecutar `python3 cloud/webhook/publish.py`: genera un secreto local con permisos 600, crea su versión fuera del estado Terraform, construye la imagen fijada a una base por digest y la publica en el Artifact Registry existente. Las credenciales Docker son temporales.
3. Planificar y aplicar el servicio con `python3 cloud/webhook/terraform.py plan -out=receiver.tfplan` y `python3 cloud/webhook/terraform.py apply receiver.tfplan`. El wrapper comprueba organización/cuenta y rechaza recreación después del vencimiento.
4. En Jenkins, instalar los cinco plugins GitHub adicionales y sus dependencias comprobando sus hashes del lock de 76 plugins. En este entorno se cargaron dinámicamente mediante la API administrativa a través de IAP; VM, volumen y build histórico #1 quedaron intactos. JUnit sigue fijado a `1458.v38661c0638e2`, compatible con Jenkins 2.580.2.
5. Crear una credencial Jenkins de tipo Secret text, alcance SYSTEM, ID `semester-github-webhook`, con el mismo secreto. Seleccionarla en **Manage Jenkins → System → GitHub → Advanced → Shared secret**, algoritmo SHA256; mantener desactivada la gestión automática de hooks.
6. Crear el job de Pipeline from SCM con la URL y rama de la tabla; ejecutar una vez para registrar SCM y triggers. El primer build remoto también pudo recibir polling, por lo que no se atribuye al webhook.
7. Instalar exclusivamente el hook de esta URL con el plan e instalador siguientes:

```bash
python3 ci/github_webhook.py --url https://semester-jenkins-webhook-tcwenm7hba-uc.a.run.app/github-webhook/
python3 ci/github_webhook.py --url https://semester-jenkins-webhook-tcwenm7hba-uc.a.run.app/github-webhook/ \
  --secret-file .jenkins/secrets/github-webhook --apply
```

El instalador confirma identidad ADMIN, dirección HTTPS pública, evento push, TLS habilitado y lectura posterior; no modifica hooks de otros receptores ni imprime secretos. No se entregó al controlador ningún token GitHub del propietario.

## Verificación histórica de push y merge

Para aislar la causa, se dejó temporalmente vacío el cron SCM antes de cada evento observado. Los builds arrancados por el webhook registran **Started by GitHub push by 03loveslollipop**. El Jenkinsfile restablece el polling de respaldo al comenzar cada ejecución.

- Push directo: commit `7775c84526afb3836b272f6595ee30cddbfb3207`, entrega GitHub HTTP 200 y build **#2**.
- Merge real: [PR #16](https://github.com/03loveslollipop/cdp_2026/pull/16), integrado únicamente en la rama de laboratorio; commit `501952de01570ea5e29b04cf230c7f886dad387b`, entrega HTTP 200 y build **#3**.
- El push de la rama no vigilada `ci/webhook-merge-check-20261108` recibió HTTP 202 (ignorado), sin build independiente del job de laboratorio.
- El primer ping tuvo HTTP 403 por un salto de línea final en el secreto de Secret Manager. Se normalizó el secreto, se añadió una regresión y su reentrega recibió HTTP 200. El intento fallido se conserva en la evidencia.

Los resultados completos, SHA de checkout, JUnit, aprobación y notificación se registran en `output/github-webhook/verification.json` y los recibos de cada build. Un HTTP 200 o un ping por sí solos no acreditan éxito de las pruebas. Las capturas de Jenkins son de navegador; los recibos de GitHub se obtienen de su API real, sin simular una sesión autenticada del dashboard de GitHub.

## Alcance inicial de eventos (histórico)

| Caso | Comportamiento |
|---|---|
| Push nuevo a la rama vigilada | Solicita polling mediante GitHub y ejecuta la revisión observada |
| Merge / squash / rebase merge a la rama vigilada | El push de la rama destino solicita sus tests; se probó merge con commit de integración |
| Otra rama, tag o borrado | El receptor ignora lo que no sea un push válido a una rama permitida |
| Reentrega del mismo evento | Se deduplica por ID de entrega; SCM protege frente al mismo estado después de reiniciar el receptor |
| PR abierto / actualizado sin integrar | Este job de una rama no ejecuta checks previos al merge; el repositorio ya tiene GitHub Actions para PRs, que se reportan por separado |
| Cierre de PR sin merge | No equivale a un push sobre la rama destino |
| Firma inválida o repositorio distinto | Rechazo sin ejecución de Jenkins |
| Tras vencimiento | El receptor rechaza con 410; la parada y limpieza retiran el servicio y su conectividad |

El receptor permite también la referencia `master` para una futura configuración, pero **el job inicial vigilaba solo la rama de laboratorio**. La presencia de un hook no activa tests de todas las ramas ni protección de merges. Cambiar la rama del job requiere que esa rama contenga la implementación y una decisión explícita sobre los despliegues ya asociados a `master`.

## Limpieza

El worker incorpora servicio Run, firewall y subred del receptor, su secreto e identidad. Se ampliaron tres permisos Run en el rol temporal y se instalaron 49 nuevos payloads de limpieza `cleanup-webhook-00` a `cleanup-webhook-48`, con los horarios originales. Tras verificar cada payload por lectura FULL y todas las páginas, se retiraron los 49 payloads anteriores. La tarea `stop-vm-at-expiry` quedó intacta.

El Cloud Build de solo lectura `1b7b638c-d558-44e3-8670-19416c132f3d` verificó los 29 permisos del worker. La política no elimina proyectos compartidos ni el entorno de entrenamiento. El hook de GitHub es configuración externa sin costo de cómputo: tras retirar el receptor, su URL deja de servir; eliminar ese registro desde GitHub cuando finalice el ejercicio evita entregas futuras a una URL retirada.

Referencias: [crear webhooks](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks), [validar firmas](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries), [plugin GitHub de Jenkins](https://plugins.jenkins.io/github/), [Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc).
