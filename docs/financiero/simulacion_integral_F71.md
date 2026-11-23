# F7.1 — Simulación institucional integral reutilizable

Base: `5ffb90b2c8954e339b7c789b0ab7e7988ce8a489`, rama
`semana-9-rutas-calificaciones`. Ensayo de datos ficticios previo a F8; no modifica
modelos, migraciones, servicios, reglas, permisos ni pantallas productivas.

## Ejecutar desde Windows

Primero deben estar disponibles los archivos F7.1 en su checkout. El commit de F7.1 se
prepara localmente: `git pull` no puede obtenerlo hasta autorizar su push. Después de
publicarlo, actualizar mediante `git pull --ff-only origin semana-9-rutas-calificaciones`,
con árbol limpio y esa rama activa. No ejecutar migraciones por separado.

Desde PowerShell, en la raíz del repositorio y con el entorno virtual **existente** activado
(si se llama `.venv`, activar con `.\.venv\Scripts\Activate.ps1`):

```powershell
$env:PYTHONUTF8 = "1"
python -B .\iniciar_simulacion.py --comprobar --semilla 711 --fecha 2026-11-22
python -B .\iniciar_simulacion.py --semilla 711
```

El primer comando genera, comprueba y descarta. El segundo genera un escenario referido
al día local actual e inicia `http://127.0.0.1:8000/login/`. Para reproducir exactamente las
cantidades/evidencias de este informe, agregar `--fecha 2026-11-22` también al segundo.
No usar otra fecha esperando los mismos estados de vencimiento o cantidad de asistencias.
Con fecha histórica, al abrir el navegador las consultas actuales usan el reloj real,
por lo que pueden variar solvencia, alertas y antigüedad; el validador reconcilia al `--fecha`.
Para ensayos habituales se recomienda **omitir --fecha**. Las fechas futuras de simulación
se validan con ese reloj simulado, no son afirmaciones sobre operaciones reales.

Ctrl+C detiene el servidor y descarta SQLite en memoria. Una nueva ejecución vuelve a
crear los datos. No hay `--database`, importación de una base existente, reset ni limpieza
como alternativa de recuperación. Puerto 8000 debe estar libre; detener el ensayo básico
antes de iniciar el integral. No ejecutar `manage.py runserver` en otro proceso: perdería
la conexión y los datos en memoria. Autoreload y threading están desactivados.

El lanzador básico F6 (`iniciar_vidasys.py`, conservado fuera de Git) sigue siendo alternativa
sin modificaciones. El segundo lanzador **no** se incorpora a WSGI/ASGI, Render, comandos
normales de Django ni arranque de producción. No ejecuta F8 ni realiza despliegue.

## Seguridad y preparación del esquema

`simulacion/settings.py` es autónomo: no importa `config.settings`, no usa decouple ni
carga `.env`; no toma credenciales de producción. Conserva autenticación, middleware,
CSRF, validadores de contraseña y roles institucionales. Genera SECRET_KEY y contraseñas
nuevas de forma segura en cada proceso, usando PBKDF2; no registra contraseñas en archivos.

Antes de cualquier generación/DDL se comprueban explícitamente motor y nombre tanto en
settings como en la conexión: exclusivamente SQLite y **`:memory:` exacto**. Se rechazan
PostgreSQL, archivos SQLite y URI distintas, aunque indiquen memoria. La inicialización
requiere esquema vacío; el generador requiere tablas de datos vacías y aborta si ya hay
usuarios, matrículas u operaciones. No mezcla ni elimina datos existentes.

`simulacion.entorno.preparar_tablas` aplica las migraciones **solo en esa conexión en
memoria**, luego crea los modelos históricos no administrados mediante schema_editor y
la columna calculada virtual de obligación, siguiendo el mecanismo de pruebas aisladas
existente. Registra el adaptador SQLite de la función SQL base de solvencia. No reescribe
migraciones ni emite DDL contra una conexión persistente. El test runner habitual usa una
URI de prueba propia: por eso el lanzador tiene bootstrap explícito para mantener el nombre
`:memory:` exigido. Las pruebas completas del generador se ejecutan en procesos separados.

El único archivo auxiliar del ensayo es el calendario por ciclo: JSON en un directorio
**temporal** aislado, con limpieza al terminar normalmente; no datos financieros ni BD
persistentes. No se escribe `.financiero-local` del proyecto. Si el proceso se mata de
forma abrupta el sistema podría conservar ese directorio temporal; no contiene credenciales.

