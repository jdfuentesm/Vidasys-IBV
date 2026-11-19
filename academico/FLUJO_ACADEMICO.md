# Flujo académico integrado — matrícula y sesiones

## Alcance

Las entradas operativas de matrícula (pantalla de Secretaría y alta ACTIVA desde
Django Admin) reutilizan `flujo.matricular()`. No hay señales globales ni cambios
en Matricula.save(): los comandos de ensayo y las cargas ORM de bajo nivel
conservan su funcionamiento anterior y no son interfaces de matrícula operativa.
Cualquier nueva entrada operativa debe utilizar el servicio, no crear la matrícula
por separado. No se ejecutaron operaciones contra PostgreSQL ni se agregaron
migraciones. No se modifican docentes, usuarios ni el módulo financiero.

## Secretaría

`/matriculas/nueva/` requiere cuenta activa con rol SECRETARIA, DIRECTORA o
ADMINISTRADOR. Pide estudiante existente, ciclo, número, fecha de matrícula y
observaciones. No genera estudiantes ni modifica sus datos.

Antes de crear una matrícula ACTIVA, el servicio valida que el número formativo
del ciclo tenga exactamente seis materias y que estén preparados sus seis cursos
correspondientes en el ciclo académico seleccionado. Cursos CANCELADO o FINALIZADO
se consideran una configuración incompatible para una nueva matrícula: se informa
y no se crea nada. No se presupone el catálogo real de PostgreSQL ni se lo repara.

La transacción bloquea ciclo, estudiante, cursos, matrícula e inscripciones.
Crea las inscripciones faltantes CURSANDO, con fecha igual a fecha_matricula.
Las existentes se conservan completas, incluso si tienen notas, asistencias o un
cierre académico. No se reabren. Una matrícula existente del mismo estudiante/ciclo
solo se reutiliza si es ACTIVA y coinciden número y fecha; no se sobrescribe su
información. Si hay inscripciones de cursos incompatibles, se cancela todo.
Un reintento con los mismos datos no duplica matrícula ni inscripciones.

El Admin incorpora la misma validación previa y el servicio para el alta ACTIVA.
La edición de matrículas históricas en Admin conserva su comportamiento anterior;
no actúa como herramienta masiva de reinscripción ni de reparación. No se asignan
nuevos permisos a usuarios ni se requiere que Secretaría administre inscripciones.

## Docente

`/mis-cursos/` ofrece enlaces directos a asistencia, calificaciones, programación
y revisión de cierre. Se enlaza desde el dashboard. Cada ruta vuelve a comprobar
rol MAESTRO, cuenta activa y pertenencia del curso; ocultar enlaces no sustituye
los permisos del servidor. No se crean matrículas al abrir un curso.

## Propuesta de calendario

`/cursos/<id>/programar/` pide explícitamente:

- Fecha inicial (referida a la clase 1 de la propuesta).
- Frecuencia semanal (7 días), quincenal (14) o personalizada (intervalo en días).
- Hora de inicio y duración en minutos.

No hay frecuencia ni duración académica por defecto. No se interpreta Curso.horario
(texto libre), no se deducen días de reunión y no se desplazan feriados. Las seis
filas ordinarias son editables antes de confirmar. La frecuencia define únicamente
la propuesta; el docente puede ajustar fechas y horas individualmente.

La sesión debe terminar el mismo día y después de la hora de inicio, conforme al
modelo que exige hora_fin > hora_inicio. Las nuevas fechas deben estar dentro del
período del curso. Se rechazan valores fuera de rango en vez de desplazarlos.
Si una clase ya existe, se muestra deshabilitada con sus datos originales y no se
actualiza. Solo se crean números 1–6 en estado PROGRAMADA, nunca 7 u 8.

La propuesta no escribe sesiones. Confirmar revalida el curso y todas las filas
bajo una transacción. Una firma de revisión detecta cambios en curso/sesiones
entre la propuesta y el guardado. Un envío obsoleto requiere generar de nuevo la
propuesta, sin duplicar ni sobrescribir. Cursos finalizados o cancelados no admiten
confirmación. Las sesiones existentes se pueden consultar en la misma pantalla.

## Extraordinarias y cierre

`/autorizar-clase/` exige sesión autenticada activa con rol DIRECTORA. No muestra
ni acepta como autoridad los valores enviados de usuario_autoriza o
fecha_autorizacion: se asignan desde el usuario autenticado y la hora del servidor.
Solo crea clases 7 y 8, con motivo; no actualiza una sesión existente ni admite
cursos cancelados/finalizados. Se conservan las validaciones del modelo y Admin.

