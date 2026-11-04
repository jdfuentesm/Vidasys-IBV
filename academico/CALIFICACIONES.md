# Registro de calificaciones — Semana 9

## Flujo

Un usuario autenticado, activo y con rol MAESTRO accede a `/calificacion/`,
selecciona uno de los cursos vinculados a su perfil Maestro y selecciona una
inscripción de ese curso. Puede consultar, registrar y modificar la nota.
Se carga el registro existente antes de validar el formulario para no intentar
crear un duplicado. Los identificadores enviados por POST se verifican nuevamente
contra los cursos e inscripciones autorizados. Otros roles no obtienen acceso a
esta vista. El administrador conserva sus permisos existentes.

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
venv/bin/python -B manage.py test academico --settings=academico.test_settings --noinput
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
