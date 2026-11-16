# Primera demo gratuita: preparación final

Base publicada `5672d03`. Documento de preparación; no autoriza publicación ni producción.

## Decisión de persistencia, antes de aplicar esquema

Para un servidor web gratuito con disco efímero se almacenará el calendario en PostgreSQL.
Se añadirá `calendario_financiero`: `id_ciclo` PK/FK uno a uno hacia ciclo_academico,
`datos` JSONB y `fecha_actualizacion` timestamptz. Los datos conservan las mismas fechas,
conceptos, período y validaciones del calendario anterior; no cambian tarifas ni saldos.
El bloqueo del ciclo y la escritura del calendario comparten transacción PostgreSQL.

El modelo será unmanaged y la tabla se contemplará en la inicialización de una base demo
NUEVA y vacía. No se generará ni aplicará una migración sobre bases existentes. La base
real y la demo de pruebas anterior no se modificarán. Un despliegue sobre un esquema
existente sin esta tabla debe detenerse y requerir una modificación aprobada por separado.
No se copiarán archivos de calendario automáticamente ni se adivinarán IDs.

Se conserva el backend de archivo para desarrollo y la receta de volumen existente como
alternativa histórica; la configuración de demo web exigirá PostgreSQL para el calendario.
Así el calendario sobrevive a reinicios/despliegues y todas las réplicas comparten la BD.

## A. Arquitectura recomendada

**Render Web Service gratuito (Docker) + proyecto Neon gratuito separado (PostgreSQL).**
Navegadores de escritorio/móvil → HTTPS del dominio asignado por Render → Gunicorn/Django
→ PostgreSQL de Neon. WhiteNoise sirve estáticos del contenedor. Sesiones, usuarios,
matrículas, finanzas y calendario JSONB residen en la BD persistente y compartida; el
contenedor web puede reiniciarse sin perder el calendario. No se necesita disco web de pago.
La configuración Render utiliza un worker para reducir memoria en la demo pequeña.

Los seis roles usan la misma aplicación y sus permisos actuales. PASTOR_PRINCIPAL conserva
su inicio limitado; no se le agregan módulos. ESTUDIANTE sigue sujeto a vínculo y solvencia;
no se amplían sus permisos por tratarse de una demo.

**Límites gratuitos por confirmar antes de crear recursos:** disponibilidad del plan Docker
gratuito, suspensión/cold start por inactividad, cuotas de cómputo, almacenamiento,
transferencia y conexiones de BD. No hay garantía de SLA ni de gratuidad indefinida. No
activar escalado/upgrade pagado. Verificar condiciones de conservación de datos e inactividad
para no depender de una base con vencimiento de prueba. Evitar usar una BD de prueba con
caducidad como única copia. Mantener un respaldo manual antes de la entrega académica.
No se proponen keep-alives artificiales para eludir políticas del proveedor.

Referencias oficiales a revisar por el operador:
- https://render.com/docs/free
- https://render.com/docs/deploy-django
- https://neon.com/docs/introduction/plans
- https://neon.com/docs/connect/connect-from-any-app

La red de este entorno devolvió 403 al intentar consultar los planes oficiales; **no se
verificaron cuotas ni condiciones comerciales vigentes**. La recomendación es técnica y
condicionada a que los planes gratuitos sigan disponibles y cumplan la entrega. No se
abrió ninguna cuenta ni se creó un recurso externo. Si no hay una opción realmente gratuita,
detener la publicación y elegir otra opción con el usuario, sin contratar servicios.

## B. Preparación disponible

Los 17 archivos locales originales fueron respaldados fuera del checkout y conservados
como archivos existentes; se aprovecharon y actualizaron los necesarios. No se descartó
trabajo anterior. Docker/Gunicorn/dependencias, healthcheck, configuración de demo y scripts
SQL siguen formando parte de la preparación.

- `render.yaml`: una web Docker con plan `free`, rama explícita, despliegue automático
  desactivado, healthcheck, SECRET_KEY generada por el proveedor y credenciales DB sin
  valores en el archivo. No declara bases, discos ni recursos de pago.
- `Dockerfile`, `requirements-deploy.txt`, `deploy/start.sh`, `deploy/gunicorn.conf.py`:
  ejecución no root; check → preflight de esquema de solo lectura → collectstatic → Gunicorn.
  También los comandos manuales del contenedor usan por defecto settings_demo_pg.
- `config/settings_demo_pg.py`: nombres de base permitidos, conexión/SECRET_KEY explícitas,
  rol PostgreSQL limitado, clúster sin una BD llamada gestion_ibv; bloquea migrate/flush/test.
