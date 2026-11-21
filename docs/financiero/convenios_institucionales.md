# F3 — Convenios de pago institucionales

## Alcance entregado y decisiones confirmadas

Solicitud de Secretaría → comparación y resolución exclusiva de Dirección → convenio,
obligaciones vinculadas y cuotas individuales → pagos/abonos con desglose explícito →
recibo → seguimiento → CUMPLIDO al saldar todas las cuotas. Sin intereses o recargos.
Administración consulta y cobra; no autoriza. El estudiante consulta solo sus propios
convenios, cuotas, movimientos y recibos desde su estado de cuenta. Maestro y Pastor
Principal no reciben acceso nuevo.

Se confirmó expresamente durante F3:

- Se admiten obligaciones de matrícula y mensualidades vencidas Y no vencidas. Se retiró
  únicamente la validación Python que exigía vencimiento pasado en ConvenioObligacion.clean.
  No se modificaron columnas, restricciones físicas ni funciones SQL existentes.
- En cada cobro Secretaría/Administración indica dos desgloses: importes por cuota e
  importes por obligación original. Las sumas deben coincidir exactamente. No hay
  distribución automática ni una regla de prioridad implícita. El mismo Pago vincula
  AplicacionPagoCuota y DetallePago, sin duplicar el efectivo ingresado.
- Modificaciones/cancelaciones con movimientos previos de cuotas permanecen bloqueadas:
  requieren definir el tratamiento de pagos, saldos y condiciones originales. No se
  redistribuye, anula o modifica dinero ya registrado. También se bloquea si existen
  aplicaciones cuyos pagos fueron anulados: conservar historial exige revisión adicional.

## Solicitud y autorización

Finanzas → Convenios de pago → Solicitar convenio. Secretaría selecciona estudiante y
cantidad de cuotas, prepara filas y selecciona obligaciones. Se muestran saldos reales
con descuentos, pagos REGISTRADO y donaciones RECIBIDA existentes. Cada cuota tiene
importe y fecha individuales. La cantidad puede ajustarse al preparar la solicitud y
Dirección también puede cambiarla antes de autorizar. Los formularios limitan a 100 filas
por operación para acotar recursos; no se generan cuotas iguales automáticamente.

El total de cuotas debe coincidir exactamente con el saldo de obligaciones seleccionadas.
No se incluyen cargos anulados, saldados, ajenos, de otro concepto ni ya vinculados a un
convenio no cancelado. Una cuota nueva no vence antes de la autorización (regla vigente
de CuotaConvenio). La solicitud no modifica obligaciones, deuda ni solvencia.

Dirección revisa condiciones solicitadas y ajusta obligaciones, cuotas y observaciones.
La comparación produce una revisión firmada del usuario, solicitud, condiciones, saldos,
pagos y donaciones. Confirmar vuelve a consultar y bloquear todos los datos relevantes.
Si cambia la selección, los importes o el estado financiero, no se autoriza silenciosamente:
se exige nueva comparación. Rechazar exige motivo y no crea un convenio.

UUID único protege reenvíos de solicitud; una pendiente por estudiante evita trámites
simultáneos duplicados. La aprobación se serializa por estudiante, comprueba coberturas
existentes y crea convenio, vínculos, cuotas y resolución en una sola transacción.
La fecha de convenio del modelo antiguo es DateField; SolicitudConvenio conserva también
la fecha/hora, identidad de Dirección y condiciones definitivas en el historial.
Una decisión idéntica repetida devuelve la resolución original. Decisiones contradictorias
se rechazan; no se modifican ni borran solicitudes resueltas.

## Cobro y conservación de recibos

Secretaría y Administración abren Registrar pago o abono desde el convenio. Se reutiliza
reservar_recibo y la secuencia institucional: todos los pagos conservan IBV-0000000000 y
la reserva firmada ligada al usuario/estudiante con vigencia de dos horas. No se genera
Pago ni recibo al autorizar o modificar un convenio.

