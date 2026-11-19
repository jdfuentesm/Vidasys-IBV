# Incorporación controlada de solicitud_academica en PostgreSQL

**Procedimiento preparado, NO ejecutado. Requiere autorización separada de cambios
persistentes y publicación.** No usar Neon para ensayos. No retirar la protección
de settings_demo_pg ni agregar migrate al arranque. No ejecutar preparar_demo_pg
contra una base existente. Este documento no autoriza conexiones ni cambios.

## 1. Preparación y comprobaciones previas

1. Fijar commit candidato, versión Django/PostgreSQL, destino, esquema public,
   operador DDL autorizado y rol web. Obtener autorización de ventana de mantenimiento.
   Confirmar identidades con current_database(), current_user y servidor esperado;
   abortar si no coinciden exactamente. No guardar contraseñas en scripts o historial;
   utilizar el mecanismo de credenciales del operador (.pgpass protegido, por ejemplo).
2. Comprobar por catálogo que public.solicitud_academica NO existe, que las tablas
   public.curso, public.sesion_clase y public.usuario existen con PK bigint en
   id_curso, id_sesion e id_usuario, respectivamente. Confirmar search_path explícito,
   disponibilidad de referencias y permisos del operador. Si la tabla ya existe,
   abortar y comparar su estructura; no usar IF NOT EXISTS para ocultar diferencias.
3. Verificar historial de django_migrations por lectura, si la tabla existe. No asumir
   que las migraciones Django describen el esquema externo. La migración inicial de
   financiero es una deuda de estado preexistente y queda fuera de esta operación.
4. Generar respaldo lógico completo en formato custom y, adicionalmente, esquema
   previo: pg_dump --format=custom --file=respaldo-previo.dump "$DESTINO_AUTORIZADO"
   y pg_dump --schema-only --no-owner --no-privileges --file=esquema-previo.sql
   "$DESTINO_AUTORIZADO". Estas variables son del operador, no del repositorio.
   Guardar con acceso restringido, registrar SHA-256 y comprobar pg_restore --list.
   Probar la restauración en un destino aislado autorizado antes de continuar.

## 2. Preparar y verificar el SQL exclusivamente en PostgreSQL desechable

1. Preparar PostgreSQL aislado con tablas sintéticas compatibles, nunca datos reales.
   Usar settings exclusivos de ensayo que apunten solo a ese destino; no reutilizar
   settings_demo_pg ni improvisar desactivando su guardia.
2. Revisar el plan de la migración academico 0001: el bloque de estado no produce
   DDL. Las dependencias deben estar comprobadas en el ensayo. Generar sqlmigrate,
   revisarlo y aplicar la migración SOLO allí para comprobar compatibilidad PostgreSQL.
   No ejecutar makemigrations ni migraciones globales en la base de demostración.
3. Validar en el ensayo el índice único parcial sol_acad_unica_pendiente, el CHECK
   sol_acad_rechazo_motivado (rechaza vacío, espacios, tabuladores y saltos de línea),
   sol_acad_decision_coherente, clave UUID única, cuatro FK e índices de consulta.
   Probar concurrencia real: dos aprobaciones, aprobación contra asistencia,
   aprobación contra extraordinaria y cambios de roles/vínculos concurrentes.
4. Exportar SOLO la tabla preparada con pg_dump --schema-only --no-owner
   --no-privileges --table=public.solicitud_academica. Revisar que incluya su secuencia
   o identidad y todos los índices/constraints; obtener el nombre de secuencia desde
   pg_get_serial_sequence en el ensayo, sin adivinarlo. Esquema sin datos.
5. Revisar el artefacto SQL y su hash. La lista permitida es la tabla nueva, su
   secuencia/identidad, índices y constraints. ALTER TABLE solo puede tener como
   objeto solicitud_academica (por ejemplo, agregar FK), nunca sus tablas destino.
   No debe contener DROP, CASCADE, modificaciones de datos, otras tablas, ni cambios
   a django_migrations. Adaptar calificación de nombres al esquema public y revisar
   configuración search_path. Una FK referencia tablas existentes sin alterarlas.

## 3. Aplicación futura autorizada

1. Detener escrituras web durante la ventana; conservar la versión anterior lista.
2. Ejecutar el SQL revisado como una única transacción con ON_ERROR_STOP y tiempos
   acotados de lock_timeout y statement_timeout. Usar el rol DDL separado del rol web.
   Si cualquier paso falla, rollback y detener el procedimiento, sin reintentos ciegos.
3. En la misma transacción, conceder al rol web USAGE en public, SELECT e INSERT
   sobre la tabla, UPDATE únicamente sobre estado, directora_id, fecha_decision,
   motivo_decision y aplicados; USAGE sobre la secuencia realmente creada.
   No conceder DELETE, TRUNCATE, CREATE ni propiedad de la tabla. Verificar también
   privilegios heredados/PUBLIC; no asumir que un GRANT limitado elimina otros.
   Si el entorno no permite este reparto, detener y solicitar revisión de permisos.
4. No ejecutar migrate con settings_demo_pg. La provisión SQL es externa y no marca
   una migración como aplicada. Registrar commit, SQL/hash y resultado en el registro
   de publicación. Antes de adoptar Django como gestor sobre esa base, reconciliar
   de forma autorizada dependencias y estado con inspección exacta del esquema;
   no usar --fake/--fake-initial como atajo basado solo en la existencia de la tabla.

## 4. Verificación posterior y publicación

1. Consultar information_schema/pg_catalog y comparar columnas, tipos, defaults,
   nulabilidad, identidad/secuencia, FK, índice parcial y CHECK con el ensayo.
   Verificar has_table_privilege/has_column_privilege y permisos de secuencia con
   el rol web. La revisión anterior del esquema existente debe permanecer idéntica
   salvo los objetos explícitos de la tabla nueva. Confirmar tablas y datos previos
   sin modificaciones; usar las comprobaciones acordadas en la ventana sin escrituras.
2. Con settings de demo autorizados, verificar_demo_pg debe pasar. El arranque actual
   exige la tabla nueva y abortará si falta; no cambiar ese comportamiento para ocultar
   problemas. Confirmar que la aplicación anterior aún funciona antes de publicar.
3. Solo tras autorización de publicación desplegar el commit y probar con registros
   sintéticos acordados el recorrido maestro/directora, sin borrar el historial de
   solicitudes. Confirmar permisos, rechazos, reintentos y cierres académicos.
4. Conservar respaldo, hashes, SQL ejecutado y evidencias. No desplegar automáticamente
   desde este procedimiento ni cambiar autoDeploy.

## 5. Recuperación ante fallos

- Antes de COMMIT: rollback; verificar que no quedó la tabla ni objetos parciales.
- Después de COMMIT, antes de nuevas solicitudes: volver a la aplicación anterior,
  mantener la tabla adicional (no perjudica por sí sola al código anterior), investigar
  permisos/esquema y planificar una reparación autorizada. No eliminarla automáticamente.
- Si ya existen solicitudes/aprobaciones: detener escrituras y respaldar el estado
  actual. Volver de versión no revierte las sesiones canceladas. No restaurar un respaldo
  antiguo ni borrar la tabla, pues se perderían decisiones y cambios concurrentes.
  Cualquier restitución académica requiere conciliación y autorización institucional.
- Restauración completa solo ante incidente que la justifique y autorización específica,
  primero comprobada en destino aislado. Nunca sobrescribir la base como respuesta
  automática a un fallo de despliegue. Registrar incidentes y resultados.
