# F4 — Anulaciones autorizadas y caja por operador

## Alcance y decisiones institucionales confirmadas

Secretaría solicita la anulación de un recibo; únicamente una cuenta activa con rol
DIRECTORA puede resolverla. Administración consulta y cobra, incluso si es superusuario,
pero no puede solicitar ni autorizar anulaciones. Maestro, Pastor Principal y Estudiante
no reciben acceso interno. El portal del estudiante conserva sus filtros de pertenencia.

Se confirmó durante esta entrega:

- Todo **nuevo** cobro ordinario o de convenio exige caja propia abierta. No se abren
  cajas automáticamente ni se asignan retrospectivamente recibos históricos.
- Un convenio CUMPLIDO con saldo restablecido por anulación vuelve a ACTIVO. Un convenio
  INCUMPLIDO conserva esa condición; la insolvencia por cuota vencida sigue siendo
  determinada por el SQL existente. No se redefinen vencimientos ni se crean recargos.
- Anular administrativamente un recibo **no devuelve dinero**. El efectivo ingresado
  permanece en el arqueo, separado de los cobros vigentes como efectivo anulado retenido,
  pendiente de regularización. Las transferencias nunca aumentan el efectivo esperado.
- Se bloquean anulaciones de recibos sin caja y de cajas cerradas. Tampoco se habilitan
  devoluciones, correcciones bancarias, reaperturas ni ajustes posteriores al cierre.
  Requieren una política institucional y otra implementación autorizada.
- Un operador puede abrir otra caja después de cerrar la anterior, incluso el mismo día.
  No se impone una sola caja por institución ni una sola caja por fecha.

## Datos y migración preparada

`financiero/migrations/0003_caja_y_anulaciones.py` crea únicamente:

| Tabla | Finalidad y controles |
| --- | --- |
| `caja` | Operador, UUID de apertura, fondo, fechas, observaciones y cierre. Una ABIERTA por operador mediante índice único parcial; fondo no negativo; coherencia de cierre y diferencia exacta en BD. |
| `movimiento_caja` | Un movimiento por Pago (OneToOne), operador, fecha, método, importe y referencia originales; importe positivo y método válido. |
| `solicitud_anulacion` | Pago, UUID, solicitante, motivo, instantánea anterior, decisión, directora, fecha, observaciones y valores aplicados. Una pendiente y una aprobada por pago, coherencia de resolución y motivo de rechazo. |

Los movimientos originales son inmutables por el modelo; su estado financiero procede
de `Pago.estado`, sin duplicarlo en otra columna. La foto de cierre sí conserva el estado
y los valores de todos los movimientos al cerrar. Los cierres y resoluciones definitivas
no admiten `save()` ni `delete()` posteriores. Los modelos nuevos no se registran en
Django Admin; Pago, ConvenioPago y AplicacionPagoCuota conservan su protección de escritura.
Estas garantías cubren servicios, modelos e interfaces institucionales, no escrituras SQL
o `QuerySet.update()` ejecutadas por una cuenta externa con privilegios sobre la BD.

Las migraciones financieras 0001 y 0002 permanecen idénticas. No se modifica físicamente
ninguna tabla `managed=False`, función SQL, restricción histórica ni configuración.
La introspección de SQLite efímero verifica las tres tablas nuevas; el SQL generado de
0003 contiene DDL únicamente sobre ellas (más sus copias temporales internas SQLite).

## Servicios, bloqueos y auditoría

Orden común para las operaciones que comparten filas:

`Usuario actor → Caja → Estudiante → Obligacion por PK → ConvenioPago por PK → CuotaConvenio por PK → Pago → SolicitudAnulacion`.

Los servicios de cobro incorporan Caja antes de Estudiante. Becas y convenios mantienen
sus bloqueos existentes sobre estudiante/obligaciones y nunca toman Caja después de ellos.
El cierre toma Usuario → Caja. Los cobros y aprobaciones mantienen el bloqueo de Caja
hasta terminar; no pueden intercalarse con un cierre de esa misma caja.

Pago y MovimientoCaja se crean en la misma transacción tanto en cobros ordinarios como
en convenios. Si falla el movimiento, se revierten recibo, detalles, aplicaciones y estados.
La reserva firmada y la numeración vigentes se conservan: no se reutiliza un número anulado.
Un reenvío de cobro ya registrado devuelve su recibo sin crear un nuevo movimiento, incluso
si después se cerró aquella caja. No revive recibos anulados.

La solicitud no cambia dinero. Conserva todos los campos originales del pago y de sus
aplicaciones, datos/saldos de las obligaciones del estudiante, convenio/cuotas y caja.
La comparación de Dirección produce una revisión firmada con vigencia de dos horas,
ligada a directora, solicitud, observaciones e instantánea. Aprobar vuelve a bloquear y
validar todo. Cambios posteriores invalidan la aprobación; se puede rechazar la solicitud
obsoleta y presentar otra. Se prioriza integridad: incluso cambios descriptivos o en otras
obligaciones del estudiante pueden exigir una nueva solicitud.