- `config/settings_deploy.py`: DEBUG=False, hosts concretos, CSRF HTTPS, cookies Secure y
  HttpOnly, TLS verify-full para PostgreSQL remoto, CA del sistema o configurada y timezone
  institucional. En Render los hosts/orígenes se derivan de RENDER_EXTERNAL_HOSTNAME si
  no se proporcionan explícitamente; no se toman de la .env local de desarrollo.
- `financiero/models.py`, `financiero/calendario.py`, `config/settings.py`: almacenamiento
  JSONB compartido para la demo y compatibilidad del backend de archivo en desarrollo.
  `academico/test_settings.py` fija archivo para conservar el aislamiento de baterías previas.
- `core/demo_preflight.py`, comando `verificar_demo_pg`: comprueba tablas, unicidades,
  relaciones críticas, funciones, vistas, columna calculada, calendario JSONB y secuencia
  sin crear ni modificar registros.
- `preparar_demo_pg`: crea únicamente un esquema nuevo y vacío a partir de los modelos y
  SQL versionado, incluida calendario_financiero. Una base con objetos se rechaza.
- `sembrar_demo_pg`: datos ficticios y seis cuentas con claves aleatorias fuera del checkout,
  STATIC_ROOT y MEDIA_ROOT; archivo nuevo 0600, sin mostrar valores en logs. Rechaza datos
  de aplicación existentes y exige elegir explícitamente políticas de abonos de la demo.
- `core/health.py`: devuelve solo disponibilidad (incluye objetos SQL esenciales), sin
  nombres de BD, usuarios ni credenciales.
- `.gitignore`, `.dockerignore`: excluyen .env anidados, claves de demo y respaldos.
- `deploy/compose.demo.yml` y `Caddyfile.example`: conservados como alternativa de un host
  propio. El volumen antiguo permanece en la receta; la demo gratuita no depende de él.
- Este documento, el antecedente `preparacion_postgresql.md` y la actualización del manual
  financiero explican la evolución y los requisitos. Los pasos de este documento prevalecen
  para la demo gratuita.

## C. Requisitos externos pendientes

1. Autorizar por separado commit/push del paquete de despliegue y publicación pública.
2. El operador debe verificar planes gratuitos y crear un **proyecto Neon nuevo**, exclusivo
   para datos ficticios. No reutilizar servidor/proyecto/credenciales de gestion_ibv.
3. Crear allí una BD `vidasys_demo` y un rol `vidasys_demo` propietario de su esquema, sin
   SUPERUSER, CREATEDB, CREATEROLE, REPLICATION ni BYPASSRLS. La aplicación rechaza roles
   administrativos o un clúster que contenga gestion_ibv. No usar el rol principal del
   proveedor como credencial de la aplicación si no cumple estas restricciones.
4. Obtener endpoint directo, contraseña y CA TLS del proyecto nuevo por los mecanismos
   seguros del proveedor. Para esta demo pequeña es más sencillo el endpoint directo;
   no se ha validado un pooler de transacciones de terceros.
5. Autorizar a Render el acceso al repositorio/rama y confirmar dominio HTTPS asignado,
   proxy que sobrescribe X-Forwarded-Proto y puerto interno no accesible directamente.
   La configuración de confianza del proxy del blueprint solo es válida en ese escenario.
6. No proporcionar claves en chat ni incluirlas en Git. SECRET_KEY estable y secretos DB
   van en el panel seguro del proveedor; usar la misma configuración en el terminal local
   autorizado para inicializar. No registrar cookies o archivos de credenciales como logs.

## D. Compatibilidad y comprobaciones esenciales

Se utilizó una BD **local nueva `vidasys_demo`** en el clúster independiente de la preparación
previa, sin conectar a gestion_ibv y sin alterar la BD `vidasys_demo_test` anterior. No se
aplicaron migraciones a ninguna base existente ni se repitieron las baterías funcionales.

Comprobado:
- Inicialización del esquema sintético nuevo con calendario JSONB y semilla ficticia.
- Preflight de tablas, PK/uniques, FK críticas, funciones y vistas SQL, monto_final STORED
  y secuencia identity de pago. La secuencia se consulta sin consumir nuevos recibos.
- Calendario leído desde otro proceso con una ruta de archivos deliberadamente inexistente:
  no depende de la memoria ni de un archivo web. El calendario se respalda con la BD.
- Un nuevo caso de compatibilidad PostgreSQL: dos administradores ficticios intentan
  desactivarse simultáneamente; una operación se rechaza y queda uno activo. Se retiraron
  únicamente esos actores temporales y se conservó el administrador de la semilla.
- Configuraciones que apuntan a gestion_ibv, intentan migrate, usan calendario de archivo
  en demo o TLS remoto desactivado son rechazadas antes de abrir conexión remota.
- Derivación de dominio Render, CSRF, DEBUG y cookies seguras, sin conectar a un proveedor.
- Sintaxis/coherencia de Compose y blueprint Render sin crear recursos.

