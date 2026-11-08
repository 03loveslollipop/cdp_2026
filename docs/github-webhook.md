# GitHub → Jenkins: integración y evidencia

La cuenta propietaria `03loveslollipop` está activa y tiene ADMIN en `03loveslollipop/cdp_2026`. Se publicó la implementación en **`ci/jenkins-lab-20261108`** y se instaló el webhook **708866067**, activo, para `push`, con TLS verificado y secreto HMAC SHA-256. La rama `master` no se modificó.

## Configuración desplegada

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

## Ejecución reproducible

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

## Verificación de push y merge

Para aislar la causa, se dejó temporalmente vacío el cron SCM antes de cada evento observado. Los builds arrancados por el webhook registran **Started by GitHub push by 03loveslollipop**. El Jenkinsfile restablece el polling de respaldo al comenzar cada ejecución.

- Push directo: commit `7775c84526afb3836b272f6595ee30cddbfb3207`, entrega GitHub HTTP 200 y build **#2**.
- Merge real: [PR #16](https://github.com/03loveslollipop/cdp_2026/pull/16), integrado únicamente en la rama de laboratorio; commit `501952de01570ea5e29b04cf230c7f886dad387b`, entrega HTTP 200 y build **#3**.
- El push de la rama no vigilada `ci/webhook-merge-check-20261108` recibió HTTP 202 (ignorado), sin build independiente del job de laboratorio.
- El primer ping tuvo HTTP 403 por un salto de línea final en el secreto de Secret Manager. Se normalizó el secreto, se añadió una regresión y su reentrega recibió HTTP 200. El intento fallido se conserva en la evidencia.

Los resultados completos, SHA de checkout, JUnit, aprobación y notificación se registran en `output/github-webhook/verification.json` y los recibos de cada build. Un HTTP 200 o un ping por sí solos no acreditan éxito de las pruebas. Las capturas de Jenkins son de navegador; los recibos de GitHub se obtienen de su API real, sin simular una sesión autenticada del dashboard de GitHub.

## Alcance de eventos

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

El receptor permite también la referencia `master` para una futura configuración, pero **el job actual vigila solo la rama de laboratorio**. La presencia de un hook no activa tests de todas las ramas ni protección de merges. Cambiar la rama del job requiere que esa rama contenga la implementación y una decisión explícita sobre los despliegues ya asociados a `master`.

## Limpieza

El worker incorpora servicio Run, firewall y subred del receptor, su secreto e identidad. Se ampliaron tres permisos Run en el rol temporal y se instalaron 49 nuevos payloads de limpieza `cleanup-webhook-00` a `cleanup-webhook-48`, con los horarios originales. Tras verificar cada payload por lectura FULL y todas las páginas, se retiraron los 49 payloads anteriores. La tarea `stop-vm-at-expiry` quedó intacta.

El Cloud Build de solo lectura `1b7b638c-d558-44e3-8670-19416c132f3d` verificó los 29 permisos del worker. La política no elimina proyectos compartidos ni el entorno de entrenamiento. El hook de GitHub es configuración externa sin costo de cómputo: tras retirar el receptor, su URL deja de servir; eliminar ese registro desde GitHub cuando finalice el ejercicio evita entregas futuras a una URL retirada.

Referencias: [crear webhooks](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks), [validar firmas](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries), [plugin GitHub de Jenkins](https://plugins.jenkins.io/github/), [Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc).
