# Preparación PostgreSQL y primer despliegue de demostración

Base: `abbd0f32f779996a8859f4d49325e7508323d5e6`. No es autorización de producción.

## Cambios de esquema previstos, antes de aplicarlos

Se preparará exclusivamente una base NUEVA y vacía `vidasys_demo_test` en un clúster local
separado, sin acceso ni copia de `gestion_ibv`. El comando de preparación deberá rechazar
otras bases y cualquier esquema que ya contenga tablas. No se ejecutará sobre la base real.

El esquema sintético de demostración contendrá las tablas de modelos Django y sus
restricciones declaradas, incluidas relaciones OneToOne, unicidades y secuencias identity.
Se agregará la columna PostgreSQL calculada `obligacion.monto_final`, ausente del mapeo ORM
porque el modelo utiliza una propiedad. Se instalarán los scripts versionados 15, 16
(portal), 17 y 14 (resumen), solamente CREATE FUNCTION/VIEW. Los scripts de pruebas que
cambian registros no se ejecutarán.

No se dispone del DDL inicial ni de la definición de `recalcular_estado_obligacion` del
sistema original. Se preparará una definición PARA DEMOSTRACIÓN, versionada por separado,
que reutiliza el saldo del SQL 17 (pagos REGISTRADO y donaciones RECIBIDA). Conservará
ANULADA y derivará PAGADA/PARCIAL/PENDIENTE/VENCIDA. Su comportamiento no certifica los
triggers o restricciones del esquema original, que deberán contrastarse con un export
solo de esquema autorizado. No se alterará esa función en ninguna base existente.

El comando no usa `migrate`, no modifica `managed=False` ni genera migraciones para las
aplicaciones. Construye solo el esquema nuevo de demostración y deja claro su origen.
No se añadirá una tabla de calendario: la configuración se conservará en un volumen
persistente compartido, evitando una modificación de esquema operativo innecesaria.

El esquema sintético incluye un trigger al cambiar el estado de un pago, para recalcular
sus obligaciones con la función de demostración. Ningún trigger/función real se sustituye.

## Resultado de la compatibilidad comprobada

Instancia local preparada: PostgreSQL **17.11**, clúster independiente en
`/workspace/.demo-vidasys/pgdata`, socket privado y puerto 55432, sin escucha TCP.
Base `vidasys_demo_test`; rol `vidasys_demo` sin SUPERUSER/CREATEDB/CREATEROLE. Este
clúster no contiene `gestion_ibv`. No se consultó ni copió la base real. La identidad
de base/rol se comprueba al conectar mediante `settings_demo_pg`.

Se ejecutaron únicamente los recorridos relevantes en el motor real, sin volver a
las baterías completas previamente aprobadas:

- Alta con seis inscripciones, seis obligaciones y USD 120; reintento sin duplicados.
- Reversión completa de matrícula/inscripciones/obligaciones ante fallo financiero.
- Pago con `nextval` nativo, reenvío sin duplicación y anulación excluida del saldo.
- Dos conexiones simultáneas: recibos únicos y aplicaciones correctas al saldo.
- Competencia por un saldo: un cobro aprobado y el otro rechazado al superar el remanente.
- Reversión de pago/detalles/estado ante fallo en la aplicación.
- Vistas SQL nativas de estado de cuenta y portal, y función de solvencia.
- Portal propio HTTP 200, módulo financiero administrativo HTTP 403 para ESTUDIANTE,
  recibo ajeno HTTP 404. Datos y cuentas ficticios exclusivamente.
- Calendario leído desde otro proceso, sin depender de caché o memoria del servidor.
- Gunicorn 23 con dos workers y `DEBUG=False`; archivos estáticos con manifiesto WhiteNoise.
- HTTPS **solo local**, con un certificado de prueba confiado explícitamente (sin omitir
  verificación TLS): health/login/static HTTP 200, login real con CSRF, cookies Secure y
  HttpOnly, portal/cuenta HTTP 200, redirección HTTP → HTTPS 301.
- `manage.py check --settings=config.settings_demo_pg` y `git diff --check`: correctos.

La primera apertura del portal detectó que faltaba `collectstatic`; se ejecutó ese paso
normal de despliegue y se continuó desde la comprobación afectada, sin repetir las
operaciones ya verificadas. Los archivos generados están ignorados. Las contraseñas
conocidas de fixtures se deshabilitaron al terminar; no hay credenciales públicas de demo.
Los secretos locales y la clave TLS están fuera del repositorio, en una carpeta privada.

