# Solicitudes académicas — Semana 11, fase 1

## Alcance implementado

Desde Mis cursos → Programar sesiones → Gestionar sesión, el maestro solicita
cancelación con motivo. En Mis solicitudes consulta pendientes y resoluciones.
Dirección entra desde su dashboard a Solicitudes académicas y aprueba o rechaza
(con motivo obligatorio). No se concede autoridad al administrador ni al superusuario
por su condición técnica. La operación conserva la autorización original de extras.
Solo sesiones PROGRAMADA/SUSPENDIDA sin asistencia de cursos ACTIVO.
No hay correcciones de notas/asistencia, cancelaciones de impartidas ni reapertura.

## Integridad y auditoría

El envío no modifica datos académicos. Clave UUID única y bloqueo del curso evitan
reenvíos; el índice único parcial impide también pendientes duplicadas por sesión.
El CHECK de rechazo exige texto no vacío, incluso frente a escrituras directas.
La aprobación revalida cuenta, rol, docente actual, curso, estado, ausencia de
asistencia y fotografía de la sesión. Las propuestas obsoletas permanecen pendientes
para rechazo motivado y nueva solicitud. El rechazo puede resolver solicitudes
obsoletas sin alterar registros académicos. La decisión final es inmutable en el
servicio; save/delete del modelo protegen historial. No se registra el modelo en
Django Admin. QuerySet.update/delete y SQL directo son accesos internos privilegiados,
no un mecanismo autorizado para resolver trámites.
Cambio de sesión y decisión se confirman en la misma transacción. Reintentos idénticos
conservan la resolución; una decisión distinta se rechaza. No se modifican notas,
inscripciones ni finanzas. Cancelar puede dejar al curso sin las cinco impartidas
necesarias; los requisitos de cierre vigentes siguen bloqueando un cierre inválido.

## Migración preparada, sin ejecución en bases persistentes

`academico/migrations/0001_initial.py`: SeparateDatabaseAndState con operaciones
exclusivamente de estado para modelos managed=False, seguido de CreateModel para
SolicitudAcademica (tabla solicitud_academica). No crea ni altera tablas académicas
existentes. Dependencia de la migración de usuario mediante swappable_dependency.
Referencias PROTECT, índice de bandeja y restricción de coherencia de decisión.
La migración incluye solo las referencias requeridas por cancelación; inscripción,
tipo de corrección y versiones de notas/asistencia pertenecen a una fase futura.
El SQL generado bajo SQLite se revisa: una tabla nueva e índices; sin ALTER de
las tablas existentes. La aprobación del despliegue y la aplicación de migración
sobre un entorno persistente son pasos posteriores y separados.

## Validación aislada

Usar `academico.test_settings`, SQLite :memory:, runner que rechaza PostgreSQL.
El runner existente crea las tablas no administradas solo en esa base efímera;
Django crea la nueva tabla administrada al preparar las pruebas. No requiere
cambiar el runner. Ejecutar check, test y makemigrations --check --dry-run con esos
settings y variables DB ficticias. No utilizar settings de despliegue.
SQLite verifica reglas, permisos, idempotencia y rollback, pero no demuestra
bloqueos concurrentes de PostgreSQL; esa validación requiere posteriormente un
PostgreSQL aislado autorizado. No se ha accedido a Neon.

## Correcciones de integridad — revisión Semana 11

Usuarios por PK → curso → maestro → sesión → solicitud es el orden de bloqueos
compartido por solicitud/aprobación y autorización de extraordinarias (esta última
solo necesita usuario y curso). Usuarios se bloquean antes del curso para no invertir
las esperas con administración de cuentas y sus bloqueos de expedientes; los servicios
académicos ordinarios que solo bloquean curso/maestro/sesiones conservan su orden.
Los servicios de matrícula parten del ciclo y estudiante antes del curso: no se añaden
bloqueos tardíos sobre esos expedientes. No se eliminaron bloqueos.
La instantánea incluye campos del curso, identidad docente, ciclo, materia y sesión;
la aprobación valida nuevamente modelos, rango de fechas, estado y ausencia de
asistencia. Una solicitud obsoleta no se ejecuta ni pierde historial: Dirección puede
rechazarla motivadamente. Se ocultan formulario y enlace cuando la consulta detecta
un impedimento, sin sustituir la validación transaccional ante POST directo.

Procedimiento de provisión futura separado y no ejecutado:
[PostgreSQL y Render](despliegue/solicitudes_academicas_fase1.md).
La provisión externa requiere reconciliar después el estado Django antes de adoptar
migraciones sobre esa base; no habilita migrate automático ni la publicación.
