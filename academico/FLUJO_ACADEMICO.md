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
no puede finalizar. Esta interfaz NO cancela esa clase, no cambia estados de
sesiones, no altera matrículas/calificaciones y no autoriza extraordinarias.
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
