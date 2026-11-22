# F5 — Ingresos administrativos y egresos institucionales

## Entrega y decisiones confirmadas

Secretaría y Administración registran ingresos, solicitan egresos y ejecutan pagos
íntegros autorizados desde Finanzas → Ingresos y egresos. Únicamente una cuenta activa
DIRECTORA decide egresos y anulaciones; ni Administración superusuario tiene esa facultad.
No se implementa el rediseño integral de UI/UX pendiente.

Se confirmó expresamente durante F5:

- Solo Administración crea y activa/desactiva categorías en la interfaz institucional.
  Secretaría y Dirección consultan. No hay eliminación ni cambio de nombres de categorías
  usadas desde esta interfaz. Los movimientos históricos se conservan.
- Administración también puede solicitar la anulación de sus propios movimientos. Secretaría
  solicita las de sus propios movimientos. La resolución continúa siendo exclusiva de Dirección.

El importe de una autorización es exactamente el solicitado: no se permite ajustarlo ni
pagar parcialmente. La solicitud original y una instantánea de autorización conservan
importe, directora, fecha y condiciones. Cualquier modificación requiere otra política
institucional; no se implementa por inferencia.

Secretaría consulta sus ingresos y solicitudes de egreso, incluidos los documentos de sus
solicitudes pagadas por Administración. Administración y Dirección consultan todas y los
reportes consolidados. Administración puede desembolsar una solicitud autorizada ajena;
Secretaría solo las propias. Maestro, Estudiante y Pastor Principal no reciben acceso.

## Esquema y reutilización

Se reutilizan las tablas históricas `ingreso`, `egreso`, `categoria_ingreso` y `categoria_egreso`
sin modificar columnas, índices, restricciones ni funciones SQL. No se crean pagos académicos
ficticios. Las migraciones financieras 0001, 0002 y 0003 permanecen idénticas al commit base.

`0004_ingresos_egresos_institucionales` prepara cinco tablas administradas:

| Tabla | Propósito |
| --- | --- |
| `registro_ingreso` | UUID único, vínculo único a Ingreso, concepto, origen, respaldo y datos originales para idempotencia. |
| `solicitud_egreso` | Categoría, concepto, beneficiario, importe, justificación, solicitante/fecha, respaldo, estado, resolución e instantánea autorizada. |
| `desembolso_egreso` | Un desembolso por solicitud y por Egreso, UUID, documento de pago y datos de ejecución. |
| `solicitud_anulacion_operacion` | Origen único ingreso/desembolso, solicitante, motivo, instantáneas, directora y resolución; una pendiente y una aprobada por origen. |
| `comprobante_privado` | Bytes privados, nombre seguro, MIME real, tamaño, SHA-256, operador y fecha. |

La única tabla existente con DDL es `movimiento_caja`, administrada por Django desde F4:
`pago` pasa a nullable, se añaden referencias únicas nullable a Ingreso y Egreso y un CHECK
exige exactamente un origen. Los checks previos de método e importe permanecen intactos.
Las filas académicas anteriores conservan su pago y reciben NULL en los dos campos nuevos.
No se cambia físicamente ninguna tabla `managed=False` ni las funciones de solvencia.

Comprobantes institucionales: `ING-<id_ingreso de diez dígitos>` se deriva del ID existente,
sin nueva secuencia ni columna histórica. Los egresos utilizan `EG-<id_egreso de diez dígitos>`
y la secuencia existente de Egreso en PostgreSQL; una colisión con un número histórico
bloquea la operación por unicidad y requiere revisión, nunca sobrescribe un comprobante.

## Flujos y trazabilidad

### Ingresos

Categoría activa → concepto/origen/importe/método/referencia/fecha/respaldo → caja propia
abierta → Ingreso REGISTRADO + RegistroIngreso + MovimientoCaja en una sola transacción.
Fecha efectiva y fecha/hora de registro se conservan separadamente; no se admiten fechas
futuras. La fecha efectiva puede ser anterior: el movimiento físico se registra en la caja
abierta actual, sin alterar una caja histórica. No se asignan datos retrospectivamente.

No hay referencias a estudiantes, matrículas, obligaciones ni cuotas. Se rechazan categorías
y conceptos que identifiquen matrícula, mensualidad, convenio, donación o padrinazgo,
normalizando acentos y singular/plural. El módulo no aplica dinero a obligaciones ni crea
Pago, DetallePago o AplicacionPagoCuota. Esta validación no puede inferir la naturaleza real
de una descripción deliberadamente falsa: la clasificación institucional requiere supervisión.

