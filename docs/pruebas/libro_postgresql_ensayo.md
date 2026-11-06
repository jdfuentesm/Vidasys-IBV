# Ensayo masivo del Libro de Calificaciones — PostgreSQL 18

**Estado:** procedimiento implementado, pendiente de autorización de ejecución.
No se ha ejecutado inspección, preparación, prueba ni limpieza en PostgreSQL como
parte de su implementación. La validación automatizada usa SQLite de memoria y
simulaciones del catálogo PostgreSQL. No constituye certificación del esquema real.

## Alcance y condiciones obligatorias

- Rama `semana-9-rutas-calificaciones`. La lógica académica no cambia.
- Base exacta: `gestion_ibv_ensayo`, ya existente y con el esquema compatible.
- La base principal `gestion_ibv` no se usa ni se copia desde este procedimiento.
- No se ejecutan migraciones, DDL, SQL externo ni ajustes de secuencias.
- Un ciclo existente se usa solo como referencia y no se modifica ni elimina.
- No se deben ejecutar otros escritores ni cambios de esquema durante el ensayo.
- El usuario de conexión debe ser un rol limitado de ensayo, sin SUPERUSER,
  CREATEDB, CREATEROLE, REPLICATION o BYPASSRLS y **sin privilegio CONNECT a ninguna
  otra base conectable**, incluidas `gestion_ibv` y `postgres`.

**Importante:** PostgreSQL suele otorgar CONNECT a PUBLIC. Un REVOKE únicamente
sobre el rol no elimina ese acceso heredado. Este comando comprueba los permisos
efectivos y se detiene si no se demuestra el aislamiento. Un DBA debe preparar
el rol/entorno por un procedimiento independiente previamente autorizado; este
trabajo no cambia roles, permisos, pg_hba.conf ni la base principal. No usar el
usuario `postgres`. Una restricción solo en pg_hba.conf no satisface esta prueba
conservadora de privilegios de catálogo.

También se rechazan servidores externos, extensiones adicionales a plpgsql,
particiones/RLS en las tablas de trabajo, disparadores propios activos, reglas,
tipos propios, dependencias de funciones propias y FK sin validar. La inspección
es deliberadamente restrictiva; puede bloquear un esquema legítimo con funciones
financieras. No las deshabilita ni incluye una opción de omisión. En ese caso,
detenerse y solicitar una revisión específica de sus efectos. Si el DBA modifica
el esquema concurrentemente, este procedimiento no puede garantizar su aislamiento;
por eso requiere una ventana exclusiva y ausencia de administradores concurrentes.

## Capas de protección

`config.settings_ensayo` exige DB_NAME exacto, un único alias default y ausencia
de routers. Registra una guardia en cada conexión nueva y también en conexiones
ya abiertas. La guardia comprueba la configuración y `current_database()` antes
de cada escritura. Nunca habilita DDL. INSERT/UPDATE/DELETE están prohibidos por
defecto y se habilitan solo dentro de la acción confirmada del comando.
El SET que inicia una transacción de solo lectura se ejecuta antes del SELECT de
la guardia para respetar el orden exigido por PostgreSQL; no escribe datos.

Las sesiones del cliente de prueba se firman en cookies temporales: no se crean
filas django_session. Se utiliza force_login exclusivamente dentro del proceso
del comando para el docente ficticio; puede actualizar su ultimo_acceso, nunca
el de otro usuario. El docente tiene contraseña inutilizable y no acceso Admin.
No se entrega contraseña ni se registra cookie/token alguno.

Esta configuración es **solo para estos comandos**, no para runserver, Admin,
migrate, flush, createsuperuser ni el runner habitual de pruebas PostgreSQL.
No hay un flag para saltar las comprobaciones. Los escenarios usan la vista real
del libro con CSRF habilitado y conservan las revisiones firmadas de cada fila.

## Datos y manifiesto

`preparar` crea un identificador aleatorio `EL-<16 caracteres hexadecimales>`:
1 usuario MAESTRO activo, 1 perfil Maestro, 1 materia, 1 curso, 4 estudiantes,
4 matrículas y 4 inscripciones: **16 registros nuevos**. Los nombres incluyen
FICTICIO; códigos y relaciones quedan registrados en el manifiesto firmado.
No se reutilizan usuarios, estudiantes, materias o cursos existentes.

