# Semana 11, fase 2 — correcciones excepcionales de calificaciones

## Alcance institucional autorizado

Solo calificaciones definitivas existentes y coherentes de cursos FINALIZADO,
matrícula ACTIVA y docente actual con cuenta activa. Se permiten aumentos y reducciones
de los nueve componentes, incluso cambiar APROBADA por REPROBADA_ACADEMICAMENTE y
viceversa. Se conserva fórmula, límites y redondeo de Calificacion. Cero es válido;
los extras solo completan apreciación hasta 100. Se rechazan componentes incompletos,
no finitos, con más de dos decimales o fuera de rango. Nota final y resultado se
calculan en el servidor; nunca se aceptan como instrucciones del navegador.

No se crean notas faltantes ni se reparan cierres históricos inconsistentes. Se bloquea
REPROBADA_POR_INASISTENCIA y cualquier inscripción con dos ausencias injustificadas,
aunque su estado sea incorrecto. Corregir nota_asistencia cambia solo ese componente,
nunca los registros de asistencia. Matrícula de otro ciclo, resultados inconsistentes,
fechas originales ausentes o curso con reglas de cierre incompatibles bloquean el trámite.

## Recorrido

Mis cursos → Calificaciones → Revisar corrección excepcional. La pantalla informa
los bloqueos y precarga componentes. El maestro escribe motivo y compara la propuesta.
Enviar exige una confirmación firmada de los valores mostrados, motivo y revisión;
si cambia los valores debe compararlos nuevamente. También se comprueba la revisión
bajo bloqueo al guardar. La solicitud pendiente no modifica notas ni inscripción.

Dirección usa la misma bandeja, con tipo de trámite, estudiante y resultado propuesto.
El detalle muestra componentes anteriores/propuestos y nota registrada actualmente.
Aprueba exactamente lo solicitado o rechaza con motivo. El administrador técnico y
el superusuario sin rol DIRECTORA no reciben autoridad académica. Rutas y servicios
verifican ámbito, cuentas activas y roles; no basta con ocultar botones.

## Aplicación y auditoría

El servicio común decidir conserva el orden usuarios por PK → curso → maestro →
matrícula → inscripción → asistencias por PK → calificación → solicitud. Cancelaciones
conservan su rama de ejecución y su orden propio después del maestro. No se abren
cursos ni se desactivan las protecciones ordinarias de save, vistas o Django Admin.

Al aprobar se reconsulta docente actual, matrícula, resultado y asistencia; se compara
la instantánea de curso, vínculo docente, ciclo, materia, inscripción, matrícula,
calificación y registros de asistencia. Una reasignación invalida solicitudes previas.
La última corrección aprobada identifica también cambios previos de versión. Datos
obsoletos dejan la solicitud pendiente para rechazo y nueva presentación, sin sobrescribir.

Únicamente se actualizan nueve componentes, nota_final y estado de calificación,
y estado de inscripción. fecha_registro, fecha_cierre, motivo_cierre, observaciones y
estado FINALIZADO del curso se conservan. Datos anteriores, propuesta, resultado
aplicado, motivo, solicitante, decisora y fechas quedan en la solicitud inmutable.
Cambio y resolución comparten una transacción: cualquier error revierte todos.
La excepción usa actualizaciones de campos explícitos dentro de decidir, después
de validar permisos, solicitud pendiente y registros obtenidos con bloqueos en la
misma transacción. No hay helper público de aplicación ni parámetro de bypass.

UUID único permite reenvíos idénticos, sin duplicar. Una sola corrección pendiente por
inscripción se exige también en base. Una decisión repetida idéntica devuelve la
resolución original; decisiones o motivos contradictorios se rechazan. Tras aprobar,
una segunda corrección necesita solicitud nueva y motivo. Cambios directos de SQL o
QuerySet fuera de estos servicios siguen siendo accesos internos privilegiados, no
una vía institucional de corrección ni una garantía de inmutabilidad física.