Los servicios de recibos/pagos conservan el código publicado y la secuencia/transacciones
PostgreSQL verificadas en la preparación previa. No se volvieron a ejecutar las pruebas
funcionales de matrícula, pagos o portales. El nuevo preflight comprueba sus prerrequisitos;
la semilla usa el servicio existente de matrícula con seis obligaciones, sin duplicarlo.

La construcción Docker del entorno inicialmente encontró una CA de proxy desconocida.
Se restauró confianza con una **copia temporal del Dockerfile y un secreto BuildKit con
el bundle CA**, manteniendo TLS. No se añadió esa CA al repositorio ni a capas de imagen.
El Dockerfile del proveedor mantiene los certificados normales de la imagen. No se cambian
versiones para ocultar fallos TLS ni se utiliza trusted-host/--insecure.

### Riesgos que impiden publicar sin resolverlos

- No se han confirmado los planes gratuitos actuales ni se han aprovisionado credenciales,
  dominio y proyecto aislado. No declarar que una web pública ya funciona.
- No iniciar contra la demo antigua sin calendario_financiero ni aplicar ALTER/migrate
  para repararla automáticamente. Usar una base nueva o solicitar aprobación del esquema.
- La definición de recalcular_estado_obligacion es una definición de DEMO. Falta el DDL
  original completo y sus CHECK/triggers para certificar el sistema histórico. Esta demo
  usa solo registros ficticios; no es un despliegue de la base institucional.
- No publicar si falla preflight, TLS, aislamiento, provisión de administrador o acceso a
  secretos. No resolverlo activando DEBUG, permisos de superusuario o desactivando SSL.
- Calendarios en archivo o réplicas con almacenamiento local separado no son válidos para
  esta arquitectura. La demo web los rechaza.
- Las copias de seguridad del proveedor pueden estar limitadas en el plan gratuito. Tener
  un pg_dump privado y una prueba de recuperación en otro proyecto nuevo antes de depender
  de la demo para información importante. No se habilita producción ni se cargan datos reales.

## E. Primer despliegue, después de autorización

### 1. Revisar y publicar código

Revisar los archivos pendientes y autorizar su commit/push en semana-9-rutas-calificaciones.
No usar main. Render no podrá usar estos cambios hasta que estén publicados; esta tarea
no hizo commit ni push. No activar despliegue automático en cada commit.

### 2. Crear exclusivamente la base de demostración externa

Tras verificar la gratuidad y autorizar recursos, crear el proyecto Neon nuevo, BD y rol
limitado indicados. Elegir PostgreSQL 17 si está disponible, que es la versión local
verificada; otras versiones del proveedor requieren comprobar compatibilidad, sin asumirla.
Copiar credenciales únicamente a configuración privada, por ejemplo deploy/.env.demo
(ignorada), con las variables del ejemplo. Usar SSLMODE=verify-full y CA válida. No copiar
la .env actual de desarrollo ni un dump de la base real.

### 3. Inicializar desde un terminal autorizado, no desde logs del hosting

Instalar dependencias de requirements-deploy.txt en un entorno virtual. Cargar las variables
privadas en el proceso sin imprimirlas, comprobar host/proyecto y ejecutar:

```sh
export DJANGO_SETTINGS_MODULE=config.settings_demo_pg
python manage.py check
python manage.py preparar_demo_pg --confirmar
python manage.py verificar_demo_pg
python manage.py sembrar_demo_pg --confirmar \
  --credenciales /ruta/privada/vidasys.demo-credenciales.json \
  --abonos-matricula no --abonos-mensualidad no
```

La carpeta privada debe existir, ser accesible solo al operador y quedar fuera del checkout,
STATIC_ROOT y MEDIA_ROOT. El archivo no debe existir previamente; se crea 0600. Guardarlo
solo localmente en un lugar seguro, no en disco efímero de Render ni en variables visibles.
No publicar su contenido. Cambiar claves temporales al ingresar y compartir cada una solo
con su destinatario por canal seguro.

La semilla crea seis roles, un docente y estudiante FICTICIOS vinculados explícitamente,
un ciclo próximo, seis materias/cursos, calendario, matrícula y obligaciones por USD 120,
una asistencia y una nota de ejemplo. No registra dinero ficticio como cobro automático.
Las opciones `no` son políticas explícitas para esta demostración, no una aprobación de
política institucional real. Puede elegirse `si` antes de sembrar si se desea demostrar
abonos, sin modificar las tarifas confirmadas. No volver a sembrar una base con datos.

Si se prefiere una demo sin datos de ejemplo, omitir la semilla, crear el administrador
con createsuperuser y configurar solo datos ficticios por la interfaz autorizada. No usar
ambos procedimientos de arranque consecutivamente: la semilla exige la aplicación vacía.

### 4. Configurar la web gratuita

