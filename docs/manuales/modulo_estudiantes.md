# Gestión institucional de estudiantes

Implementada sobre `semana-9-rutas-calificaciones`, base `84a2f97`.

## Recorrido

Inicio o menú **Estudiantes** → búsqueda por nombre, apellidos o código → expediente.
El listado permite filtrar por estado personal y ciclo con matrícula; pagina de 20 en 20
conservando los filtros. Desde el listado se registra al estudiante y desde el expediente
se edita su información o se matricula en un ciclo.

Solo cuentas activas de SECRETARIA, DIRECTORA y ADMINISTRADOR tienen acceso, tanto por
GET como por POST. MAESTRO, ESTUDIANTE y PASTOR_PRINCIPAL no pueden consultar ni modificar
estos expedientes. Los formularios POST usan la protección CSRF institucional.

El registro incluye código, nombres, apellidos, nacimiento, teléfono, correo, dirección,
fecha de ingreso y estado. Código obligatorio y único, con comprobación adicional sin
distinguir mayúsculas/minúsculas y tratamiento de errores de integridad al guardar.
Los nombres y el correo no son identificadores únicos en el modelo: no se rechazan
homónimos ni correos compartidos. Se validan formato de correo y fechas de nacimiento.

La edición conserva código, fecha de ingreso y vínculo de usuario, incluso ante un POST
manipulado. Actualiza exclusivamente los demás datos personales. No modifica docentes,
matrículas, inscripciones, calificaciones, asistencias ni cierres. Cambiar el estado personal
no cambia automáticamente el estado académico.

El expediente muestra datos personales, matrículas, ciclos, materias inscritas, estados
de cursos e inscripciones y fechas de cierre disponibles. No consulta tablas financieras
ni muestra saldos, pagos o notas de observaciones que pudieran contener información sensible.

**Matricular en un ciclo** reutiliza `matricula_secretaria`, `MatriculaSecretariaForm` y
el servicio existente `matricular`; no hay otra lógica de matrícula. El estudiante se fija
en el servidor a partir del expediente, ignorando un identificador distinto enviado por
POST. Se mantienen los errores, transacción e idempotencia del servicio original. La
confirmación permite volver al expediente con las seis materias.

## Límites del modelo y validación

- `Estudiante.estado` no define opciones (`choices`): se conserva como texto de máximo
  20 caracteres, con ACTIVO como valor inicial ya utilizado por el proyecto. Los filtros
  usan los valores existentes; no se inventa un catálogo de estados ni restricciones SQL.
- El vínculo opcional `usuario` se conserva; este módulo no crea credenciales ni vincula
  cuentas. Así no puede reasignar accidentalmente una cuenta docente.
- No se incorporan campos nuevos ni cambios de esquema. Los modelos siguen siendo
  `managed=False`; una instalación real requiere el esquema externo correspondiente.
- No se ejecutaron migraciones ni escrituras en PostgreSQL. La compatibilidad con sus
  restricciones externas no se validó contra registros reales.

## Pruebas ejecutadas

Desde `/workspace/Vidasys-IBV`, con el entorno virtual activo:

```sh
python manage.py test academico.test_estudiantes core.test_frontend academico.test_flujo --settings=academico.test_settings --noinput
```

Resultado: **42 pruebas aprobadas**. SQLite efímero, con guardia del runner que rechaza
PostgreSQL. Incluye roles y acceso directo, registro, duplicados e integridad, validaciones,
edición con conservación de historial y docentes, búsqueda y filtros, paginación, navegación
e integración real con matrícula de seis materias, reintentos y estudiante fijado.

Comprobación con Chromium/Playwright sobre servidor local aislado en SQLite en memoria:
login, navegación desde Inicio, listado, registro, edición, filtros, expediente y enlace de
matrícula. Revisadas capturas a 1440 px y 390 px; sin desbordamiento horizontal en listado,
registro, edición, expediente y matrícula. Solo se usaron datos ficticios. Capturas de esta
sesión en `/workspace/artifacts/estudiantes/` (fuera del repositorio).

No se hizo commit ni push.
