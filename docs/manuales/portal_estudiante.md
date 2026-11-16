# Portal del estudiante

Implementación sobre `507a363`, rama `semana-9-rutas-calificaciones`. Sin commit ni push.

## Recorrido

El login Django existente conserva su autenticación y dirige las cuentas ESTUDIANTE a
`/portal/` a través del inicio institucional. La navegación compartida ofrece Inicio,
Mis materias y resultados y Mi estado de cuenta. El portal es exclusivamente de consulta.

- Inicio: nombre personal y código; para cuentas habilitadas muestra la última matrícula
  registrada, su estado y ciclo. Si no hay matrículas, lo informa sin inventar inscripciones.
- Académico: matrículas y materias propias, estados de inscripción/curso, nota final y
  componentes ya registrados, estado de calificación y asistencias por clase/fecha.
  No recalcula notas, asistencia, cierres ni estados. No expone observaciones internas.
- Financiero: reutiliza `financiero.consultas.cuenta` y la plantilla institucional para
  obligaciones, vencimientos, descuentos, pagos registrados, saldo y solvencia. No ofrece
  registro de pagos, edición ni acciones administrativas.
- Recibos: consulta e impresión de pagos propios, reutilizando la presentación existente,
  incluidos contenido preservado y recibos históricos. No crea ni modifica recibos.

## Identidad y permisos

Existe `Estudiante.usuario`, una relación OneToOne con `Usuario`. Se reutiliza directamente;
no se añaden campos, modelos ni migraciones. Todas las peticiones resuelven el expediente
con `usuario_id=request.user.pk`, exigiendo sesión, rol ESTUDIANTE y cuenta ACTIVA.
No se toma identidad desde parámetros, URL, correo, nombre, matrícula ni campos de formulario.
Si no existe vínculo o hay más de uno en un esquema externo inconsistente, se deniega el
acceso con un mensaje de verificación. No hay asociación automática ni autoservicio.

Antes de habilitar una cuenta real, Administración debe comprobar presencialmente o por
su procedimiento institucional la identidad, el número de usuario y el expediente correcto,
y confirmar manualmente el vínculo existente desde la administración autorizada de Estudiante.
Esta entrega no asignó ninguna cuenta real ni creó credenciales. No se recomienda vincular
por coincidencias de nombre/correo ni hacer vinculaciones masivas.

Las rutas personales son `/portal/`, `/portal/academico/` y `/portal/cuenta/`, sin ID de
estudiante. `/portal/recibos/<pago_id>/` filtra primero por el estudiante de la sesión:
un pago ajeno devuelve 404, igual que uno inexistente. Los parámetros adicionales no
cambian propietario ni filtros. Los POST se rechazan con 405. Los endpoints administrativos
académicos y financieros mantienen sus restricciones por rol; no se amplían sus permisos.

Se protegió además `/probar-conexion/`, que previamente exponía códigos y nombres sin
autenticación. Ahora exige sesión activa y un rol administrativo, evitando una vía
alternativa de consulta de otros estudiantes. El portal no permite acceder a esa ruta.

## Restricción académica y solvencia

Se reutiliza `financiero.consultas.solvente`, que llama a la función SQL existente
`estudiante_esta_solvente(id, fecha)`. Las condiciones de cuenta activa/rol/vínculo y
solvencia siguen la vista `vw_acceso_portal_estudiante` (script 16). No hay otra lógica
de solvencia ni cálculos alternativos de notas o asistencia.

- Se consulta solvencia en cada petición académica, sin guardar una autorización en sesión.
- Insolvencia bloquea toda la pantalla académica (materias, estados, notas, componentes y
  asistencia), con HTTP 403 antes de consultar esos registros. El inicio tampoco consulta
  ni incluye matrícula/ciclo protegidos en esa situación.
- Cuenta y recibos propios siguen disponibles, con las referencias de matrícula necesarias
  para identificar los cargos. La insolvencia no genera cambios académicos ni financieros.