UUID identifica reenvíos exactos, incluidos hash de adjunto y todos los datos. Una clave
reutilizada con otros datos se rechaza. Se bloquea además un ingreso del mismo operador con
el mismo conjunto de datos aunque envíe otra clave; debe revisarse el historial antes de
registrar un segundo ingreso realmente distinto. No se interpretan automáticamente
referencias bancarias como identificadores únicos globales.

### Egresos

Solicitud PENDIENTE → resolución APROBADA/RECHAZADA → desembolso efectivo independiente.
Ni solicitar ni aprobar crea Egreso ni mueve caja. Rechazar exige motivo. Las decisiones
son inmutables; reintentos iguales devuelven la resolución, los contradictorios se bloquean.
Una categoría histórica con `requiere_autorizacion=False` no permite saltarse este flujo.

Al desembolsar se exige solicitud aprobada y coherente con sus datos originales y la
instantánea autorizada, categoría activa, caja propia abierta y un único desembolso.
El importe procede exclusivamente del servidor. No se aceptan importe ni directora desde
POST. Se crea Egreso REGISTRADO con autorización original y fecha de pago efectivo,
DesembolsoEgreso, documento y movimiento de caja, todo atómicamente. Transferencia se
registra separadamente; efectivo exige disponibilidad suficiente bajo bloqueo de Caja.

### Caja, integridad y concurrencia

Orden común: Usuario actor → Caja → categoría/origen financiero → solicitud. Solicitar
un egreso y resolverlo no necesitan Caja; mantienen categoría antes de solicitud. Los
servicios académicos de F4 conservan Usuario → Caja → Estudiante → obligaciones → convenio,
cuotas, Pago y solicitud. Ningún servicio nuevo toma Caja después de una categoría/origen.
Se mantienen todos los bloqueos existentes.

Arqueo físico: **fondo + entradas reales de efectivo − salidas reales de efectivo**.
Disponible para desembolsar: **arqueo esperado − entradas anuladas retenidas**.
Las transferencias no se suman al contado físico. Se distinguen cobros académicos, ingresos
administrativos, egresos efectivos, transferencias recibidas/realizadas y efectivo retenido.
No se guardan nuevos totales vivos redundantes; el cierre conserva su fotografía inmutable.

Ejemplo probado: fondo 10 + cobros académicos 100 + ingreso administrativo 30 − desembolso
40 = efectivo esperado 100. La protección de disponible también se aplica a la anulación
académica de F4: se bloquea si el pago respalda desembolsos posteriores y reservarlo dejaría
el disponible negativo. No se cambia el cálculo de obligaciones, becas, convenios o solvencia.

### Anulaciones administrativas

Solicitar no modifica dinero. Dirección compara y confirma con una revisión firmada ligada
a su identidad, solicitud, datos del origen, disponible actual y observaciones. Confirmar
revalida todo bajo bloqueo y exige solicitante con permisos vigentes y caja ABIERTA.
Se conserva el movimiento original, documento y metadatos. Rechazar requiere motivo.

Anular ingreso excluye su importe de ingresos vigentes sin retirar su efectivo físico;
ese efectivo queda retenido y no financia nuevos egresos. Si ya respalda desembolsos, se
bloquea. Anular egreso excluye su importe de gastos vigentes sin recuperar dinero: la salida
física original sigue restando en el arqueo y se identifica separadamente. Las anulaciones
por transferencia no ejecutan correcciones bancarias. No hay devoluciones, recuperaciones,
reaperturas ni ajustes de cajas cerradas. Esos procesos requieren una política posterior.
Una solicitud obsoleta o de caja cerrada todavía se puede rechazar sin tocar el cierre.

Las interfaces nuevas no registran sus modelos en Admin. Ingreso, Egreso y ambos catálogos
históricos quedan solo consulta en Admin para evitar escritura alternativa. No se modifican
los demás módulos financieros. Las garantías institucionales no cubren una escritura SQL
o `QuerySet.update()` hecha por una cuenta externa con privilegios; se detectan discrepancias
críticas de solicitud/autorización/origen antes de ejecutar dinero, sin reparar datos solos.

## Documentos privados

Se aceptan PDF, PNG y JPEG de hasta **5 MiB**. Pillow verifica/decodifica imágenes y limita
sus dimensiones; `pypdf==6.21.4` valida estructura PDF, hasta cien páginas, rechaza cifrado,
acciones activas, JavaScript, formularios y archivos embebidos. Es la única dependencia nueva,
necesaria para analizar PDF reales; requirements-deploy ya incluye requirements.txt.
Se conserva la codificación preexistente del archivo de dependencias.