`/cursos/<id>/cierre/` muestra sesiones y errores del propio Curso.full_clean(),
sin duplicar las reglas académicas. Confirmar vuelve a validarlas bajo bloqueo:
entre cinco y ocho impartidas y ninguna PROGRAMADA o SUSPENDIDA. Por eso, si se
imparten cinco de las seis ordinarias y queda otra programada, el curso todavía
no puede finalizar. La gestión de sesiones permite marcar impartida, suspender o reprogramar bajo las
restricciones de etapa 2. El cierre no cancela clases ni autoriza extraordinarias;
ahora también valida calificaciones y fija resultados académicos definitivos.
Un curso CANCELADO no se transforma en FINALIZADO, y uno ya finalizado no se reabre.

Las reglas de dos injustificadas, conservación de cierres por inasistencia y
revisión de Dirección permanecen sin cambios. Tampoco cambia la fórmula de notas.

## Validación

```powershell
.\venv\Scripts\python.exe manage.py test core academico --settings=academico.test_settings --noinput
.\venv\Scripts\python.exe manage.py check
```

SQLite de memoria comprueba matrícula con seis inscripciones, reintento y rollback,
alta desde Admin, permisos web, preservación de cierres y datos docentes, frecuencias
explícitas, edición del calendario, sesiones existentes, revisiones obsoletas,
autorización efectiva de Dirección y cierre mínimo con pendientes.

Pendiente: ensayo autorizado del esquema, unicidades, disparadores y bloqueos en
PostgreSQL. No se inspeccionaron datos reales; no se presume que el ciclo local ya
tenga preparados sus seis cursos ni que los perfiles docentes estén vinculados a
sus cuentas. Las incompatibilidades se informan, nunca se corrigen modificando
usuarios/docentes, borrando pruebas o alterando restricciones automáticamente.

## Etapa 2: decisión de cierre

Antes, el cierre era operativo (5–8 sesiones impartidas, sin programadas/suspendidas),
y guardar notas cerraba inscripciones. La regla confirmada establece un cierre único
operativo y académico: las notas se guardan PENDIENTE y la inscripción permanece
CURSANDO hasta confirmar el cierre. No se cambian la fórmula, el mínimo 70 ni los
cierres por inasistencia. No se reescribe automáticamente el historial existente.

### Sesiones y restricciones posteriores al cierre

El calendario enlaza a `/cursos/<curso>/sesiones/<sesion>/`. Solo su docente activo
puede gestionar una sesión de un curso ACTIVO. PROGRAMADA puede pasar a SUSPENDIDA
o IMPARTIDA (no futura). SUSPENDIDA puede reprogramarse como PROGRAMADA. Fechas y
horas deben quedar en el período del curso; una sesión con asistencia no se suspende
ni reprograma. Se conserva número, curso y autorización de extraordinarias. Las
sesiones impartidas y canceladas son de consulta. Las revisiones firmadas detectan
calendarios obsoletos; el servicio vuelve a validar propiedad y estado bajo bloqueo.

El cierre exige las reglas operativas previas y notas válidas para cada inscripción
CURSANDO con matrícula ACTIVA. Recalcula con la fórmula vigente, fija APROBADA desde
70 o REPROBADA_ACADEMICAMENTE y la fecha/motivo de cierre. Inscripciones reprobadas
por inasistencia se conservan completas y no requieren otra nota. Cierres previos
incompatibles no se reinterpretan: requieren revisión explícita. Todo se guarda en
una transacción; un fallo revierte el lote. Repetir un cierre ya finalizado no cambia
notas ni fechas. La revisión de cierre incluye calendario, inscripciones, notas y asistencia.

Asistencia y notas se bloquean después de finalizar/cancelar, tanto en POST como en
los métodos de persistencia. No hay reapertura. Los cursos con resultados históricos
no se migran ni se reabren automáticamente. Los informes y portal distinguen notas
provisionales; `nota_final` sigue siendo la columna numérica existente y `PENDIENTE`
el estado provisional, sin añadir campos ni estados.

### Finalización de etapa 2: reglas confirmadas

Se conserva por confirmación explícita la regla vigente de seis clases ordinarias
(1–6), extraordinarias 7–8 y cierre con 5–8 impartidas sin programadas/suspendidas.
La mención de cuatro ordinarias no cambia numeración ni mínimos en esta entrega.