El generador envuelve todos los datos en una transacción. Un fallo revierte las filas y
se restaura el reloj. El cierre del proceso destruye la BD incluso si no termina el ensayo.
Se conserva el stash original y el respaldo ZIP, sin aplicarlos ni modificarlos.

## Cuentas de ensayo

La consola imprime los 50 usuarios y una contraseña temporal común a esa ejecución.
No copiarla a documentación, Git ni respaldos. No es una contraseña de producción.

| Rol | Usuario |
| --- | --- |
| Directora | `sim-directora` |
| Administración | `sim-administrador` |
| Secretaría | `sim-secretaria` |
| Maestro | `sim-maestro-01` a `sim-maestro-06` |
| Estudiante | `sim-estudiante-01` a `sim-estudiante-40` |
| Pastor Principal | `sim-pastor-principal` |

Los alumnos 01–20 pertenecen al primer año de la muestra; 21–40 al segundo. El esquema
no tiene un campo «año del estudiante»: se representa por matrículas en ciclos formativos
I y III, respectivamente, con seis materias distintas por nivel. No se inventa una columna
ni se modifica progresión académica. Catálogos y perfiles se inicializan con sus modelos
(UsuarioManager para cuentas); matrícula y operaciones usan sus servicios institucionales.

## Cronología y reproducibilidad

Se fija una semilla local (`random.Random`, sin modificar el generador global) y UUID5 de
trámites derivados de semilla/fecha/contador. Las contraseñas y hashes de autenticación
son deliberadamente aleatorios y no forman parte de la huella reproducible.

La fecha inicial es el primer día de dos meses antes de la referencia; el ciclo dura seis
meses. En el ejemplo: septiembre 2026–febrero 2027. Matrícula USD 20 y cinco mensualidades
USD 20 con vencimientos de octubre a febrero. Así hay cargos vencidos y no vencidos.

Se ejecuta una agenda ordenada: matrículas, becas, padrinazgos, convenios, cobros y clases,
notas y cierres. El reloj se acota al generador mediante el proveedor datetime de
`django.utils.timezone`; alcanza los defaults de fecha existentes y se restaura al salir.
No se parchan permisos, validaciones, restricciones ni métodos de guardado. No se fuerzan
fechas después de insertar registros ni se modifican saldos o fotos de cierres.
Las operaciones con fecha futura a la referencia no se ejecutan. Las clases suspendidas o
canceladas no se convierten en impartidas al avanzar la agenda.

Servicios reutilizados: matrícula/calendario/sesiones/extraordinarias/cierre y solicitudes
académicas; becas; aportes y padrinazgos; convenios/abonos con desglose; cobros con reserva
de recibo; categorías/ingresos/egresos; cajas y anulaciones. Asistencias y calificaciones se
guardan con los mismos `save()` validados usados por la interfaz, sin bulk_create ni atajos
para eludir el cierre. Dos injustificadas cierran la inscripción y cesa su registro ordinario;
no se inventan calificaciones faltantes para esos casos. La captura docente no concede
acceso al portal: ese acceso conserva la comprobación financiera vigente.

La huella reproducible incluye nombres, libro de control de operaciones, cargos y notas;
excluye contraseñas, hashes de autenticación y tiempos. Dos procesos independientes con
semilla 711 y fecha 2026-11-22 producen la misma huella y todos los mismos esperados.

## Cantidades observadas — semilla 711, referencia 2026-11-22

| Entidad | Cantidad |
| --- | ---: |
| Estudiantes / por año | 40 / 20 y 20 |
| Usuarios / maestros / materias | 50 / 6 / 12 |
| Ciclos / cursos | 2 / 12 |
| Cursos finalizados / activos | 6 / 6 |
| Matrículas / inscripciones / obligaciones | 40 / 240 / 240 |
| Sesiones | 74: 62 impartidas, 10 programadas, 1 suspendida y 1 cancelada |
| Asistencias | 1.236: 1.176 presentes, 36 justificadas y 24 injustificadas |
| Calificaciones | 148, incluidas provisionales de cursos activos |
| Inscripciones aprobadas / reprobadas por nota | 70 / 38 |
| Reprobadas por inasistencia / cursando | 12 / 120 |
| Solicitudes académicas | 4: cancelación aprobada y pendiente; corrección aprobada y pendiente |
| Pagos académicos | 132, incluidos 2 recibos anulados |
| Becas / solicitudes | 8 / 9: ocho autorizadas, una pendiente |
| Padrinazgos autorizados / solicitudes | 10 / 11: ocho grupos principales y dos combinados; una pendiente |
| Convenios / cuotas | 4 / 12; tres ACTIVO y uno CUMPLIDO |
| Donantes / recepciones / líneas Donacion | 5 / 14 / 29 |
| Ingresos | 32: 18 administrativos y 14 recepciones; dos anulados |
| Solicitudes de egreso | 15: 11 aprobadas, 3 pendientes, 1 rechazada |
| Desembolsos Egreso | 10, uno anulado; queda uno autorizado sin desembolso |
| Movimientos de caja | 174: un origen por cada pago, ingreso o egreso |
| Cajas cerradas / abiertas | 10 / 2 |
| Solventes / insolventes | 31 / 9 |

