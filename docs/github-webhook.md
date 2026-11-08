# GitHub → Jenkins: activación y evidencia

Estado de esta entrega: **implementación preparada; webhook remoto pendiente de acceso del propietario y de receptor HTTPS**. El usuario conectado es `02loveslollipop`, con WRITE, sin ADMIN, en `03loveslollipop/cdp_2026`. La consulta de hooks devuelve HTTP 404. El repositorio pertenece a una cuenta personal (`03loveslollipop`); no se debe interpretar WRITE como permiso para administrar hooks.

El `Jenkinsfile` incorpora `githubPush()` y conserva `pollSCM('H/2 * * * *')` como respaldo. El plugin `github` y sus dependencias están fijados en `ci/jenkins/plugins.lock.json`. Estos cambios deben llegar al controlador y a la rama remota antes de afirmar que están activos. Los builds históricos local #5 y cloud #1 corresponden a la versión anterior, con polling; no prueban el webhook.

Verificación de esta revisión: imagen Compose local reconstruida con 76 plugins conservando el volumen existente; `github` 1.47.0 activo y `Jenkinsfile successfully validated` mediante el validador del controlador real. Pasaron 15 pruebas enfocadas (ocho casos del instalador de hooks, dos regresiones de compatibilidad de plugins y cinco regresiones CI existentes). La VM GCP no se actualizó ni se reemplazó por estos cambios. Se detectó y corrigió un JUnit incompatible en los metadatos de actualización: se conservó el pin 1458.v38661c0638e2 y se agregó una comprobación de versión mínima de Jenkins al instalador de plugins.

## 1. Obtener acceso del propietario

En una terminal del equipo compartido, completar el flujo web con la cuenta propietaria:

```bash
gh auth login --hostname github.com --web --git-protocol ssh --scopes admin:repo_hook
gh api repos/03loveslollipop/cdp_2026 --jq '.permissions'
```

Si ambas cuentas ya están conectadas, `gh auth switch --hostname github.com --user 03loveslollipop` selecciona la propietaria. Un token de alcance suficiente tampoco amplía los permisos del usuario en el repositorio. No pegar contraseñas ni tokens en el informe.

## 2. Publicar y seleccionar la fuente correcta

Publicar la implementación en una rama de trabajo y abrir un PR. No mezclar los commits automáticamente en `master`. Configurar el job con URL `https://github.com/03loveslollipop/cdp_2026.git`, la rama publicada y script `Jenkinsfile`; el repositorio es público y no requiere credenciales de lectura. Ejecutar una vez para registrar sus triggers. Tras integrar el PR, seleccionar `*/master` para comprobar los cambios de esa rama.

Reconstruir el controlador con los 76 plugins fijados. Actualizar la VM requiere conservar su volumen e historial: el módulo mínimo reemplaza VM/disco al cambiar la imagen del startup script. No aplicar ese reemplazo sin respaldo; tampoco modificar la fecha de vencimiento.

## 3. Preparar el receptor HTTPS

GitHub necesita una URL pública `https://<receptor>/github-webhook/`. Los puertos 18081/18083 de localhost y el acceso privado mediante IAP **no son receptores válidos para GitHub**. No se abrió la consola administrativa de Jenkins a Internet.

El receptor debe ofrecer TLS válido y reenviar únicamente `/github-webhook/` a Jenkins, con validación del secreto de firma de GitHub, límite de tamaño de solicitudes y registro del identificador de entrega. Mantener privadas las demás rutas de Jenkins. Si se agrega un relay administrado, incluir servicio, identidad, secretos, red y almacenamiento en el teardown del **13 de noviembre de 2026 a las 02:41:05 UTC**, sin ampliar el plazo. La política existente contiene un payload fijo: editar el worker local no actualiza las tareas ya programadas.

Configurar en **Manage Jenkins → System → GitHub → Advanced → Shared secret** el mismo secreto aleatorio que se usará en GitHub. Mantener desactivado el manejo automático de hooks si se utiliza el instalador de este documento. Comprobar que solicitudes con firma incorrecta se rechazan y que el receptor no funciona después del vencimiento.

## 4. Crear el hook de forma revisable

Guardar el secreto en un archivo local ignorado, con permisos 600; no suministrarlo como argumento literal. Primero obtener el plan, y después instalar:

```bash
python3 ci/github_webhook.py --url https://<receptor>/github-webhook/
python3 ci/github_webhook.py --url https://<receptor>/github-webhook/ \
  --secret-file .jenkins/secrets/github-webhook --apply
```

El instalador solo administra el hook que coincide con esa URL en este repositorio. Comprueba acceso ADMIN, HTTPS, dirección pública, validación TLS, evento `push` y lectura posterior; no modifica otros hooks. No imprime secretos. Su recibo diferencia instalación de entrega efectiva. También se puede usar **Settings → Webhooks → Add webhook**: Content type `application/json`, secreto compartido, evento **Just the push event**, Active y TLS habilitados.

## 5. Casos y criterios de aceptación

| Caso | Comportamiento esperado |
|---|---|
| Push con commit nuevo a la rama vigilada | Entrega `push` válida; polling solicitado por GitHub; nuevo build con SHA coincidente |
| Merge, squash merge o rebase merge en la rama vigilada | El `push` de la rama destino activa sus pruebas; verificar el SHA resultante |
| Push a otra rama | El job de una sola rama no debe evaluar una rama diferente |
| Push de una etiqueta o borrado de rama | No equivale a un commit nuevo de la rama vigilada |
| Reenvío de la misma entrega | Sin build adicional si SCM no cambió; revisar cola y log |
| Apertura/actualización de PR sin integración | No está cubierta por este job de rama única; requiere Multibranch Pipeline/GitHub Branch Source para checks previos al merge |
| Cierre de PR sin merge | No constituye un cambio en la rama destino |
| Firma inválida | Rechazar; sin build |
| Receptor temporalmente caído | Polling periódico conserva detección de cambios; revisar/reentregar el hook |

No se suscribe `pull_request` solo para aparentar pruebas de PR. El trigger estándar inicia una comprobación de SCM; una entrega HTTP 2xx o un `ping` por sí solos no prueban ejecución ni éxito de tests.

## 6. Capturas pendientes

Con Playwright, conservar una sesión autenticada y capturar: configuración del hook sin mostrar el secreto, Recent Deliveries con HTTP 2xx y evento/ref/SHA, build iniciado automáticamente, checkout del mismo SHA, reporte JUnit, aprobación y notificación final. Para acreditar merge, añadir el PR integrado y la entrega `push` de su rama destino. Guardar los recibos con UTC y hashes; actualizar el informe español únicamente con resultados observados.

Referencias: [GitHub: crear webhooks](https://docs.github.com/en/webhooks/using-webhooks/creating-webhooks), [plugin GitHub de Jenkins](https://plugins.jenkins.io/github/), [permisos de repositorios personales](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository).