Revisar render.yaml con el esquema vigente del proveedor y crear solo el Web Service
Docker gratuito desde la rama indicada. SECRET_KEY debe ser aleatoria, de al menos 50
caracteres, estable entre despliegues y diferente de la local. Completar DB_HOST/DB_PASSWORD
y comprobar que DB_NAME/DB_USER son del proyecto demo. No crear discos ni base Render de
pago desde el blueprint.

El dominio Render se configura automáticamente para hosts/CSRF mediante su variable oficial;
para dominio propio, fijar ALLOWED_HOSTS sin esquema y CSRF_TRUSTED_ORIGINS con https://.
Confirmar TLS y proxy privado antes de aceptar TRUST_PROXY_HTTPS=True/PROXY_ALLOWED_IPS=*.
Fuera de ese proveedor, fijar las IP de proxy reales y no confiar en headers de clientes.

Docker arranca check → verificar_demo_pg → collectstatic → Gunicorn. No migra ni siembra
al iniciar. Healthcheck /healthz/ devuelve 200 únicamente si puede consultar la BD y están
los objetos esenciales; si falla, el despliegue debe mantenerse no disponible.

### 5. Entrega de demostración

Después de aprobar la publicación, comprobar certificado HTTPS válido y la misma URL desde
computadora/teléfono. Ingresar cada cuenta ficticia, cambiar la clave temporal y verificar
el recorrido autorizado. PASTOR conserva sus límites; alumno no ve datos ajenos ni notas
si queda insolvente. Estas comprobaciones externas siguen pendientes: no se realizaron
contra Render/Neon en esta tarea. Prever cold start antes de la exposición, sin eludir las
políticas gratuitas. No cambiar los calendarios ni perderlos al reiniciar el servicio web.

### 6. Respaldo y recuperación

Respaldar la BD demo con pg_dump en formato custom, sin propietario/ACL. Conservar el archivo
fuera del repositorio, con permisos privados y umask 077. La tabla JSONB incluye calendarios;
no existe una segunda carpeta que deba conciliarse con IDs de otra base. Mantener SECRET_KEY
en el gestor seguro del proveedor; no incluirla en el dump ni en documentación.

Para restaurar, usar otro proyecto/BD demo NUEVO y vacío, verificar aislamiento y restaurar
con pg_restore --exit-on-error --no-owner --no-privileges. No usar --clean contra una base
existente. Tras restaurar, ejecutar solo verificar_demo_pg; no preparar_demo_pg, migrate ni
sembrar_demo_pg sobre el respaldo restaurado. Cambiar las variables privadas de la web al
nuevo proyecto tras la comprobación autorizada y conservar la copia anterior para reversión.
La secuencia de pagos forma parte del dump; no resetear ni renumerar recibos.

Si falló una inicialización, no borrar por prefijos ni reintentar a ciegas. Esquema y semilla
utilizan transacciones; un fallo normal revierte sus cambios. Un cierre abrupto puede dejar
un archivo de claves sin confirmar la transacción: inspeccionar privadamente si hay cero
cuentas o seis antes de decidir, sin mostrar hashes/claves ni sustituir cuentas ya creadas.
Si existen datos, no repetir semilla. Ante pérdida de acceso, el operador autorizado puede
usar changepassword sobre la cuenta ficticia identificada, con settings_demo_pg y el destino
demo comprobado; no recuperar ni mostrar claves anteriores. Conservar el cambio obligatorio.

Si falla la web: revisar configuración y mensajes de error sin volcar entorno/secretos,
confirmar BD/CA/rol/objetos con verificar_demo_pg y publicar manualmente la versión anterior
compatible. No ampliar permisos ni suprimir TLS para desbloquear. No activar un plan pagado
como solución automática a un límite gratuito.

### Estado final de construcción y seguridad

La imagen Docker se construyó con los pins existentes y TLS verificado. En este entorno
solo, se usó una copia temporal del Dockerfile con secreto BuildKit para la CA del proxy;
la CA no queda en capas ni en el repositorio. La receta de Render no requiere esa CA local.
El contenedor se comprobó sin red: configuración demo, usuario no root y collectstatic;
no contiene .env de desarrollo/despliegue ni el secreto CA de sesión. No se ejecutaron
baterías funcionales dentro de Docker.

`check --deploy` detectó el backend de correo de consola heredado. La demo ahora define
MAILERS vacío: no hay SMTP ni envío de correo, y los resets siguen siendo manuales. No se
finge un servicio inexistente ni se imprimen mensajes con claves. Son advertencias
intencionales mail.W001 (correo no disponible), security.W005 (sin HSTS para subdominios)
y security.W021 (sin preload). No se silencian los checks ni se habilitan políticas que
el operador no controla sobre el dominio del proveedor. Esto no sustituye la autorización
ni una revisión para producción.