El nombre provisto por el cliente y su MIME no determinan el almacenamiento: se identifica
el contenido y se genera un nombre UUID con extensión segura. Se conservan exactamente los
bytes aceptados y su SHA-256. La descarga autenticada comprueba propiedad/rol y después
integridad, devuelve attachment con nosniff, CSP sandbox y no-store. No hay MEDIA_URL ni
ruta pública a un archivo; listar movimientos no carga el contenido binario de los adjuntos.

Los bytes se insertan en la tabla nueva dentro de la misma transacción: un rollback no deja
archivos huérfanos. No se versionan adjuntos ni se escriben en el disco de Render. El futuro
PostgreSQL persistente conservaría los documentos frente a la pérdida del disco gratuito,
pero consume su cuota de almacenamiento y necesita respaldo/restauración de BYTEA. Si el
volumen supera esa capacidad, proponer almacenamiento privado persistente externo en una
intervención autorizada, sin contratarlo ahora. No se afirma disponer de antivirus ni de
certificación de inocuidad total; formatos válidos siguen requiriendo supervisión del origen.

## Interfaces, reportes y permisos

Rutas bajo `/finanzas/operaciones/`: panel paginado, `ingresos/nuevo/`, `ingresos/<id>/`,
`egresos/nuevo/`, `egresos/<id>/`, `egresos/<id>/desembolso/`, `comprobantes/<id>/`,
`anular/INGRESO/<id>/`, `anular/EGRESO/<id>/`, `anulaciones/<id>/`, `categorias/` y `reportes/`.
GET no realiza escrituras; los POST conservan CSRF y controles de rol y pertenencia.

Los reportes exclusivos de Dirección/Administración filtran fecha, tipo, categoría, estado,
método y operador; muestran solicitudes, autorizados pendientes, desembolsados y anulados.
En efectivos la fecha es la del movimiento; en solicitudes aún no pagadas es la de solicitud,
ambas expresadas en la zona institucional. Totales por categoría/método cuentan únicamente
movimientos realizados vigentes. Hay impresión y CSV con neutralización de fórmulas del
mecanismo existente. No incluyen ingresos académicos ni prometen consolidación integral F7.

## Validación realizada

**490 pruebas aprobadas: 414 anteriores + 76 nuevas F5**, exclusivamente SQLite en memoria.
Se cubren límites, categorías, UUID y duplicados, permisos/roles cambiados, autorizaciones
inmutables, importe manipulado, pagos únicos, disponible y efectivo retenido, transferencias,
rollback (incluidos documentos), solicitudes obsoletas, cierres, Admin, CSRF, identificadores
ajenos, PDF/imágenes, hash/descarga privada, reportes y CSV. Se conserva toda la suite previa.

Una prueba adicional aplica todas las operaciones de 0004 sobre otra conexión SQLite
`:memory:` con un movimiento y cierre F4 originales; verifica que conserva ambos y no toca
las filas mínimas de tablas históricas. La introspección confirma las cinco tablas nuevas.
El SQL SQLite inspeccionado apunta solo a ellas y `movimiento_caja`, incluidas sus copias
internas `new__...` de reconstrucción. Django check, ausencia de migraciones pendientes y
`git diff --check` pasan. No se ejecutan conexiones a PostgreSQL.

Chromium/Playwright: 40 pantallas de Secretaría, Dirección y Administración, en 1366 y 390 px,
HTTP 200 y sin desbordamientos. Se corrigió el ancho del selector de archivos exclusivamente
en formularios F5. Además se completó un recorrido móvil real: ingreso con adjunto → solicitud
→ aprobación → desembolso con adjunto → anulación administrativa sin recuperación → cierre
cuadrado USD 47.50 en una base ficticia independiente. Se mantiene la identidad gráfica.

## Prueba manual condensada

1. Actualizar el checkout autorizado e instalar dependencias con `python -m pip install -r
   requirements.txt`. No ejecutar migrate sobre la configuración normal ni Neon.
2. Iniciar un ensayo nuevo mediante el lanzador reutilizable SQLite en memoria de la sesión
   anterior. El runner aplica 0004 automáticamente en memoria, prepara las tablas históricas
   ficticias y la solvencia. Usar el mismo proceso `--noreload --nothreading`. No usar solo
   migrate para una base vacía: no crea las tablas `managed=False`. Las credenciales son
   ficticias y se generan para ese proceso; no se guardan en Git.
3. Administración: Finanzas → Ingresos y egresos → Categorías. Crear categorías propias de
   ingreso y egreso. No hay catálogo obligatorio ni se cambian categorías anteriores.
