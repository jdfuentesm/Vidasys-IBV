# Registro de calificaciones — Semana 9

## Flujo

Un usuario autenticado, activo y con rol MAESTRO abre `/calificacion/` y selecciona
uno de los cursos vinculados a su perfil Maestro. El libro muestra todas sus
inscripciones y todos los componentes, observaciones, nota final y estado en una
tabla editable. Los nombres y encabezados permanecen fijos dentro de la tabla.
Se puede navegar con Tab o desplazarse horizontalmente. Los controles son grandes,
y el botón de guardar todas las calificaciones permanece visible al desplazarse.

Una fila nueva completamente vacía queda pendiente y no crea una calificación.
Si se comienza una evaluación, deben completarse sus componentes (extras opcionales).
Una evaluación con todos los componentes en cero se registra con nota 0.00 y reprueba.
No se borran evaluaciones existentes al dejar una fila vacía: se muestran errores.
Las inscripciones reprobadas por inasistencia permanecen visibles y no editables.

Se reutilizan CalificacionForm, las validaciones del modelo, calcular_nota() y
save(). La vista previa automática consulta el mismo cálculo Python, sin guardar;
si no hay JavaScript o conexión para la vista previa, el botón de guardar sigue
calculando en el servidor. La clasificación se centraliza en estado_para_nota(),
sin cambiar el umbral existente ni la fórmula.

El servidor valida la lista completa de inscripciones del curso, incluidos POST
adulterados. Todas las filas se validan antes de guardar, y la transacción revierte
todo si falla cualquiera. Solo se guardan las filas modificadas. Cada fila lleva
una revisión firmada para detectar cambios concurrentes desde la apertura del
libro y evitar sobrescribir una versión nueva. No se modifica la estructura SQL.
Las modificaciones pendientes reciben advertencia al abandonar la pantalla.

Otros roles no obtienen acceso a esta vista. El administrador y los demás módulos
conservan su funcionamiento existente. La ruta y su nombre no cambian.

## Reglas y procedencia

- Fórmula conservada de `8e668f5`: apreciación = asistencia (0–40), uniforme
  (0–20), participación (0–20), compañerismo (0–20) y extras (0–10), con tope 100.
  Nota final = (apreciación + tarea 1 + examen 1 + tarea 2 + examen 2) / 5.
- Tareas y exámenes: 0–100, confirmado por el usuario durante esta tarea.
- Extras opcionales, a consideración del docente; se usan para cubrir puntaje
  faltante en la apreciación sin superar 100. No se asignan automáticamente.
- Aprobación desde 70; por debajo se reprueba. La regla está en el historial
  anterior a `8e668f5` (por ejemplo `e6d5db0`) y fue confirmada por el usuario.
- La nota se representa con dos decimales, conforme al campo existente.
- Según la aclaración del usuario (notas de 0–100 y menos de 70 reprueba), una
  evaluación registrada con todos los componentes en cero ahora guarda 0.00 y
  reprueba; no se confunde con una inscripción sin calificación registrada.
- Una inscripción reprobada por inasistencia no admite guardar calificaciones.
- Se restaura el cierre de inscripción al registrar una nota final, conservando
  la fecha original de registro de la calificación. No se revierte un cierre
  por inasistencia.

## Verificación sin PostgreSQL

Desde `/workspace/Vidasys-IBV`:

```bash
venv/bin/python -B manage.py check
venv/bin/python -B manage.py test core academico --settings=academico.test_settings --noinput
```

Las pruebas usan exclusivamente SQLite en memoria. El runner rechaza otros
motores y crea las tablas no administradas solo dentro de esa base efímera.
Las migraciones del framework, si el runner las necesita, también se ejecutan
exclusivamente allí. No ejecutar esta suite con la configuración normal de
PostgreSQL. No se cambian `managed=False`, migraciones ni esquemas reales.

## Bloqueos pendientes en PostgreSQL

No se ha validado este flujo contra PostgreSQL ni se han ejecutado scripts SQL
ni migraciones en esa base. El repositorio no contiene el esquema inicial y no
incluye SQL para las nueve columnas de componentes de calificación. Antes de una
prueba funcional real hay que contrastar con el esquema autorizado:

- `usuario`, `maestro.id_usuario`, estudiante, matrícula, materia, ciclo y curso.
- Inscripción y su relación con el curso y la matrícula.
- `calificacion`: claves, unicidad de `id_inscripcion`, componentes, nota final,
  estado, fecha de registro y observaciones.
- Tablas de sesión/autenticación de Django y relaciones de permisos.
- Restricciones, funciones y disparadores existentes, así como su compatibilidad
  con las actualizaciones de estado académico realizadas por Django.

SQLite verifica persistencia y flujo web, pero no reproduce disparadores,
restricciones específicas ni bloqueos concurrentes de PostgreSQL. Un error de
base de datos se presenta al docente sin SQL ni datos de conexión. La reparación
del esquema requiere una tarea autorizada separada.

## Validación del libro completo

La suite incluye registro y edición de múltiples estudiantes, filas pendientes
frente a cero, límites, datos incompletos, permisos, inscripciones adulteradas,
revisiones desactualizadas, exclusión por inasistencia y rollback total. La vista
previa se comprueba sin escrituras. Se conserva la cobertura de rutas y Admin.
La comprobación de navegador se realizó con Chromium, servidor temporal y SQLite
exclusivamente de pruebas: vista previa, guardado, consulta, columna fija y ancho
móvil. No constituye validación del esquema ni de los bloqueos en PostgreSQL.
