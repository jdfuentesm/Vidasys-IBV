# Semana 9: referencia de auditoría administrativa al usuario personalizado

## Diagnóstico y límites de la evidencia

El error reportado en Windows identifica una FK de `django_admin_log.user_id`
referida a `auth_user.id`. El actor autenticado pertenece a `usuario.id_usuario`.
La FK valida al actor de la operación, no al nuevo docente que se está creando.
Por eso la creación puede fallar al registrar su auditoría.

Comprobado por inspección del repositorio y del Django instalado:

- `AUTH_USER_MODEL = "core.Usuario"` ya figura en el primer commit versionado.
- `Usuario` usa `db_table = "usuario"`, PK `id_usuario` y `managed=False`.
- `core.0001_initial` mantiene ese modelo no administrado; no crea su tabla.
- `admin.0001_initial` de Django usa `swappable_dependency(AUTH_USER_MODEL)` y
  `LogEntry.user` referencia al usuario configurado. No codifica `auth_user`.
- No hay una migración propia que cambie la FK de `django_admin_log`.
- `django_migrations` registra qué migraciones se aplicaron, pero no guarda la
  configuración efectiva ni la definición de cada FK en ese momento. Que
  `admin.0001_initial` esté aplicada no demuestra que el esquema sea compatible.
- Los formularios heredados de UserAdmin declaran `auth.User` en su Meta. Se
  agregaron formularios explícitos para creación y edición de `Usuario`. Esto
  mejora la coherencia del código; NO cambia una FK ya existente en PostgreSQL.

La causa histórica exacta no está demostrada: una base iniciada con el usuario
predeterminado antes de este repositorio, una restauración de esquema antiguo o
DDL manual podrían producir el desajuste. El historial versionado no demuestra
un cambio anterior de AUTH_USER_MODEL. No se consultó la base de Windows ni se
han aplicado correcciones a ninguna instancia PostgreSQL durante esta tarea.

## Otras referencias que deben revisarse

`auditar_referencias_usuario` inspecciona las FK de las tablas accesibles en el
search_path y comprueba los destinos de `django_admin_log.user_id`,
`usuario_groups.usuario_id` y `usuario_user_permissions.usuario_id`. El SQL de
diagnóstico amplía el inventario a todos los esquemas y lista referencias a
`auth_user` sin mostrar información personal. No las modifica.

Las tablas heredadas `auth_user_groups` y `auth_user_user_permissions`, si
existen, no deben redirigirse automáticamente: pertenecen al modelo antiguo.
`auth_group_permissions` referencia grupos y permisos; `auth_permission` y la
FK `django_admin_log.content_type_id` referencian content types, no actores.
`django_session` guarda la sesión serializada sin FK de usuario; tras la
reparación se recomienda cerrar e iniciar sesión normalmente para confirmar la
identidad autenticada, sin borrar las sesiones mediante SQL.
`LogEntry.object_id` es una referencia genérica en texto, no una FK hacia
usuarios: el script no la altera ni cambia content types antiguos.

## Corrección permanente propuesta

Conservar `core.Usuario` y reparar únicamente la FK física de `user_id` para
referenciar `public.usuario(id_usuario)`, validando todos los registros. No
cambiar settings a auth.User, no duplicar usuarios en auth_user, no desactivar
LogEntry y no falsificar ni volver a ejecutar migraciones históricas.

Los scripts asumen explícitamente esquema `public`. Si el diagnóstico muestra
otro esquema, detenerse y adaptar/revisar los scripts antes de aplicarlos.

`admin_log_aplicar.sql`:

- Exige exactamente una FK simple en `user_id`, validada y dirigida al destino
  esperado (`auth_user.id` o ya `usuario.id_usuario`). Un estado desconocido falla.
- Si ya es correcta y validada, es una operación sin reemplazo (idempotente).
- Bloquea las tablas durante la comprobación y el cambio, con tiempos máximos.
- Falla si alguna entrada histórica no tiene ID correspondiente en `usuario`.
- Si hay entradas históricas, exige `identidades_verificadas=true`. Ese parámetro
  es una declaración del operador, NO demuestra por sí mismo la identidad.
- Guarda la definición original mediante `pg_get_constraintdef` en
  `public.vidasys_admin_log_fk_backup`, una tabla de metadatos sin información
  personal. Proteger su acceso: la reversión utiliza la definición DDL guardada.
- Reemplaza y valida la FK dentro de una transacción, manteniendo el patrón de
  Django: NO ACTION y DEFERRABLE INITIALLY DEFERRED. No desactiva la auditoría.
- No modifica, elimina ni remapea filas de `usuario`, `auth_user` o
  `django_admin_log`; solo agrega metadatos y cambia la restricción.

**Historial ambiguo:** que el mismo número exista en ambas tablas no implica
que represente a la misma persona. El responsable debe contrastar la procedencia
contra registros autorizados o respaldos, sin compartir datos personales en el
chat. Si algún actor antiguo no corresponde al mismo usuario personalizado,
esta reparación no puede aplicarse bajo la restricción de no alterar registros.
Detenerse y diseñar una estrategia de conservación/mapeo en una tarea separada.