Distribución principal: 20 con cobros ordinarios, 8 con becas, 8 con padrinazgos y 4 con
convenios. Dos becarios reciben además padrinazgo sobre obligaciones compatibles, sin
acumular descuentos. Hay becas 50/100 %, coberturas parciales/totales, sin recepción,
con recepción parcial/completa, compromiso vencido protegido y compromiso de inicio futuro.
Cierres cuadrados y con diferencia USD 1 documentada; fondos iniciales separados de ingresos.

**Límite real:** no existe servicio vigente para transicionar formalmente un convenio a
`INCUMPLIDO`. No se escribió ese estado directamente ni se inventó un procedimiento.
Se generaron dos convenios ACTIVO con cuotas vencidas e insolvencia consecuente, uno ACTIVO
con cuotas futuras y uno CUMPLIDO. El filtro literal INCUMPLIDO queda vacío. Su operación
institucional necesita una decisión/implementación posterior, no un cambio en esta simulación.

## Libro de control y totales esperados

El libro se forma con **los importes de entrada** a cada servicio, tipo, método, aplicaciones,
fecha y anulaciones confirmadas; no calcula sus esperados llamando a F7 ni a sus helpers.
Se concilian resultado, saldos, becas, compromisos, contratos, caja, solvencia, notas y HTTP.

| Concepto | USD |
| --- | ---: |
| Matrículas recibidas vigentes, fuera de convenios | 450,00 |
| Mensualidades recibidas vigentes, fuera de convenios | 1.480,00 |
| Pagos mediante convenios | 160,00 |
| Ingresos administrativos vigentes | 321,00 |
| Donaciones generales vigentes | 115,00 |
| Donaciones dirigidas | 8,00 |
| Aportes de padrinazgos recibidos | 230,00 |
| **Ingresos efectivos vigentes** | **2.764,00** |
| Egresos desembolsados vigentes | 86,00 |
| **Resultado financiero** | **2.678,00** |
| Anulados informativos, incluidos egresos; no sumar | 42,00 |
| Obligaciones originales | 4.800,00 |
| Descuentos por becas | 520,00 |
| Pagos académicos vigentes aplicados | 2.090,00 |
| Donaciones aplicadas a obligaciones | 238,00 |
| **Saldo financiero actual** | **1.952,00** |
| Protección de padrino efectiva pendiente | 640,00 |
| Saldo en convenio | 320,00 |
| Saldo directo sin convenio | 992,00 |
| **A cargo de estudiantes, incluido convenio** | **1.312,00** |
| Compromisos activos pendientes de recepción (informativo) | 760,00 |

Controles: `4800 - 520 - 2090 - 238 = 1952` y `640 + 320 + 992 = 1952`.
Compromiso total autorizado de padrinazgos USD 990; recibido USD 230; pendiente USD 760.
USD 120 corresponden a inicio futuro, por eso no son protección efectiva hoy.
No sumar compromisos como ingresos, becas como egresos, ni cuotas nuevamente a la deuda.
Gastos por categoría vigentes: Servicios USD 38; Material didáctico USD 18; Mantenimiento
USD 30. Anular un desembolso no recupera su salida física: el arqueo conserva esa diferencia
respecto del resultado. Retenciones y transferencias físicas se concilian por separado.

## Comprobaciones y rendimiento

[Resultado verificable del escenario](../evidencias/F71/resultado_simulacion.json): ocho
reportes y 24 combinaciones HTML/CSV/impresión, filas paginadas, filtros de fecha/método/
estudiante/ciclo; controles por obligación, solvencia independiente por estudiante y acceso
al portal, notas y estados definitivos, fuentes únicas, fotos de caja e historial de anulaciones.
Consulta sin escrituras verificadas durante la construcción de los ocho reportes.
Reejecución del generador sobre datos existentes bloqueada sin modificar pagos.