El cobro exige convenio ACTIVO o INCUMPLIDO, cuotas propias no anuladas y saldo suficiente,
y obligaciones originales incluidas con saldo suficiente. Ambos desgloses deben sumar
exactamente lo mismo. Son válidos abonos parciales a cuotas, incluso cuando una obligación
original de matrícula no admite abonos por el mecanismo ordinario: es la modalidad de
cuotas expresamente autorizada. El cobro ordinario conserva su política de saldo neto
completo y rechaza obligaciones de convenios ACTIVO, CUMPLIDO o INCUMPLIDO.

Un solo Pago REGISTRADO contiene su snapshot de recibo, aplicaciones a obligaciones y
aplicaciones a cuotas. DetallePago reutiliza la actualización de estado de obligación.
Las cuotas pasan a PAGADA al alcanzar su importe y conservan PENDIENTE si queda saldo.
Al saldar todas las cuotas, el convenio pasa a CUMPLIDO. Un convenio formalmente
INCUMPLIDO sigue siéndolo con abonos parciales; solo el cumplimiento total elimina esa
causa conforme al SQL actual. No se declara INCUMPLIDO automáticamente por vencimiento:
la regla SQL ya detecta cuotas vencidas en un convenio ACTIVO.

Reenvíos idénticos recuperan el mismo recibo sin nuevos movimientos, incluso después del
cumplimiento. Reserva usada con otro convenio, referencia, método o aplicaciones se
rechaza. La numeración puede tener huecos por reservas abandonadas o rollback, igual que
el mecanismo ordinario. Pagos y recibos anteriores se conservan sin alteraciones.

Antes de cobrar, se compara el saldo de cuotas con el saldo de obligaciones originales.
Si divergen (por ejemplo, una donación posterior reduce la obligación pero no las cuotas),
se bloquea y se solicita revisión de Dirección. No se inventa una redistribución ni se
crea crédito. El tratamiento de esos ajustes con pagos previos queda pendiente de política.

## Saldos, solvencia y portal

La deuda original no se borra ni se duplica. El estado de cuenta y reportes siguen
calculando saldo sobre Obligacion menos descuentos, pagos y donaciones; NO suman CuotaConvenio
como una segunda cuenta por cobrar. Cada abono reduce ambos registros del mismo flujo,
pero Pago.monto_total se contabiliza una sola vez. El detalle del convenio muestra importe
original, abonado, saldo de cuotas, cantidades pagadas/pendientes/vencidas y estado guardado.
Las cuotas de versiones canceladas se etiquetan como saldo histórico.

Se reutiliza estudiante_esta_solvente sin modificar SQL: cobertura ACTIVO/CUMPLIDO,
cuotas vencidas de ACTIVO e INCUMPLIDO formal. Otras deudas pueden conservar insolvencia.
El portal filtra por request.estudiante obtenido de la sesión; un identificador de otro
estudiante produce 404. Las vistas del personal verifican roles en servidor. No se otorgan
permisos financieros de personal al alumno, maestro o pastor.

## Modificación/cancelación sin pagos de cuotas

Solo Dirección, motivo obligatorio y comparación firmada. Se permiten convenios ACTIVO o
INCUMPLIDO sin AplicacionPagoCuota. Cancelar registra usuario, motivo y fecha/hora y cambia
estado a CANCELADO sin modificar importes originales ni borrar cuotas/vínculos. La solvencia
vuelve a considerar las obligaciones con sus saldos originales actuales mediante el SQL.

Modificar crea una nueva versión autorizada con sus cuotas, conserva el anterior como
CANCELADO y registra RevisionConvenio con condiciones anteriores y nuevas. Nunca se
sobrescriben cuotas históricas ni se usan números duplicados en el mismo convenio.
La operación completa es transaccional y tiene UUID idempotente; cualquier fallo revierte
la cancelación del anterior y la creación de la versión nueva. No se implementó modificación
o cancelación con movimientos previos, aunque el usuario sea Dirección.

