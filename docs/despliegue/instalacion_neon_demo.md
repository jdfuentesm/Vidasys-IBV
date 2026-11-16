# Instalación del esquema de demostración en Neon

Preparación estática; no se han ejecutado SQL, migraciones ni conexiones para
esta revisión. Destino exclusivo: `vidasys_demo`, rol `vidasys_demo_limitado`.
No es una restauración del esquema institucional ni una migración de sus datos.

## Instalación futura (requiere autorización)

Desde la raíz del repositorio, con el entorno virtual y las variables de entorno
ya configuradas para Neon, sin imprimirlas ni poner contraseñas en el comando:

```bash
python manage.py preparar_demo_pg --settings=config.settings_demo_pg --base-esperada vidasys_demo --usuario-esperado vidasys_demo_limitado --confirmar
```

No ejecutar `migrate`, ni todos los archivos SQL por orden numérico. El comando
solo acepta la configuración demo, la base `vidasys_demo` y el usuario
`vidasys_demo_limitado`; también los exige si se omiten los parámetros. Antes del DDL
contrasta configuración, base y usuario efectivos, fija `search_path=public`,
serializa instalaciones con un bloqueo transaccional y exige que `public` no
tenga relaciones, funciones ni tipos existentes. Cero tablas no basta.
`settings_demo_pg` rechaza roles administrativos y servidores que anuncien una
base `gestion_ibv` en su catálogo: nunca abre una conexión a esa base.
Estas comprobaciones son defensas adicionales, no sustituyen seleccionar la
conexión Neon correcta en las variables de entorno.

Toda la creación ocurre en una transacción: cualquier error revierte el DDL.
Una segunda ejecución sobre un esquema instalado se rechaza; no hay limpieza,
DROP ni reinicialización automática. Si falla, conservar el error sin secretos,
corregir la causa y comprobar el estado antes de reintentar; no borrar objetos
para forzar la instalación.

## Objetos y orden

1. El `schema_editor` de Django crea todos los modelos registrados, incluidos
   `managed=False`, y sus relaciones intermedias automáticas. Incluye usuarios,
   grupos, permisos, sesiones y administración Django; estudiantes, maestros,
   materias, ciclos, cursos, matrículas, inscripciones, sesiones de clase,
   asistencias y calificaciones; obligaciones, conceptos, pagos y detalles,
   convenios, cuotas, aplicaciones, becas, ingresos, egresos, donaciones y
   calendario financiero. Reportes no tiene tablas propias.
   Se crean las claves primarias, secuencias/identidades de los AutoField,
   índices, claves foráneas y restricciones únicas declaradas en los modelos.
2. Se añade `obligacion.monto_final`, columna generada almacenada
   (`monto_original - monto_descuento`): el modelo la representa como propiedad,
   pero las consultas SQL requieren la columna física.
3. `database/scripts/demo_restricciones.sql`: restricciones de ciclo formativo,
   estados de calificación y sesión, y autorización de sesiones extraordinarias.
   Los `choices` y validadores Python no generan estos CHECK automáticamente.
4. `15_funcion_solvencia_estudiante.sql`: función de solvencia con convenios.
5. `16_vw_acceso_portal_estudiante.sql`: vista de acceso al portal.
6. `17_vista_estado_cuenta_estudiante.sql`: vista de detalle y saldos.
7. `14_vw_resumen_cuenta_estudiante.sql`: resumen; depende del script 17,
   aunque su número sea menor.
8. `demo_recalcular_estado.sql`: función de recálculo y función/trigger ante
   cambios de estado de pago. Su instalación no registra pagos ni obligaciones.

La secuencia de `pago.id_pago` permite reservar correlativos mediante `nextval`;
`numero_recibo` es único. Las secuencias pueden dejar huecos tras cancelaciones
o rollback. `calendario_financiero.datos` usa JSONB persistente compartido en
PostgreSQL. Los CHECK recuperados proceden de reglas existentes, no tarifas
nuevas. Las asociaciones de usuario/estudiante y demás unicidades se crean
según los modelos actuales, sin asignar cuentas automáticamente.

## Archivos excluidos y límites

- No hay un DDL inicial completo institucional: se reconstruye un esquema
  sintético desde los modelos actuales. No se pueden certificar restricciones
  institucionales que no estén representadas en el repositorio.
- `14_trigger_estado_pago.sql` es una prueba que modifica pagos existentes,
  pese a su nombre. No es parte de la instalación.
- `16_actualizar_estados_obligaciones.sql` es mantenimiento opcional; no se
  necesita para inicializar y no se invoca su actualización masiva.
- Los scripts 18–24 son parches para esquemas existentes. Sus columnas y
  relaciones ya están en los modelos; los CHECK necesarios se extraen al
  archivo demo. No ejecutar esos parches en bloque.
- `20_catalogo_academico_inicial.sql` contiene información institucional y
  actualizaciones generales de docentes/materias; además no satisface por sí
  solo el campo obligatorio actual de ciclo formativo. Está excluido.
- `admin_log_*` son diagnóstico/reparación histórica, no inicialización.
- Los scripts seleccionados no crean/eliminan bases, roles ni otros esquemas.
  Las funciones/vistas usan CREATE OR REPLACE: por eso se verifica también la
  ausencia de funciones y tipos, no solo tablas, antes de instalarlas.
- `managed=False` impide que las migraciones ordinarias creen estas tablas;
  el inicializador las crea explícitamente. Las FK físicas generadas por Django
  no reproducen necesariamente las acciones SQL ON DELETE de esquemas antiguos;
  la protección/eliminación de aplicación sigue las reglas de los modelos.
- No se cargan datos, cuentas, tarifas ni calendarios. La demo requerirá después
  una inicialización ficticia independiente y autorizada.

## Permisos y comprobación posterior

Se necesita CONNECT a la base, USAGE y CREATE en `public`, y USAGE del lenguaje
`plpgsql` (normalmente concedido por defecto). CREATE ya fue confirmado por el
operador; los demás se comprobarán al ejecutar el comando. El propietario de
los objetos nuevos puede crear sus FK, triggers e índices y utilizar sus
secuencias. No requiere SUPERUSER, CREATEDB, CREATEROLE ni BYPASSRLS. No se
proponen GRANT indiscriminados ni cambios de credenciales. Si ya hay extensiones
con objetos en `public`, el control de esquema vacío rechazará la instalación:
revisar ese caso expresamente, sin eliminar extensiones automáticamente.

Tras una instalación autorizada, comprobar sin reparar ni insertar datos:

```bash
python manage.py verificar_demo_pg --settings=config.settings_demo_pg
```

Verifica tablas, relaciones críticas, unicidades, funciones, vistas, secuencia de
pagos, columna generada y calendario JSONB. Hasta ejecutarlo y validar las
operaciones mínimas en la demo, la compatibilidad PostgreSQL está revisada en
fuentes, no confirmada en Neon. No se autoriza producción por este procedimiento.