El ciclo debe tener número 1–4 y fechas coherentes; la materia usa el mismo número
y las fechas del curso quedan dentro del ciclo. Los valores PRESENCIAL, ACTIVO,
ACTIVA y CURSANDO siguen los modelos/pruebas actuales. Si los CHECK del servidor
no los aceptan, se revierte la creación: no se relajan restricciones.

El manifiesto está fuera del repositorio. Incluye versión, base, huella del
servidor/base, identificador de ejecución, IDs, marcas de propiedad y fase.
La huella es un hash de metadatos técnicos, no contiene direcciones en claro.
La firma utiliza el SECRET_KEY local existente: no cambiarlo ni compartirlo
mientras dure el ensayo. La firma impide alteraciones, **no cifra** el contenido.
No contiene contraseñas, hashes de contraseñas, datos personales, cookies o tokens.
Conservarlo con acceso restringido y no subirlo a GitHub.

Hay dos recursos, archivo y base: no existe una transacción distribuida entre
ellos. Se escribe el manifiesto antes de confirmar la transacción; si el archivo
falla, se revierte el lote. Si el proceso o la conexión fallan durante el commit,
puede quedar un manifiesto cuya fase no corresponde a los registros. No reintentar
ni borrar por prefijo: el comando detecta faltantes y se detiene. Revisar archivo
y base de ensayo antes de una recuperación autorizada. Las secuencias pueden
avanzar incluso en rollback; no se reinician ni se consideran datos a restaurar.

## Acciones independientes

| Acción | Efecto |
| --- | --- |
| inspeccionar | Catálogo y compatibilidad, sin escrituras |
| preparar | Crea 16 registros en una transacción; exige --ciclo-id y --confirmar |
| probar | Escenarios con la vista real; exige --confirmar y fase preparado |
| verificar | Consulta resultados esperados; exige fase probado; sin escrituras |
| limpiar | Sin --confirmar: vista previa y dependencias. Con --confirmar: limpieza exacta |

`probar` no es una prueba de carga. Ejecuta cuatro filas y valida:

1. Una nota fuera de rango rechaza todo el envío y conserva el estado anterior.
2. Un fallo controlado después del primer guardado revierte notas y cierres.
   La inyección existe solo en este proceso; no modifica archivos ni el servidor web.
3. Se guardan 80,00 aprobada; 0,00 reprobada; y 69,00 reprobada. La cuarta fila
   vacía queda pendiente y no crea una calificación: **3 notas nuevas**.
4. Se rechazan lista adulterada, curso ajeno/inexistente y acceso anónimo.
5. Una revisión obsoleta no sobrescribe una modificación posterior. Es una
   simulación secuencial de concurrencia, no una prueba de carreras entre procesos.
6. Se restauran los valores ficticios esperados y se comprueban desde conexión
   nueva después del commit. `verificar` permite repetir la lectura en otro proceso.

No repetir `probar` sobre una ejecución ya probada: falla para no sobrescribirla.
Si se desea repetir todo, verificar/limpiar y utilizar un manifiesto nuevo.

## Windows PowerShell — después de autorización de ejecución

Desde la raíz de VIDASYS-IBV, con venv y dependencias instaladas. DB_HOST, DB_PORT,
DB_USER y DB_PASSWORD deben estar previamente configurados para el rol restringido
de ensayo mediante la configuración segura local. **No pegar contraseñas en el
chat, comandos o manifiestos.** No editar `.env` para esta prueba: DB_NAME del
proceso tiene prioridad temporal. Reiniciar procesos anteriores no cambia sus
variables: no usar un servidor Django que ya estuviera ejecutándose sobre la base
principal para estas pruebas.

Crear una carpeta local fuera del repositorio y conservar la ruta entre sesiones:

```powershell
$carpeta = Join-Path $env:LOCALAPPDATA "VIDASYS-IBV\ensayos"
New-Item -ItemType Directory -Force -Path $carpeta | Out-Null
$manifiesto = Join-Path $carpeta ("libro-" + [guid]::NewGuid().ToString("N") + ".firmado")
$python = Join-Path (Get-Location) "venv\Scripts\python.exe"
$ciclo = Read-Host "ID de un ciclo existente y compatible EN LA BASE DE ENSAYO"
$anterior = [Environment]::GetEnvironmentVariable("DB_NAME", "Process")
function Confirmar-Salida {
    if ($LASTEXITCODE -ne 0) { throw "La acción falló. Detenerse y revisar; no continuar automáticamente." }
}
try {
    $env:DB_NAME = "gestion_ibv_ensayo"
    & $python manage.py ensayo_calificaciones inspeccionar --settings=config.settings_ensayo
    Confirmar-Salida

    # Ejecutar SOLO después de la autorización de escrituras en ensayo:
    & $python manage.py ensayo_calificaciones preparar --settings=config.settings_ensayo --ciclo-id $ciclo --manifiesto $manifiesto --confirmar
    Confirmar-Salida
    & $python manage.py ensayo_calificaciones probar --settings=config.settings_ensayo --manifiesto $manifiesto --confirmar
    Confirmar-Salida
    & $python manage.py ensayo_calificaciones verificar --settings=config.settings_ensayo --manifiesto $manifiesto
    Confirmar-Salida
    Write-Host "Conserve esta ruta para revisar o limpiar: $manifiesto"
}
finally {
    if ($null -eq $anterior) { Remove-Item Env:DB_NAME -ErrorAction SilentlyContinue }
    else { $env:DB_NAME = $anterior }
}
```

Si `inspeccionar` falla no ejecutar los comandos siguientes. No usar `migrate`
para resolverlo. La herramienta no crea la base ni repara esquemas.

## Limpieza selectiva — autorización separada

El manifiesto identifica las claves exactas, no solo un prefijo. Antes de borrar,
se verifican firma/huella, existencia, marcas y relaciones. Se comprueban las FK
físicas, también las no representadas en Django y las de otros esquemas. Cualquier
dependencia ajena o FK compuesta/alternativa detiene la limpieza. Las tablas public
se bloquean conservadoramente sin esperar, y las filas se bloquean para impedir
referencias concurrentes. El rol necesita permisos de bloqueo adecuados; si
faltan, la limpieza se cancela sin ampliar permisos automáticamente.

Se usan DELETE parametrizados por PK en orden inverso de creación, sin el
recolector/cascadas de Django. Las FK se comprueban antes del commit. Se conserva
el ciclo y no se borran registros preexistentes. Si existen notas nuevas fuera del
manifiesto, se detiene en vez de eliminarlas. Tras limpiar, repetir la acción es
una operación sin cambios si ninguno de los IDs volvió a existir.

En otra sesión PowerShell, especificar la ruta exacta del manifiesto guardado:

```powershell
$manifiesto = Read-Host "Ruta completa al manifiesto firmado de esta ejecución"
$anterior = [Environment]::GetEnvironmentVariable("DB_NAME", "Process")
try {
    $env:DB_NAME = "gestion_ibv_ensayo"
    .\venv\Scripts\python.exe manage.py ensayo_calificaciones limpiar --settings=config.settings_ensayo --manifiesto $manifiesto
    if ($LASTEXITCODE -ne 0) { throw "Vista previa fallida; no limpiar." }
    # PARAR AQUÍ, revisar y obtener autorización antes de ejecutar la siguiente línea.
    # .\venv\Scripts\python.exe manage.py ensayo_calificaciones limpiar --settings=config.settings_ensayo --manifiesto $manifiesto --confirmar
}
finally {
    if ($null -eq $anterior) { Remove-Item Env:DB_NAME -ErrorAction SilentlyContinue }
    else { $env:DB_NAME = $anterior }
}
```

No reutilizar una ruta de manifiesto para preparar otra ejecución. No modificar
ni eliminar manualmente el manifiesto mientras sus registros existan.

## Verificación automatizada sin PostgreSQL

No usar settings_ensayo para el runner de pruebas. Usar únicamente SQLite aislado:

```powershell
.\venv\Scripts\python.exe manage.py test core academico --settings=academico.test_settings --noinput
.\venv\Scripts\python.exe manage.py check
```

La suite verifica rechazo de base configurada/real incorrecta, alias, routers,
motores, DDL y escritura sin habilitación; firmas y colisiones de archivos;
bloqueos por rol, acceso externo y catálogo incompatible; creación de ficticios,
preservación del ciclo y datos existentes; escenarios reales de la vista sobre
SQLite y detección de dependencias ajenas simuladas. Sigue pendiente ensayar en
PostgreSQL autorizado el catálogo, locks, FK, limpieza completa y persistencia
entre conexiones reales. No se afirma aislamiento de su instancia hasta que
`inspeccionar` complete satisfactoriamente todas sus comprobaciones.