El resumen registra generación y validación en segundos. El conteo SQL reinicia el log
antes de cada medición para no falsearlo al llenarse la cola de debug durante la generación.
La evidencia concreta contiene los tiempos y consultas de esa ejecución, no estimaciones.
Con 40 estudiantes, no se observó un bloqueo de rendimiento en los reportes locales;
no se extrapola a volumen ilimitado, hardware Windows ni PostgreSQL.

Pruebas de referencia y nuevas: 605 anteriores + 15 nuevas del generador (620 en total).
Incluyen rechazo de motores/nombres no permitidos sin conexión, cambio de año, configuración
autónoma, dos ejecuciones reproducibles, cantidades exactas, dinero real/compromisos,
regresión de los ocho reportes, solvencia, privacidad del resumen y rollback/restauración del
reloj ante fallo deliberado. Django check, migraciones sin cambios y diff --check.

```powershell
python -B manage.py test --settings=academico.test_settings --noinput
python -B manage.py check --settings=simulacion.settings
python -B manage.py makemigrations --check --dry-run --settings=simulacion.settings
```

El test runner completo sigue siendo el SQLite efímero existente; los tests integrales del
generador lanzan sus procesos explícitos `:memory:`. No usar estas instrucciones con
settings de producción.


### Mediciones de esta ejecución

Generación: **17.563 s**; validación: **1.798 s**. Son tiempos locales del entorno de ensayo.

| Reporte | Constructor Python (ms) | Consultas SQL | Navegación HTTP mediana (ms, n=6) |
| --- | ---: | ---: | ---: | ---: |
| panel | 102.2 | 32 | 92 |
| resultados | 15.2 | 7 | 63.5 |
| cuentas | 24.7 | 12 | 76.5 |
| solvencia | 22.0 | 12 | 67 |
| beneficios | 28.4 | 18 | 78 |
| convenios | 19.9 | 12 | 60 |
| cajas | 2.6 | 2 | 42 |
| auditoria | 27.4 | 18 | 70 |

También se compararon las diez agrupaciones anteriores contra el CSV exportado (siete orígenes de ingreso y tres categorías de egreso), sin diferencias.

## Recorrido de revisión y F8

1. Entrar como Directora. Abrir F7 con fechas vacías para visualizar septiembre–noviembre,
   comparar totales anteriores y los tres meses del gráfico; revisar pendientes y resolver
   únicamente cuando se desee alterar conscientemente el escenario.
2. Cuentas: 240 obligaciones, paginación y distribución. Solvencia: 31/9 al corte del ejemplo.
   Beneficios: becas, coberturas combinadas, compromiso vencido protegido e inicio futuro.
3. Convenios: cumplido, vigente futuro y mora por cuotas. Caja: diez fotos, diferencias,
   efectivo retenido y transferencias. Auditoría: decisiones, anulaciones y regularización.
4. Exportar CSV e imprimir selección completa. Cambiar estudiante/ciclo/método; comprobar
   que filtro de período no se presenta como saldo histórico.
5. Secretaría: cobro de `SIM-017`, becas y convenios pendientes. Los pagos nuevos requieren
   su caja propia abierta. Administración tiene otra caja propia, sin autorizar becas/egresos.
6. Maestro 01: dos cursos finalizados, lectura de asistencia/libro y solicitud de corrección.
   Maestro 04: cursos activos para revisar pendientes. No reabrir cursos cerrados.
7. Estudiante 29: cobertura F6 y acceso académico sin ingreso ficticio. Estudiante 17:
   cuenta disponible, académico restringido por insolvencia. Pastor no accede a F7.

[114 pantallas y evidencias](../evidencias/F71/README.md), con login real, CSV, PDF y rechazos
por rol. Los hallazgos medidos están en [F8](../backlog/F8_ui_ux.md): libro docente ancho,
mensajes de solo lectura, cobro sin suma dinámica, 32.712 px de cuentas móviles, navegación y
selectores. No se implementó el rediseño ni se hicieron entrevistas con usuarios reales.

## Pendientes obligatorios antes de despliegue

- Unificar solvencia Django/SQL incluyendo F6 y revisar todos sus consumidores.
- Validar restricciones, transacciones, rollback y concurrencia en PostgreSQL aislado.
- No confundir las pruebas SQLite, tiempos locales o adaptador de solvencia con esa validación.
- No se accedió a Neon, se migró una base persistente ni se desplegó.

Archivos: `iniciar_simulacion.py`, paquete `simulacion` (settings, entorno, generador,
validación y tests), este manual, evidencias F71 y actualización del backlog F8.
No se modifica el código funcional de F1–F7 ni las migraciones existentes.