4. Secretaría: abrir caja con fondo 10. Registrar ingreso administrativo en efectivo 30 y
   un PDF/PNG/JPEG. Verificar comprobante ING, respaldo privado y esperado 40.
5. Solicitar egreso 15. Confirmar que no cambia caja. Dirección aprueba y tampoco cambia caja.
6. Secretaría ejecuta el pago efectivo 15: esperado 25. Reenviar el mismo formulario no
   duplica el egreso. Intentar otro egreso en efectivo 26 debe bloquearse; transferencia
   autorizada no disminuye efectivo.
7. Solicitar anulación del egreso pagado; Dirección compara y confirma. Sigue esperado 25:
   el dinero no regresó. El egreso queda ANULADO con historia y documentos conservados.
8. Registrar otro ingreso 20, anularlo mientras caja sigue abierta: esperado físico 45,
   disponible 25, retenido 20. No se puede financiar un egreso 26 con ese efectivo retenido.
9. Cerrar con contado físico 45; diferencia cero. Dirección/Admin consultan fotografía,
   impresión y CSV. Intentar anular un movimiento de esa caja debe bloquearse.
10. Verificar desde roles no autorizados que no se vean formularios, documentos ni reportes
    internos, y que Secretaría no consulte movimientos de otro operador.

Comandos de regresión (entorno virtual activo y variables de conexión ficticias):

```powershell
$env:SECRET_KEY='solo-pruebas-aisladas'
$env:DB_NAME='unused'; $env:DB_USER='unused'; $env:DB_PASSWORD='unused'
$env:DB_HOST='127.0.0.1'; $env:DB_PORT='1'
python -B manage.py test --settings=academico.test_settings --noinput
python -B manage.py check --settings=academico.test_settings
python -B manage.py makemigrations --check --dry-run --settings=academico.test_settings
```

## Archivos de la entrega

Nuevos: `financiero/comprobantes.py`, `operaciones.py`, `operaciones_models.py`,
`operaciones_forms.py`, `operaciones_views.py`, `test_operaciones.py` y
`financiero/migrations/0004_ingresos_egresos_institucionales.py`;
`templates/financiero/operaciones/` con panel, form, ingreso, egreso, anulacion,
categorias y reporte (siete plantillas); este documento técnico.

Modificados: `financiero/admin.py`, `anulaciones.py`, `caja.py`, `caja_models.py`,
`models.py` y `urls.py`; `requirements.txt`; `static/css/financiero.css`;
`templates/financiero/panel.html`, `caja/detalle.html` y `caja/totales.html`;
`docs/manuales/modulo_financiero.md`. Total: **27 archivos**.

Los ingresos/egresos históricos sin metadatos institucionales F5 no se importan,
reclasifican ni asignan retrospectivamente a Caja. Se conservan en sus modelos y
mecanismos de consulta previos; no se mezclan sus importes sin clasificación con
los reportes institucionales nuevos. Su eventual regularización requiere revisión.

## Pendientes antes de PostgreSQL o despliegue

No se accedió a Neon, no se migraron bases persistentes ni se desplegó. Antes de incorporar
0004 en una base existente, con autorización separada: respaldo verificable y restauración
ensayada; revisar historial 0001–0003 y columnas/restricciones reales; generar/revisar SQL
PostgreSQL en una instancia aislada; comprobar que solo modifica `movimiento_caja` y crea
las cinco tablas nuevas; probar migración con datos F4 y recuperación ante fallos.

Verificar allí los estados REGISTRADO/ANULADO y tipo_comprobante INTERNO contra las
restricciones reales de Egreso, secuencia/privilegios de egreso, índices únicos parciales,
FK, BYTEA, checks y bloqueos simultáneos de cobro/desembolso/anulación/cierre. SQLite no
certifica bloqueos de fila ni triggers PostgreSQL. Ante incompatibilidad detener esa
incorporación: no alterar restricciones históricas automáticamente. Conceder únicamente
los permisos necesarios sobre tablas/secuencias nuevas. No desactivar las guardias demo ni
usar el inicializador de base vacía sobre una base existente.

No revertir/dropear tablas después de registrar operaciones reales: parar escrituras,
preservar documentos/historial y recuperar conforme a un plan autorizado con respaldo
completo. Los cierres anteriores permanecen con su foto original, sin rellenar totales F5.

Siguen pendientes F7, donaciones/padrinazgos, devoluciones/recuperaciones y ajustes tras el
cierre, y el rediseño integral de UI/UX ya registrado. No forman parte de este commit.