## Bloqueos y protecciones

Orden compartido: Usuario → Estudiante → Obligacion por PK → ConvenioPago → CuotaConvenio
por PK → solicitud/revisión según operación. Solicitudes no existentes se crean al final.
Los servicios de becas/cobros comparten Usuario/Estudiante antes de obligaciones, de modo
que las operaciones monetarias del mismo alumno se serializan sin invertir esos recursos.
No se añaden bloqueos tardíos de ciclos o cursos. Las validaciones se repiten bajo bloqueo;
los formularios y firmas no sustituyen esa validación.

ConvenioPago, sus cuotas/vínculos inline y AplicacionPagoCuota son solo consulta en Django
Admin, incluso para superusuario. SolicitudConvenio y RevisionConvenio no se registran allí.
No hay helper público de aplicación que omita autoridad y auditoría: los puntos de escritura
son los servicios transaccionales autorizados. SQL directo/QuerySet de código privilegiado
no constituyen vías institucionales ni una garantía de inmutabilidad física de la base.

## Esquema y validación

financiero/migrations/0002_convenios_institucionales.py crea exclusivamente solicitud_convenio
y revision_convenio, con UUID únicos, FK PROTECT, unicidad de pendiente y coherencia de
resolución/revisión. 0001 financiero y las migraciones académicas quedan intactas. No se
genera DDL sobre tablas managed=False. Se reutilizan estados y modelos existentes.
No se cambia el cálculo de becas, pagos ordinarios o reglas académicas; el único ajuste
del cobro ordinario bloquea también deudas cubiertas por convenios INCUMPLIDO.

Pruebas: SQLite :memory: con academico.test_settings y el runner existente, que crea las
tablas no administradas únicamente en ese motor efímero. Las migraciones crean las tablas
nuevas en esa base. No se ejecutaron migraciones persistentes ni se accedió a Neon.

Antes de publicar: PostgreSQL aislado para carreras de cobro/aprobación/revisión, secuencia
compartida, bloqueos FK, funciones SQL de estado/solvencia, esquema y permisos DML. Verificar
las unicidades previas de pares convenio/obligación, convenio/número y pago/cuota. Mantener
las guardias de settings_demo_pg, sin migrate automático ni inicializador de base vacía.
La comprobación de arranque exige las nuevas tablas; la provisión sobre una demo existente
requiere autorización, respaldo, SQL revisado y reconciliación de historial Django.

## Recorrido manual breve

1. Iniciar un ensayo nuevo aislado del checkout actualizado, con el lanzador SQLite en
   memoria anterior (al reiniciarlo se pierden datos). Matricular estudiante ficticio.
2. Secretaría: Finanzas → Convenios → nueva solicitud; elegir el alumno, dos cuotas,
   seis cargos de USD 20, cuota USD 30 con fecha de hoy y USD 90 con fecha futura. Justificar.
3. Dirección: revisar, ajustar si corresponde, comparar y autorizar. No debe aparecer recibo
   nuevo; deuda total sigue USD 120 y solvencia depende de las demás reglas existentes.
4. Secretaría/Administración: abonar USD 5 a cuota 1 y desglosar USD 5 en una obligación
   original. Un recibo, ambos saldos USD 115. Reenviar el POST: mismo recibo.
5. Completar cuota 1 (USD 25) y cuota 2 (USD 90) con desglose manual igual al abono, sin
   superar saldos. Convenio CUMPLIDO, saldo cero; verificar cuenta y reportes sin duplicación.
6. Estudiante: portal → cuenta → su convenio y recibos. No debe abrir convenios ajenos.
7. En otro convenio sin pagos, Dirección puede comparar y cancelar o crear una versión
   modificada. Con movimientos previos, esas revisiones deben quedar bloqueadas.