- Se conservan las excepciones SQL de convenios y las reglas de incumplimiento/cuotas.
- Un fallo al verificar solvencia no habilita acceso académico: el inicio informa la
  indisponibilidad y el endpoint académico devuelve 503. No se presume solvencia.
- Las respuestas personales llevan `Cache-Control` privado/no-store para evitar caché
  compartida. Cada nueva petición vuelve a autorizarse; no se puede retirar información
  que el usuario ya haya consultado o guardado cuando tenía autorización.

## Validación esencial

```sh
python manage.py test core.test_portal --settings=academico.test_settings --noinput
```

**8 pruebas aprobadas**: login y datos propios; parámetros manipulados y recibo ajeno 404;
restricción académica sin modificar registros y con acceso financiero; convenio válido y
revocación del acceso en la siguiente petición; cuenta y enlaces personales; cuentas sin
vínculo, inactivas o con otro rol; rechazo de escrituras y rutas alternativas; cierre de
acceso ante fallo de solvencia.

El primer intento de preparar los datos ficticios registraba asistencia después de cerrar
la inscripción con la nota, y fue rechazado por las reglas académicas existentes. Se corrigió
el orden de la preparación, sin modificar esas reglas, y las ocho pruebas ejecutaron y pasaron.

Dos comprobaciones adicionales relacionadas también aprobaron:

```sh
python manage.py test \
 core.test_frontend.FrontendInstitucionalTests.test_menu_exacto_por_rol_sin_enlaces_ficticios \
 financiero.tests.FinancieroTests.test_cobro_web_recibo_reenvio_y_expediente_integrado \
 --settings=academico.test_settings --noinput
```

Solo SQLite efímero y datos ficticios, con el runner existente que rechaza PostgreSQL y
adapta literalmente las condiciones del SQL de solvencia para pruebas. No se repitieron
las baterías académica/financiera completas. `manage.py check --settings=academico.test_settings`
y `git diff --check` correctos.

Chromium/Playwright: login → inicio → materias/notas/asistencia → estado de cuenta → recibo.
Verificados escritorio 1440 px y móvil 390 px, menú móvil y ausencia de desbordamiento
horizontal. Comprobada otra cuenta insolvente: académico 403, cuenta/recibo propio disponibles,
recibo del otro estudiante 404. Capturas en `/workspace/artifacts/portal/`, fuera del repositorio.

## Archivos añadidos o modificados

- `core/portal.py`: identidad, permisos, restricción por solvencia y vistas personales.
- `core/urls.py`, `core/views.py`: rutas e integración con el inicio/login existente.
- `templates/core/portal/base.html`, `inicio.html`, `academico.html`, `aviso.html`:
  recorrido personal, estados vacíos y restricciones, reutilizando estilos institucionales.
- `templates/core/partials/sidebar.html`, `templates/core/dashboard.html`: navegación por rol.
- `financiero/views.py`: extrae únicamente la presentación común del recibo; autorización
  y selección por propietario se mantienen en cada endpoint.
- `templates/financiero/cuenta.html`, `templates/financiero/recibo.html`: enlaces personales
  cuando son usados por el portal, conservando el recorrido de Secretaría/Administración.
- `academico/views.py`: cierre de la ruta de diagnóstico para roles no autorizados.
- `core/test_portal.py`, `core/test_frontend.py`: pruebas esenciales y expectativas de navegación.
- Este documento.

## Límites

No se modificó PostgreSQL ni se ejecutó `manage.py migrate`; no se alteraron datos reales,
main ni archivos de esquema. Las pruebas construyen su esquema efímero únicamente en SQLite.
No se hizo commit/push. La validación del esquema externo y la ejecución efectiva de sus
funciones en PostgreSQL siguen pendientes; esta comprobación aislada no certifica producción.

Las cuentas reales necesitan vínculo manual previamente verificado. No se implementó
aprovisionamiento de cuentas, recuperación de contraseña ni autoasignación. Se muestran
las notas y asistencias tal como existen; una calificación o asistencia ausente se informa
como no registrada. La matrícula de referencia del inicio es la más reciente, sin asumir
que sea la única activa; la consulta académica permite revisar todas las matrículas propias.