### Diferencias relevantes frente a SQLite

PostgreSQL sí aplica bloqueos de fila reales: se comprobaron transacciones y concurrencia
con conexiones distintas. Los recibos usan su secuencia nativa, no el contador de pruebas
SQLite. `obligacion.monto_final` es una columna generada STORED en PostgreSQL, mientras
que el ORM expone una propiedad y no la incluye en INSERT/UPDATE. Se verificaron las
funciones PL/pgSQL y vistas LATERAL reales, no el adaptador SQLite.

Django usa normalmente sesiones de BD en UTC con USE_TZ. Para que `CURRENT_DATE` de las
funciones/vistas coincida con la fecha institucional, el despliegue configura la sesión
PostgreSQL en `America/El_Salvador`. Se comprobó la igualdad con `timezone.localdate()`;
esto no altera registros ni cambia el instante almacenado en campos timestamptz.

No se detectaron bloqueos adicionales de los modelos/consultas ejercitados. **No queda
certificado el esquema histórico**: faltan su DDL completo, definición original de
`recalcular_estado_obligacion`, triggers, defaults y CHECK externos no representados en
Django. Tampoco se ensayó PostgreSQL 18 ni se construyó la imagen Docker; el proceso
Python/Gunicorn sí se ejecutó directamente. La función/trigger demo son exclusivos del
esquema nuevo, no un parche autorizado para una base existente.

## Persistencia financiera

`FINANCIERO_CONFIG_DIR` es obligatorio y absoluto en despliegue. No debe apuntar al
filesystem efímero del contenedor. `deploy/compose.demo.yml` monta el volumen nombrado
`vidasys_calendarios_demo` en `/data/calendarios`. Conservarlo al recrear contenedores;
**no usar `docker compose down -v`** si se desean conservar los calendarios.

Dos workers/procesos sobre el mismo volumen leen los mismos archivos y usan los bloqueos
del ciclo en PostgreSQL para serializar configuración y matrícula. En varias máquinas,
se necesita un filesystem persistente **compartido** con reemplazo atómico (por ejemplo,
NFS o un volumen ReadWriteMany); no se ha provisionado uno ni se presupone que el hosting
lo ofrezca gratis. Volúmenes locales independientes por réplica NO son equivalentes.
Para una primera demo basta una instancia con volumen persistente y varios workers.

Respaldar BD y carpeta de calendarios de forma coordinada: los archivos referencian IDs
de ciclo y conceptos. No copiarlos sobre otra BD con IDs distintos sin validación.
No se sustituyó esta configuración por una tabla ni se modificó el esquema real.
Los recibos conservan unicidad por secuencia y restricción existente; se mantienen posibles
huecos por reservas abandonadas/rollback. Los registros históricos no se renumeran.

## Primer despliegue: instrucciones

Estos pasos preparan un proveedor **todavía no elegido**. No se creó ningún servicio
externo o de pago ni se publicó un dominio.

1. Elegir un host/servicio con PostgreSQL independiente y almacenamiento persistente.
   Crear una BD NUEVA `vidasys_demo`, con usuario limitado propietario de ese esquema,
   sin acceso a `gestion_ibv` ni privilegios de administración del clúster. El comando
   de preparación rechaza objetos existentes y no intenta repararlos ni borrarlos.
   No utilizar el usuario postgres/superusuario como credencial de la aplicación.
2. Instalar Python 3.12 y dependencias con `pip install -r requirements-deploy.txt`, o
   construir el Dockerfile. Copiar `deploy/.env.demo.example` a `deploy/.env.demo`
   (ignorado) y completar las variables mediante el almacén seguro del proveedor.
   Generar SECRET_KEY aleatoria de al menos 50 caracteres con una herramienta segura;
   no reutilizar la clave de desarrollo ni pegar credenciales en chat o Git.
3. Configurar hosts concretos en ALLOWED_HOSTS, orígenes completos `https://...` en
   CSRF_TRUSTED_ORIGINS, conexión PostgreSQL y TLS con `DB_SSLMODE=verify-full` y la CA
   del proveedor si hace falta (`DB_SSLROOTCERT`, montada como archivo, no incluida en
   la imagen). El valor `disable` se usó únicamente en el socket Unix local aislado.
