# Módulo financiero: primera etapa

Base: `b2e3d0f`, rama `semana-9-rutas-calificaciones`. Sin commit ni push.

## Recorrido disponible

Inicio / menú **Finanzas** → buscar estudiante → estado de cuenta → registrar pago →
recibo → imprimir. El expediente académico abre el mismo estado de cuenta. La confirmación
de matrícula permite continuar directamente a obligaciones y cobro.

Secretaría y Administrador consultan, configuran calendario, registran pagos e imprimen
recibos. Dirección solo consulta (incluidos historial y recibos). Maestro, Estudiante y
Pastor Principal no tienen acceso. Las comprobaciones se realizan en el servidor, antes
de consultar información. Los POST institucionales tienen CSRF; no existen operaciones
de edición ni anulación de pagos en esta etapa. El admin de Pago también queda sin alta
ni modificación: el alta utiliza el servicio transaccional institucional.

## Obligaciones y calendario

- USD 20 de matrícula + cinco mensualidades de USD 20 = USD 120 ordinarios por ciclo.
- Los ciclos solo tienen fechas de inicio y fin; no definen los cinco meses ni el
  vencimiento de matrícula inequívocamente. **Finanzas → Configurar calendario** exige
  emisión, vencimiento de matrícula y cinco meses ordenados y distintos. Cada mensualidad
  vence el día 10; todas las fechas deben quedar dentro del ciclo y no preceder la emisión.
- Se seleccionan los conceptos activos MATRÍCULA y MENSUALIDAD existentes. Si faltan,
  pueden crearse desde esa pantalla, eligiendo explícitamente si permiten abonos. No se
  cambian las políticas de conceptos ya existentes ni se inventan abonos por defecto.
- Configuración JSON por ID de ciclo en `.financiero-local/`, ignorada por Git. Puede
  configurarse otra ruta mediante `FINANCIERO_CONFIG_DIR`. Incluye las fechas del ciclo
  para detectar cambios. Escritura mediante reemplazo atómico y bloqueo del ciclo en BD.
  Se permite configurar inicialmente un ciclo con matrículas históricas, pero no
  reemplazar un calendario guardado cuando el ciclo ya tiene matrículas.
- El servicio académico existente `matricular` crea matrícula, seis inscripciones y seis
  obligaciones dentro de su misma transacción. Un error financiero revierte toda el alta.
  Se mantienen las validaciones y restricciones académicas existentes.
- En un reintento de matrícula existente, no se generan ni se modifican obligaciones
  históricas, becas, descuentos, pagos o inscripciones. No hay un relleno masivo de cargos
  para matrículas antiguas. No se crean señales ni otra lógica de inscripción.

## Saldos, solvencia y pagos

La consulta de saldo usa `monto_final` del modelo (original menos descuento), menos detalles
con pago REGISTRADO y donaciones RECIBIDA, con piso cero, conforme a la vista SQL 17.
Los pagos ANULADO no reducen saldo. Las obligaciones ANULADA permanecen visibles pero no
se suman al saldo exigible. Los descuentos previamente registrados se conservan; no se
implementan nuevos módulos de becas o donaciones.

En PostgreSQL se llama directamente a `estudiante_esta_solvente(id, fecha)` existente,
conservando las tres reglas SQL 15: obligaciones vencidas con saldo sin cobertura válida,
convenios INCUMPLIDO y cuotas vencidas pendientes en convenios ACTIVO. El vencimiento
comienza a afectar solvencia al día siguiente, como en el SQL original. Si la consulta
falla no se muestra al estudiante como solvente. No se modifica el historial académico.

`Obligacion.actualizar_estado` ahora delega en PostgreSQL a la función existente
`recalcular_estado_obligacion(id)` (referenciada por los scripts 14 y 16). Así deja de
sumar pagos anulados con una regla Django incompatible. No se instala ni modifica SQL.

El pago admite EFECTIVO o TRANSFERENCIA y aplicación explícita a una o varias obligaciones.
Usa Decimal; valida positivos, centavos, capacidad del campo, pertenencia al estudiante,
obligación no anulada, saldo disponible, no repetición de una obligación y permite_abonos.
No hay dinero sin aplicar: el total es exactamente la suma de detalles. Las obligaciones
cubiertas por convenios ACTIVO/CUMPLIDO se rechazan para cobro directo: deben usar su flujo
existente de cuotas, fuera de esta etapa, evitando una segunda aplicación incompatible.

El servicio vuelve a verificar el rol y bloquea usuario, estudiante y obligaciones, con
orden determinista, antes de comprobar saldos. Pago, detalles y actualizaciones de estados
se guardan en una transacción; cualquier fallo revierte el conjunto.

## Recibos e idempotencia

La secuencia existente de `pago.id_pago` se reserva con `nextval(pg_get_serial_sequence(...))`.
El número es `IBV-` seguido del identificador correlativo. No se usan MAX+1 ni contadores
en archivos para producción. La unicidad existente y la secuencia protegen la asignación
concurrente. Una reserva firmada, ligada a usuario y estudiante, dura dos horas. Reenviar
el mismo formulario con los mismos datos devuelve el recibo previo sin duplicarlo;
reutilizarlo con datos distintos se rechaza. Los saldos se vuelven a comprobar bajo bloqueo.

La secuencia admite huecos por formularios abandonados o errores, y el orden de reserva
no implica orden de finalización concurrente. No es una numeración fiscal sin huecos.
Abrir un formulario de cobro reserva un identificador, pero no inserta un pago incompleto.
No se cambia ni renumera un recibo anterior. Si falta la secuencia del esquema externo,
el cobro no puede abrirse y requiere revisión; no se crea una nueva sin autorización.