La aprobación comprueba además permisos actuales del solicitante, caja abierta, coherencia
entre recibo y movimiento, suma de aplicaciones, ausencia de obligaciones anuladas,
convenios compatibles y conciliación de cuotas con obligaciones. Un pago ordinario seguido
por un convenio que incluye su obligación no puede anularse automáticamente. Se bloquean
saldos excedentes o inconsistencias históricas; no se crean créditos ni reparaciones.

El único punto de anulación es `anulaciones.resolver`, dentro de `transaction.atomic()`:
actualiza exclusivamente `Pago.estado`, recalcula obligaciones con el mecanismo existente,
recalcula cuotas/convenio y solvencia y resuelve la solicitud. Se preservan número, fecha,
importe, método, operador, referencia, observaciones y todos los detalles/APC originales.
Las consecuencias anteriores y aplicadas quedan en el historial. Una decisión idéntica
repetida devuelve la existente; una contradictoria se rechaza. Rechazar exige motivo y
no modifica datos financieros, incluso si la caja ya cerró o la solicitud quedó obsoleta.

## Arqueo y consultas

`Esperado = fondo inicial + entradas físicas originales de efectivo − salidas físicas registradas`.

F4 no registra salidas: su total es cero. El efectivo anulado retenido sigue incluido en
las entradas físicas. Los ingresos financieros vigentes excluyen pagos anulados, igual
que los reportes financieros previos y la cuenta del estudiante. No se equiparan ingresos
financieros vigentes con efectivo físicamente presente en caja.

Comparar el arqueo muestra esperado, contado y diferencia. Confirmar exige la revisión
firmada sin nuevos movimientos, guarda foto de totales y movimientos, fecha, contado,
diferencia y observaciones y cierra. Un reintento idéntico conserva el cierre original.
Un arqueo positivo es sobrante, negativo faltante y cero caja cuadrada. Las transferencias
se informan separadamente y no forman parte del contado físico.

Secretaría consulta solo sus cajas; Administración y Dirección pueden consultar todas,
pero únicamente el operador puede cerrar la suya. Se ofrecen filtros por fecha de apertura,
operador y estado, listado de movimientos, impresión y CSV de cajas y movimientos. Se
reutiliza la neutralización de fórmulas CSV de Reportes. No es contabilidad integral.

Rutas bajo `/finanzas/`:

- `caja/`, `caja/apertura/`, `caja/<id>/`, `caja/<id>/cierre/`.
- `anulaciones/`, `anulaciones/nueva/<pago_id>/`, `anulaciones/<solicitud_id>/`.
- Caja o detalle con `?formato=csv`; los filtros permanecen aplicados.
- Recibo habitual: muestra ANULADO y motivo, directora y fecha también al imprimir.

## Pruebas y validación realizada

**414 pruebas aprobadas: 351 anteriores y 63 nuevas de F4**, exclusivamente SQLite en
memoria. Las tres fixtures financieras existentes ahora abren cajas ficticias para sus
cobros. La prueba de bloqueos de becas incorpora el paso Caja sin eliminar su cobertura.
Se conservan todas las pruebas anteriores.

Cobertura F4: permisos y roles actuales, CSRF, UUID/reenvíos, duplicados y restricciones
BD, saldo y solvencia, recibos intactos, convenios parciales/cumplidos/incumplidos, cuotas
vencidas, caja obligatoria, movimientos únicos, efectivo/transferencias, efectivo anulado
retenido, faltantes/sobrantes, fotografías cerradas, datos obsoletos, historial, acceso
por identificadores, manipulación de actor, Admin, impresión/CSV y rollback en puntos de
escritura de cobro/anulación/cierre. También se comprueba regresión del reporte de pagos.

`manage.py check`, `makemigrations --check --dry-run` y `git diff --check`: sin problemas.
Todos los comandos Django se ejecutan con `--settings=academico.test_settings`, y valores
de conexión ficticios. El runner rechaza cualquier destino que no sea SQLite en memoria.

Comprobación con Chromium/Playwright en otro proceso SQLite efímero: pantallas de cajas,
detalle, arqueo, búsqueda y decisión como Secretaría/Dirección, anchos 1366 y 390 px, 18
navegaciones HTTP 200 sin desbordamiento horizontal. No usa el servidor de ensayo anterior
ni sus datos. La identidad gráfica y los recursos estáticos existentes no se modifican.

Para repetir la suite desde PowerShell con el entorno virtual activo:

```powershell
$env:SECRET_KEY='solo-pruebas-aisladas'
$env:DB_NAME='unused'; $env:DB_USER='unused'; $env:DB_PASSWORD='unused'
$env:DB_HOST='127.0.0.1'; $env:DB_PORT='1'
python -B manage.py test --settings=academico.test_settings --noinput
python -B manage.py check --settings=academico.test_settings
python -B manage.py makemigrations --check --dry-run --settings=academico.test_settings
```

