# Control de Asistencia — Semana 9

## Reglas confirmadas

La ruta sigue siendo `/asistencia/` (`registrar_asistencia`). El usuario debe
estar autenticado, activo y tener rol MAESTRO, con un perfil Maestro vinculado.
Solo puede abrir sus cursos y las sesiones ya existentes de estos. No se crean
sesiones ni se modifican su fecha, autorización o estado.

Para registrar o corregir se exige:

- Matricula.estado = ACTIVA.
- La matrícula corresponde al ciclo del curso.
- InscripcionCurso.estado = CURSANDO.
- La sesión y la inscripción corresponden al mismo curso.
- SesionClase.estado = PROGRAMADA o IMPARTIDA.

ACTIVA fue confirmada como decisión funcional del proyecto; no se afirma haber
verificado su CHECK físico en PostgreSQL. No se agregan condiciones por fecha ni
campos nuevos. Las sesiones SUSPENDIDA y CANCELADA son solo de consulta.

Los únicos valores persistidos son PRESENTE, AUSENTE_JUSTIFICADA y
AUSENTE_INJUSTIFICADA. Una selección pendiente no crea una fila y nunca se
convierte automáticamente en ausencia. Una observación requiere un estado para
poder guardarse. No se puede borrar una asistencia existente dejando el estado
vacío; las correcciones cambian su estado u observación, sin duplicar registros.

## Dos ausencias injustificadas

El conteo abarca únicamente asistencias AUSENTE_INJUSTIFICADA de la misma
inscripción (no otras materias, cursos o matrículas). Desde dos, se conserva la
regla previa: REPROBADA_POR_INASISTENCIA, fecha de cierre igual a la sesión guardada
y motivo "Acumuló dos ausencias injustificadas.". Una justificada no contribuye.
No se alteran calificaciones finales, otras inscripciones ni la matrícula.

Las correcciones ordinarias se permiten mientras la inscripción siga CURSANDO
y cumpla las demás condiciones. Si ya está REPROBADA_POR_INASISTENCIA, no se permite
corregir/reabrir desde esta interfaz ni mediante Asistencia.save(). Se informa
que requiere revisión de Dirección. No se inventa un estado de solicitud ni se
simula una revisión aprobada: el caso debe canalizarse a Dirección por el proceso
institucional. La gestión de esa revisión no forma parte de este módulo.

No se sobrescriben cierres de otros motivos. Si una inscripción figura CURSANDO
pero conserva fecha o motivo de cierre, y la segunda injustificada intentara
reemplazarlos, el guardado se rechaza y se revierte el lote para revisión.

## Consulta e integridad

La lista muestra las inscripciones habilitadas, además de las que ya tienen
asistencia registrada en la sesión seleccionada, incluso si posteriormente
quedaron cerradas o su matrícula dejó de estar ACTIVA. Estas últimas se muestran
solo para consulta con el motivo de bloqueo; no se mezclan con nuevas filas
habilitadas. El contador es de ausencias ya guardadas, no una vista previa.

Antes de guardar se valida todo el lote. Se verifican curso/docente, sesión y
lista exacta de inscripciones; no se aceptan IDs agregados, repetidos o faltantes.
Se bloquean curso, sesión, matrículas e inscripciones, con orden estable. El
modelo usa el mismo orden para sus guardados. Se mantiene la unicidad de
(inscripcion, sesion), la correspondencia de curso y la inmutabilidad de esas dos
relaciones al corregir un registro existente.

Cada fila incluye una revisión firmada de la asistencia y su habilitación. Si
cambian el registro, la matrícula, la inscripción o la sesión, se rechaza el envío
obsoleto. Los guardados y cierres comparten una transacción: un error revierte el
lote completo. No se guardan filas sin cambios, pendientes ni bloqueadas.
La interfaz mantiene los valores enviados y muestra errores sin revelar SQL ni
credenciales. Los cambios pendientes generan advertencia al abandonar la sesión.

El CSS institucional de calificaciones se reutiliza sin modificarlo. Los ajustes
específicos y el JavaScript se aíslan en archivos de asistencia. No hay acciones
para crear sesiones ni enviar ausencias por defecto.

## Pruebas sin datos reales

```powershell
.\venv\Scripts\python.exe manage.py test core academico --settings=academico.test_settings --noinput
.\venv\Scripts\python.exe manage.py check
```

El runner usa SQLite en memoria, nunca PostgreSQL. La cobertura incluye permisos,
matrícula ACTIVA/ciclo, sesiones habilitadas, pendientes, justificadas frente a
injustificadas, cierre de una sola inscripción, correcciones, consulta cerrada,
Dirección, duplicados, CSRF, revisiones obsoletas, rollback de notas de asistencia
y cierre, conservación de otras matrículas/materias/calificaciones y sesiones.

No se ejecutaron migraciones, escrituras ni consultas sobre PostgreSQL real.
No se agregan migraciones ni cambia managed=False. Queda pendiente comprobar el
esquema real (incluida la unicidad física y los CHECK), los disparadores y el
comportamiento de bloqueos entre procesos PostgreSQL en un ensayo autorizado.
La cobertura de revisiones obsoletas es secuencial; SQLite no demuestra bloqueos
FOR UPDATE de PostgreSQL. No usar el comando de ensayo de calificaciones como
prueba de este módulo: su alcance sigue siendo exclusivamente calificaciones.

## Pendientes registrados para el siguiente avance

1. Validación física en PostgreSQL mediante ensayo autorizado: restricciones,
   unicidad, disparadores y bloqueos concurrentes reales. No se ha ejecutado.
2. Definir e implementar el flujo de revisión y reapertura autorizado por Dirección.
   Actualmente solo se informa y bloquea la corrección de inscripciones cerradas;
   no existe reapertura automática ni una acción de aprobación en este módulo.