Los recibos nuevos guardan una copia de nombres, identificación del estudiante, registrador
y descripciones de aplicación en el campo existente `Pago.observaciones`, con prefijo
`VIDASYS_RECIBO_V1`. Esta copia preserva el contenido emitido ante futuras correcciones
personales, sin añadir columnas. Los recibos anteriores sin esa copia se muestran con
sus relaciones actuales y una indicación explícita; no se modifican para reconstruir
información histórica inexistente. El estado de anulación, si existe, siempre es visible.

## Verificación realizada

Solo SQLite efímero y datos ficticios. El runner rechaza PostgreSQL, crea tablas de prueba
no administradas y una columna calculada exclusivamente SQLite. Para solvencia, el adaptador
extrae las tres condiciones literalmente del SQL 15; no redefine las reglas en Python.
El recalculado de estados SQLite es un adaptador de prueba; la función PostgreSQL real
no se ejecutó. La reserva SQLite usa un contador exclusivo de pruebas, sin sustituir la
secuencia PostgreSQL de producción.

Se verificaron **13 casos financieros esenciales**:

```sh
python manage.py test financiero.tests --settings=academico.test_settings --noinput
```

La primera ejecución pasó 11 y detectó dos errores en datos ficticios: faltaban fechas
obligatorias del donante y se había construido una combinación de vencimientos que violaba
la unicidad existente. Corregidos los fixtures, se repitieron únicamente esos casos.
Tras añadir preservación del contenido del recibo, se repitieron el recorrido web de
cobro y la reversión atómica de aplicación; ambos aprobaron.

Los casos cubren: seis obligaciones y USD 120, idempotencia e historial, calendario,
reversión completa del alta, pagos/abonos/saldos/donaciones, exclusión de anulados,
excedentes/importes inválidos, recibos únicos y reenvío, aplicación múltiple, reversión
de pagos, reglas de solvencia y convenios, permisos, interfaz de calendario y expediente.

También pasaron **3 comprobaciones directamente relacionadas**:

```sh
python manage.py test \
  academico.test_flujo.FlujoAcademicoTests.test_secretaria_web_y_docente_sin_permiso \
  academico.test_flujo.FlujoAcademicoTests.test_admin_crea_matricula_activa_con_seis_inscripciones \
  core.test_frontend.FrontendInstitucionalTests.test_menu_exacto_por_rol_sin_enlaces_ficticios \
  --settings=academico.test_settings --noinput
```

`manage.py check --settings=academico.test_settings` y `git diff --check`: correctos.

Comprobación Chromium/Playwright: matrícula desde expediente → seis obligaciones por
USD 120 → transferencia ficticia USD 20 → recibo y PDF. Escritorio 1440 px y móvil 390 px,
sin desbordamiento en panel, cuenta, calendario, pago y recibo. Dirección consulta pero
obtiene HTTP 403 al abrir cobro. Capturas/PDF en `/workspace/artifacts/financiero/`, fuera
del repositorio. No se repitió la batería académica completa.

## Requisitos y límites de despliegue

- No se ejecutaron migraciones, DDL, escrituras ni pruebas contra PostgreSQL. No se
  utilizaron registros reales de docentes. No se cambió main ni se hizo commit/push.
- No se añaden modelos ni migraciones. El esquema externo debe contar con las tablas,
  columna calculada `obligacion.monto_final`, funciones y secuencia ya previstas por el
  proyecto. Su presencia y la concurrencia efectiva en PostgreSQL quedan sin validar.
- Los calendarios requieren una carpeta persistente con permisos de escritura. En varias
  instancias, esa carpeta debe compartirse entre ellas; los bloqueos del ciclo se apoyan
  en la misma base PostgreSQL. Debe respaldarse junto a la configuración operativa. Si
  el despliegue exige guardar esta configuración en tablas, hará falta autorizar un
  modelo/migración mínimo antes de aplicarlo; esta entrega no altera el esquema.
- Antes de nuevas matrículas, configurar los calendarios y la política de abonos reales
  desde la interfaz. No se sembraron calendarios ni políticas en PostgreSQL.
- No se implementaron alta/cambios de becas, convenios, donaciones o egresos ni anulación
  de pagos. Se respeta su efecto previamente registrado en saldo y solvencia.

## Archivos añadidos o modificados

- `financiero/calendario.py`, `consultas.py`, `forms.py`, `servicios.py`, `urls.py`,
  `views.py`, `models.py`, `admin.py`: configuración, reglas, endpoints e integridad.
- `templates/financiero/base.html`, `panel.html`, `calendario.html`, `cuenta.html`,
  `pago.html`, `recibo.html`; `static/css/financiero.css`, `static/js/financiero.js`.
- `academico/flujo.py`: generación dentro de la transacción de matrícula existente.
- `config/urls.py`, `templates/core/dashboard.html`, `templates/core/partials/sidebar.html`,
  `templates/academico/estudiantes/expediente.html`,
  `templates/academico/matricula_secretaria.html`: integración institucional.
- `financiero/tests.py`, `financiero/test_sqlite.py`, `academico/test_runner.py`,
  `academico/test_settings.py`, `academico/test_flujo.py`, `core/test_frontend.py`:
  pruebas esenciales, aislamiento y expectativas de navegación actualizadas.
- `.gitignore` y este documento: protección de configuración local e instrucciones.
