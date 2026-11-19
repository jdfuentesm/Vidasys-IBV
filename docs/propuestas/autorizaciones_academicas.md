# Propuesta mínima: solicitudes y decisiones de Dirección

Estado actualizado — Semana 11, fase 1: implementadas solicitudes y decisiones
para cancelar sesiones PROGRAMADA/SUSPENDIDA sin asistencia en cursos ACTIVO.
Se preparó `academico/migrations/0001_initial.py`; no se ejecutó contra bases
persistentes. Ver `docs/solicitudes_academicas_fase1.md` para el alcance vigente.
El diseño siguiente conserva las propuestas para fases futuras; las correcciones
posteriores al cierre y cancelaciones de sesiones impartidas siguen bloqueadas.

## Por qué la estructura actual no alcanza

`SesionClase.usuario_autoriza`, `fecha_autorizacion` y `motivo_extension` describen
la creación de clases extraordinarias. No representan al solicitante, una solicitud
pendiente, un rechazo o una secuencia de decisiones; reutilizarlos sobrescribiría
la autorización original. `observaciones` y `LogEntry` tampoco proporcionan por sí
solos un flujo tipado de solicitudes y versiones, con referencias y concurrencia.
No se guardarán solicitudes en archivos ni en comentarios libres.

## Estructura propuesta (una tabla nueva)

Modelo `SolicitudAcademica`, tabla `solicitud_academica`, sin modificar campos de
los modelos académicos existentes:

| Datos | Propósito |
| --- | --- |
| ID y clave única de solicitud | Identificación e idempotencia del envío |
| Tipo: cancelación de sesión, corrección de asistencia o corrección de nota | Limitar operaciones; no aceptar instrucciones arbitrarias |
| Curso y referencias a sesión/inscripción según tipo | Identificar sesión y estudiante mediante sus relaciones existentes |
| Solicitante y fecha de solicitud | Cuenta docente real, obtenida de sesión |
| Motivo de solicitud | Justificación obligatoria |
| Estado: PENDIENTE, APROBADA, RECHAZADA | Estado propio de la solicitud, no nuevos estados académicos |
| Decisor, fecha y motivo de decisión | Solo cuenta activa DIRECTORA; decisión y fecha desde servidor |
| Valores anteriores, valores propuestos y resultado aplicado en JSON | Copias explícitas de campos permitidos y resultados derivados, sin contraseñas ni datos innecesarios |
| Versión de los registros afectados | Rechazar solicitudes obsoletas sin sobrescribir cambios posteriores |

Las referencias usarían PROTECT. Restricciones de coherencia impedirían una
solicitud decidida sin autoridad/fecha, destinos incompatibles y campos que no
correspondan al tipo. La referencia al estudiante se obtiene de la inscripción,
sin duplicar una identidad que pueda divergir. Los JSON se validarían por tipo,
con una lista de campos permitidos; no son actualizaciones libres de modelos.

El repositorio usa modelos académicos no administrados. Antes de preparar una
migración o un script debe autorizarse cómo se gestionará esta tabla nueva
(migración administrada por Django o provisión del esquema externo). Esa decisión
no implica permiso para ejecutar cambios sobre Neon. No se necesita nueva tecnología.

## Operación propuesta

1. Docente del curso presenta solicitud y motivo. No modifica el dato académico.
2. Dirección ve pendientes, valores previos/propuestos y efectos sobre curso,
   inscripción y calificación. Administrador técnico no recibe facultad de decisión.
3. Aprobar bloquea curso, solicitud y registros afectados, vuelve a comprobar rol,
   propiedad y versión, y valida las reglas académicas vigentes.
4. Cambio, recálculo y decisión se confirman en una misma transacción. Si falla
   cualquiera, no se aplica ni se marca aprobada la solicitud.
5. Rechazar exige motivo y conserva los registros originales. Decisiones finales
   no se editan: otra corrección requiere otra solicitud. Reintentos devuelven la
   misma decisión; datos distintos sobre una solicitud decidida se rechazan.
6. La corrección se ejecuta únicamente por ese servicio autorizado; no se abre
   temporalmente el curso ni se habilitan POST ordinarios sobre cursos finalizados.

Cancelar cambia la sesión a CANCELADA, sin borrar asistencia ni notas. El curso no
se finaliza automáticamente: se vuelven a evaluar sus requisitos. La autorización
original de una extraordinaria se conserva independiente de la cancelación.
Una corrección de nota conserva sus componentes anteriores/nuevos y recalcula el
resultado con la fórmula y el mínimo 70 vigentes. Una corrección de asistencia
requiere evaluar el efecto en la inscripción y conservar el resultado anterior.
Si faltan datos obligatorios o la operación dejaría el curso fuera de las reglas
vigentes, no debe aprobarse silenciosamente ni inventar notas.

## Alcance detenido

Para correcciones de asistencia y notas de fases futuras faltan autorización de la estructura ampliada, implementación de solicitud/bandeja/decisión,
registro transaccional y pruebas de aprobación/rechazo/versionado/rollback. La fase 1 ya permite persistir y resolver cancelaciones simples; no ofrece solicitudes de corrección todavía.

La corrección de sesiones ya impartidas antes del cierre no está expresamente
resuelta por las nuevas reglas (que sí confirman cancelaciones y correcciones
posteriores al cierre). Sigue bloqueada y requerirá delimitar su alcance antes de
habilitarla. No se amplían permisos por interpretación.