4. Montar el calendario persistente y asignar permisos al usuario del proceso (UID 10001
   en el Dockerfile). El contenedor no ejecuta como root. Configurar el proxy HTTPS y
   el dominio. Activar TRUST_PROXY_HTTPS solo si ese proxy sobrescribe X-Forwarded-Proto
   y el backend está inaccesible directamente; definir PROXY_ALLOWED_IPS según su red.
   Caddyfile.example es solo una referencia y no fue iniciado públicamente. El proveedor
   debe entregar un certificado válido y limitar el puerto HTTP interno del backend.
5. Tras autorizar el destino de demo nuevo/vacío, cargar el esquema explícitamente y
   preparar una cuenta administrativa de demo mediante terminal segura. No importar
   usuarios o datos reales ni reutilizar las contraseñas de fixtures:

```sh
# Variables seguras ya cargadas en el proceso (no usar la .env de la base real).
export DJANGO_SETTINGS_MODULE=config.settings_demo_pg
python manage.py preparar_demo_pg --confirmar
python manage.py createsuperuser
python manage.py check
sh deploy/start.sh
```

`preparar_demo_pg` es una operación única de esquema nuevo; una repetición sobre tablas
existentes aborta sin cambios. **No ejecutar migrate para las tablas unmanaged**, no
falsear migraciones ni intentar reparar la base real. La demo ya preparada se inicia
sin volver a ejecutar el comando de esquema. Crear cuentas ficticias de los otros roles
y vincular cada estudiante solo tras verificar la identidad de demostración.

`deploy/start.sh` ejecuta check, collectstatic y Gunicorn; no migra ni siembra datos. El
proveedor puede dar PORT, WEB_CONCURRENCY y la IP de proxy. Las variables de producción
no se incluyen en la imagen. Para contenedor local, el ejemplo Compose publica únicamente
`127.0.0.1:8001` y conserva el volumen. No proporciona por sí solo una BD ni HTTPS público.
No se inicia Docker/Compose ni se contrata infraestructura desde esta entrega.

Antes de compartir: comprobar `/healthz/` (solo indica disponibilidad, no credenciales),
login, estáticos, un recorrido por rol y que teléfono/computadora llegan al mismo dominio
HTTPS con certificado válido. Verificar aislamiento de BD y que el volumen sobrevive a
recrear el contenedor. Ajustar los respaldos y comprobar que una réplica no usa otro
filesystem. HSTS inicial de una hora, sin preload ni extensión a subdominios: revisar esa
política con el dominio definitivo, sin habilitarla indiscriminadamente sobre otros sitios.

## Archivos preparados/modificados

- `config/settings_deploy.py`, `settings_demo_pg.py`: despliegue seguro, TLS PostgreSQL,
  hosts/CSRF, estáticos, timezone y guardia de destino/rol de demo.
- `config/settings.py`: ruta financiera configurable por entorno.
- `core/management/commands/preparar_demo_pg.py` y
  `database/scripts/demo_recalcular_estado.sql`: esquema sintético, únicamente en BD vacía.
- `core/health.py`, `config/urls.py`: comprobación mínima de disponibilidad.
- `requirements-deploy.txt`, `deploy/start.sh`, `deploy/gunicorn.conf.py`: dependencias y arranque.
- `Dockerfile`, `.dockerignore`, `deploy/compose.demo.yml`, `deploy/.env.demo.example`,
  `deploy/Caddyfile.example`: preparación de contenedor, variables y proxy; no desplegados.
- `.gitignore` y este documento.

## Decisiones pendientes de autorización

- Proveedor/host, dominio HTTPS y disponibilidad/coste de volumen persistente; no se creará
  un servicio de pago sin autorización. Confirmar proxy/red/CA según ese proveedor.
- Autorizar la publicación pública de la demo y la creación de su BD independiente allí.
- Para conectar alguna vez datos/esquema institucionales: aportar un export **solo de
  esquema, sin credenciales ni datos personales**, y revisar sus diferencias con la demo
  antes de aprobar cambios. Esta entrega no autoriza tocar `gestion_ibv` ni certificarla.
- Commit/push siguen sin realizarse y requieren la autorización solicitada por el usuario.

## Actualización de preparación final (base 5672d03)

La propuesta de volumen de archivos descrita arriba se conserva como antecedente, pero
para la demo gratuita el calendario pasa a PostgreSQL JSONB. La configuración web demo
lo exige; no depende de un disco efímero ni de un volumen de pago. Consultar
[demo_gratuita.md](demo_gratuita.md) para el esquema nuevo, instrucciones vigentes,
semilla ficticia, recuperación y requisitos de alojamiento. No aplicar cambios a ninguna
base existente ni usar los comandos históricos de archivo como receta de publicación.