La reversión restaura la definición original guardada y también exige comprobar
identidades. Si hubo nuevas operaciones cuyos actores no existen en auth_user,
se niega a revertir: no borra historial ni inventa usuarios. Repetir una reversión
completada no vuelve a reemplazar la FK. Revertir reintroduce la incompatibilidad
con el usuario personalizado: es recuperación de esquema, no solución operativa.

## Procedimiento seguro en Windows (aún NO ejecutado)

Ejecutar desde PowerShell en la raíz del repositorio. Usar las herramientas de
PostgreSQL instaladas (`psql.exe`, `pg_dump.exe`, `pg_restore.exe`) en PATH.
Sustituir los marcadores por la conexión real. No poner la contraseña en comandos
ni en la documentación; usar el prompt de PostgreSQL o su configuración segura.
Si `DB_HOST` está fuera de localhost, usar el host real autorizado.

1. Detener operaciones de escritura de VidaSys durante la ventana de mantenimiento.
   Confirmar primero la base de destino; no asumir que se trata de desarrollo.
2. Crear un respaldo completo fuera del repositorio y verificar que sea legible:

   ```powershell
   pg_dump -h localhost -p 5432 -U <usuario_bd> -d <base_bd> -Fc -f <ruta_segura>\vidasys-antes-fk.dump
   if ($LASTEXITCODE -ne 0) { throw "Falló el respaldo; detenerse" }
   pg_restore --list <ruta_segura>\vidasys-antes-fk.dump
   if ($LASTEXITCODE -ne 0) { throw "No se pudo leer el respaldo" }
   ```

   El listado no garantiza una restauración completa. Ensayar su restauración
   en una instancia descartable autorizada antes de intervenir producción.
   No incluir el dump ni su contenido en GitHub o en el chat.
3. Ejecutar solo el diagnóstico y guardar su salida fuera del repositorio:

   ```powershell
   psql -X -h localhost -p 5432 -U <usuario_bd> -d <base_bd> -v ON_ERROR_STOP=1 -f database/maintenance/admin_log_diagnostico.sql
   if ($LASTEXITCODE -ne 0) { throw "Diagnóstico incompleto; detenerse" }
   .\venv\Scripts\python.exe manage.py auditar_referencias_usuario
   ```

   Un CommandError por referencia incompatible es el resultado esperado antes
   de reparar. Revisar todas las referencias detectadas. La comprobación SQL y
   la configuración de Django deben corresponder a la misma base.
4. Revisar identidad de TODOS los actores existentes. No continuar si hay
   huérfanos, coincidencias numéricas ambiguas, FK desconocidas o un esquema
   distinto a `public`. Revisar el script y ensayarlo (aplicar dos veces, revertir
   dos veces y reaplicar) en la copia descartable autorizada. En este trabajo no
   se ha validado su ejecución en PostgreSQL.
5. **Solo con autorización posterior**, aplicar a la base real:

   ```powershell
   psql -X -h localhost -p 5432 -U <usuario_bd> -d <base_bd> -v ON_ERROR_STOP=1 -v identidades_verificadas=true -f database/maintenance/admin_log_aplicar.sql
   if ($LASTEXITCODE -ne 0) { throw "Reparación cancelada; revisar sin reintentar a ciegas" }
   ```

   No sustituir la revisión de identidad por escribir el parámetro true. Un
   error dentro de la transacción revierte su DDL al cerrarse la conexión.
6. Repetir diagnóstico y comando; la FK debe apuntar a `usuario(id_usuario)` y
   estar validada. Comparar cantidades y el respaldo del historial antes/después.
   Ejecutar `manage.py check`. Probar creación y edición de un docente y revisar
   el historial en la copia de desarrollo. Las pruebas funcionales crean datos:
   requieren autorización separada para la base real.
7. Si se requiere revertir, detener escrituras, volver a comprobar actores y
   usar `admin_log_revertir.sql` con las mismas opciones y el parámetro de
   identidades. Si se detiene por actores nuevos, no forzarlo ni borrar registros.

No ejecutar migrate, --fake, rollback de migraciones de admin, ni DROP TABLE.
Para instalaciones nuevas, preparar primero la tabla externa `usuario` y sus
relaciones y mantener AUTH_USER_MODEL desde el inicio. Validar con el comando de
inspección antes de habilitar Django Admin; los cambios de settings no reparan
restricciones preexistentes.

## Pruebas automatizadas aisladas

```powershell
.\venv\Scripts\python.exe manage.py test core academico --settings=academico.test_settings --noinput
```

Usan SQLite en memoria, incluidos el esquema Django y las tablas no administradas
creadas por el runner de pruebas. Comprueban creación y edición reales mediante
POST al admin, hash de contraseña, actor/objeto de LogEntry, validación, rechazo
sin permisos, rollback si falla la auditoría, FK esperadas y diagnóstico de solo
lectura. La detección de una FK heredada se prueba simulando sus metadatos; no
se reproduce el esquema defectuoso de PostgreSQL. Los scripts PL/pgSQL no se han
ejecutado y sus bloqueos, idempotencia/reversión y comportamiento con historial
real quedan pendientes del ensayo autorizado descrito arriba.