## Recorrido manual inmediato en SQLite efímero

Usar un ensayo **nuevo** del checkout actualizado con el lanzador SQLite en memoria de
las pruebas funcionales anteriores. El runner instala 0003 en memoria y después prepara
las tablas históricas ficticias, sin PostgreSQL. Mantener `runserver --noreload --nothreading`
en ese mismo proceso/conexión; ejecutar `migrate` a secas sobre una base vacía no crea las
tablas `managed=False` ni el adaptador de solvencia. No usar configuraciones de Neon.
Los usuarios y contraseñas ficticios del ensayo se generan solo en memoria, no en Git.

1. Secretaría: Finanzas → Caja → Abrir mi caja, fondo USD 10.00.
2. Matricular estudiante ficticio si todavía no existe. Cobrar una obligación de USD
   20.00 en efectivo. Verificar un solo movimiento, efectivo esperado USD 30.00.
3. Registrar otro cobro por transferencia; confirmar que no aumenta el esperado físico.
4. Finanzas → Anulaciones: buscar recibo por número, estudiante, referencia o fechas,
   abrirlo y solicitar con motivo. Confirmar que aún no cambian saldos.
5. Dirección: bandeja de Anulaciones → revisar originales y consecuencias → comparar →
   confirmar aprobación. Verificar ANULADO, saldo restablecido, motivo/fecha/directora
   en recibo y exclusión del reporte de ingresos. No hubo devolución.
6. Secretaría: caja sigue con efectivo físico esperado USD 30.00; los USD 20.00 anulados
   aparecen retenidos. Comparar contado USD 30.00 y confirmar; diferencia cero.
7. Dirección: consultar/filtrar caja cerrada, imprimir fotografía y exportar CSV. Intentar
   una nueva anulación del cierre: debe bloquearse sin modificar su fotografía.
8. En otro ensayo o caja abierta, pagar un convenio hasta CUMPLIDO y anular su abono desde
   Dirección: pasa a ACTIVO, restablece cuotas y originales, conserva APC y demás pagos.
9. Repetir arqueos con contado menor y mayor para verificar faltante/sobrante. Comprobar
   que Administración cobra/consulta pero no solicita ni resuelve anulaciones.

## PostgreSQL y futura incorporación (no ejecutada)

No se accedió a Neon, no se ejecutaron migraciones persistentes ni despliegues. Sigue
pendiente ensayar bloqueos reales simultáneos (cobro/cierre/anulación, becas y convenios),
índices únicos parciales, precisión NUMERIC, FK diferidas, triggers y funciones reales de
recalcular estado/solvencia en **PostgreSQL aislado**. SQLite no certifica esas propiedades.
También se debe reconciliar cualquier movimiento SQL externo a los servicios.

Antes de incorporar F4 a una base existente, en una intervención autorizada por separado:

1. Confirmar base, esquema, rama y versión; verificar que financiero 0001 y 0002 consten
   aplicadas y que las tablas nuevas no existan. Revisar dependencias y equivalencia del
   esquema histórico. Detenerse ante divergencias; no usar el inicializador de base vacía.
2. Obtener respaldo verificable de esquema, datos e historial `django_migrations`, y probar
   restauración en un destino aislado. Acordar una ventana sin cobros/cierres.
3. Generar y revisar el SQL de 0003 con el backend PostgreSQL aislado. Debe crear solamente
   las tres tablas nuevas, sus FK, secuencias, índices y checks; nunca modificar tablas
   históricas. Validarlo y ensayar fallos/recuperación antes de tocar una base existente.
4. Aplicar exclusivamente el cambio aprobado mediante el procedimiento controlado de
   despliegue y registrar su historial coherente. No habilitar `migrate` automático ni
   desactivar las guardias de `config.settings_demo_pg`.
5. Conceder al rol web únicamente SELECT/INSERT/UPDATE sobre las tablas nuevas y USAGE/SELECT
   sobre sus secuencias según el esquema real. No ampliar facultades sobre tablas antiguas.
6. Verificar columnas, FK, índices y checks, estado de migraciones, permisos y un recorrido
   ficticio de apertura/cobro/anulación/cierre en el ensayo. Revisar solvencia SQL real y
   conciliación de cuotas. Los recibos anteriores siguen sin caja y no se rellenan en masa.
7. Si falla antes de registrar movimientos, revertir la instalación transaccional según
   el ensayo. Si ya hay datos, detener escrituras y preservar el historial; no borrar las
   tablas ni retroceder a una versión que acepte cobros sin caja. Restaurar únicamente el
   respaldo completo verificado conforme al plan autorizado, evitando pérdidas posteriores.

El comando técnico preexistente `probar_flujo_demo_pg` prepara un flujo anterior sin caja;
no forma parte del recorrido F4 y no se ejecutó. Antes de reutilizarlo hay que adaptar su
fixture al requisito de apertura y a la nueva tabla, sin quitar sus guardias de destino.