La asistencia completa es ahora requisito obligatorio de servidor. Se comprueban
las sesiones IMPARTIDA y los estudiantes correspondientes, desde la mayor de las
fechas de matrícula e inscripción. En reprobación por inasistencia se exige el
historial hasta su fecha de cierre inclusive, nunca registros posteriores. No se
reabren inscripciones ni se inventan ausencias. Un registro con estado inválido
cuenta como pendiente; dos injustificadas sin el cierre correspondiente o un cierre
sin fecha/dos ausencias se informan como inconsistencias para Dirección.

PROGRAMADA, SUSPENDIDA y CANCELADA no exigen registros de asistencia; las dos
primeras conservan su bloqueo operativo del cierre. Las extraordinarias realmente
impartidas exigen asistencia con el mismo criterio. CANCELADA ya presente se respeta
como estado histórico; esta entrega no certifica que tenga una solicitud aprobada,
porque tal registro todavía no existe. No se elimina información académica.

Mis cursos y cierre muestran cantidad de pendientes, clase/fecha, estudiantes y
enlaces directos a la asistencia. Si la inscripción está cerrada, el mensaje indica
que se requiere revisión de Dirección y no ofrece una reapertura. Una evaluación
empezada exige todos sus componentes, con extras opcionales; una fila vacía sigue
sin registro y no se inventan notas para cerrar.

Solo DIRECTORA puede aprobar cancelaciones y correcciones posteriores al cierre;
Administrador no hereda esa autoridad. Su implementación está detenida hasta aprobar
la [propuesta mínima de solicitudes](../docs/propuestas/autorizaciones_academicas.md).
No se reutilizan las autorizaciones de extraordinarias para registrar cancelaciones.
Django Admin rechaza nuevas cancelaciones y eliminaciones de sesiones; los registros
de cursos cerrados quedan sin escritura ni borrado desde las pantallas técnicas
protegidas. El cierre desde Admin no puede omitir el servicio institucional.
No se habilitaron aprobación, rechazo, solicitudes persistidas ni reapertura.

### Comprobación aislada

`python manage.py test --settings=academico.test_settings --noinput`.
La suite incluye frontera 70, resultado inferior, notas provisionales y asistencia
posterior, dos ausencias, sesiones, permisos, CSRF, cierre incompleto, revisiones
obsoletas, reintentos y rollback al final y en mitad del lote. SQLite no certifica
bloqueos concurrentes reales de PostgreSQL. No ejecutar el ensayo contra Neon.

Resultado de la verificación inicial de etapa 2: 197 pruebas aprobadas, comprobación de
Django sin incidencias y `git diff --check` correcto. Se verificaron ocho vistas
(cursos, sesión, cierre y libro) a 390 y 1440 píxeles, sin desbordamiento global ni
imágenes rotas. Los campos, estados y Meta de los modelos son idénticos al commit
base: solo se modificaron métodos. No se cambiaron reglas financieras, migraciones,
identidad visual ni configuración de base de datos. Sin commit, push o despliegue.

### Verificación de finalización

Suite completa: **212 pruebas aprobadas**, usando exclusivamente SQLite en memoria.
Se conservaron las pruebas de atomicidad, reintentos, cierres por inasistencia y
protección posterior al cierre; se añadieron casos de asistencia pendiente, sesiones
no impartidas, extraordinarias, fecha de inscripción, inconsistencias, permisos y
vías administrativas. Las pruebas de decisiones trazables de cancelación/corrección
quedan pendientes junto con la estructura propuesta, no se declaran implementadas.
Django check y git diff --check sin incidencias. Cuatro vistas actualizadas de cursos
y cierre comprobadas a 390 y 1440 píxeles, sin desbordamiento global. No se introdujeron
campos, estados de modelo, migraciones ni cambios en identidad visual o finanzas.

Archivos de esta finalización sobre el trabajo de etapa 2 existente:

- `academico/flujo.py`: asistencia obligatoria, consistencia, bloqueo y revisión firmada.
- `academico/admin.py`: cierre técnico y cancelaciones bloqueados; protección de registros cerrados.
- `academico/test_ciclo_docente.py`, `academico/test_flujo.py`: cobertura nueva y fixtures completos.
- `templates/academico/mis_cursos.html`, `cierre_curso.html`, `gestionar_sesion.html` y el
  componente nuevo `pendientes_asistencia.html`: orientación y enlaces por sesión.
- Este documento y `docs/propuestas/autorizaciones_academicas.md`: reglas confirmadas,
  límites y propuesta pendiente de aprobación.

No se accedió a Neon, no se ejecutaron migraciones y no se creó commit, push ni despliegue.