## Migración preparada, no ejecutada en bases persistentes

0001_initial.py permanece intacta. 0002_correcciones_calificaciones añade tipo y FK
opcional a InscripcionCurso, permite sesión nula y añade coherencia tipo/destino y
unicidad parcial de correcciones pendientes. El valor inicial CANCELACION_SESION
conserva las solicitudes anteriores, sus JSON y resoluciones. Se conservan índice de
cancelación pendiente, UUID único y restricciones de decisión/rechazo.
Todas las operaciones de esquema tienen como objeto solicitud_academica; no alteran
curso, calificacion, asistencia, inscripcion_curso ni otras tablas managed=False.
Las FK solo referencian sus PK existentes. No se reescribe la migración inicial.

La prueba de compatibilidad ejecuta las operaciones sobre otra conexión SQLite
:memory: con una solicitud de cancelación de 0001 y comprueba que se conserva con
tipo y destino correctos. Esa prueba no abre bases persistentes. El resto del runner
usa también SQLite en memoria y rechaza PostgreSQL.

## Despliegue futuro: pendiente de autorización

No se ha accedido a Neon ni ejecutado provisión o publicación. Mantener guardias de
settings_demo_pg y arranque sin migrate automático. Antes de publicar, ampliar el
procedimiento documentado en despliegue/solicitudes_academicas_fase1.md para evolucionar
la tabla existente con el SQL PostgreSQL revisado de 0002. No volver a crearla ni usar
el inicializador de base vacía. Respaldar tabla y esquema, comprobar que las solicitudes
anteriores siguen siendo cancelaciones, validar todos los índices/constraints y el FK
nuevo, y revisar permisos de INSERT/SELECT sobre nuevas columnas y UPDATE limitado a
campos de resolución. No alterar tablas académicas preexistentes.

Si la tabla se provisionó fuera de Django, reconciliar su estado exacto e historial
antes de adoptar migraciones. No marcar versiones como aplicadas automáticamente.
Ensayar primero la transición y la concurrencia en PostgreSQL aislado: aprobación
doble, cambios de roles, reasignaciones, solicitudes obsoletas y rollback. SQLite no
valida bloqueos PostgreSQL. Un rollback de aplicación no revierte correcciones ya
aprobadas: conservar historial y conciliar institucionalmente, nunca borrar decisiones.

## Correcciones de auditoría previas al commit

El reenvío HTTP con UUID existente se reconoce antes de calcular una propuesta
nueva. Se validan campos numéricos y confirmación firmada; el servicio reconsulta
cuenta y docente actual, y exige UUID del mismo autor, tipo, inscripción, motivo y
componentes originales. Si ya fue aprobada o rechazada, se redirige a la resolución
existente con un mensaje claro; no se repite la actualización. Datos distintos no
se aceptan. Una búsqueda por UUID no concede acceso: la página no publica valores,
firmas nuevas ni enlaces de una solicitud cuya pertenencia no esté verificada.

Una corrección pendiente bloquea la preparación y comparación de otra propuesta.
Se ofrece enlace únicamente a su solicitante autorizado; un docente reasignado ve
el bloqueo, sin acceso al trámite del docente anterior. Dirección debe resolverlo.
La validación transaccional y el índice único parcial siguen evitando duplicados
cuando una solicitud aparece después de la consulta de pantalla.

La escritura excepcional está encapsulada en decidir: usuarios, curso, maestro,
matrícula, inscripción, asistencias, nota y solicitud se obtienen bajo bloqueo antes
de la actualización. Allí se verifican transacción activa, directora activa,
solicitud pendiente y destino coherente. No se permite aportar objetos académicos
externos a una función de aplicación independiente. Calificacion.save sigue intacto.

Se mantienen todas las instantáneas conservadoras, sin reducir campos. Esta política
prioriza integridad: cambios descriptivos pueden volver obsoleta una solicitud y
obligar a rechazarla y presentar una nueva. No se modifica esta política en la auditoría.
