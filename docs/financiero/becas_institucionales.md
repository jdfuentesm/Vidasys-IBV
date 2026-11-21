# F2 — Gestión institucional de becas

## Alcance y permisos

Secretaría crea solicitudes para una matrícula ACTIVA (el selector identifica estudiante,
ciclo y número). Selecciona 50 % o 100 %, matrícula/mensualidades/ambos, vencidas/no
vencidas/ambas y justificación. No hay aplicación automática al presentar la solicitud.
Secretaría, Dirección y Administración consultan bandeja, resoluciones e historial.
Solo una cuenta activa DIRECTORA aprueba o rechaza; Administración no recibe esta
facultad por ser superusuario. Maestro, Pastor Principal y Estudiante no acceden a
trámites; el portal del estudiante conserva únicamente su estado de cuenta autorizado.

Dirección puede ajustar porcentaje/conceptos/alcance y debe seleccionar expresamente
obligaciones de la matrícula. Compara importes y confirma con una revisión firmada.
Rechazar exige justificación. Una aprobación no se ejecuta con un formulario modificado
respecto a lo comparado. La fecha de servidor clasifica vencidas con vencimiento < hoy;
una obligación que vence hoy es no vencida. Pasar de día invalida una revisión anterior.
No se modifican solicitudes presentadas ni decisiones definitivas.

## Aplicación financiera

El porcentaje autorizado se calcula sobre monto_original, no sobre saldo. Se excluyen
obligaciones anuladas, saldadas, de conceptos no autorizados/inactivos, con descuentos
previos o cualquier aplicación de beca anterior, y las cubiertas por convenios ACTIVO
o CUMPLIDO. No se acumulan ni sustituyen descuentos. La selección no modifica convenios,
donaciones, padrinazgos o egresos.

Se compara el descuento con saldo disponible después de pagos REGISTRADO y donaciones
RECIBIDA. Si lo supera, se rechaza la operación COMPLETA sin créditos, devoluciones o
aplicaciones parciales. Los cargos ordinarios de USD 20 producen descuentos exactos
(USD 10 o USD 20). Si un cargo excepcional produce fracciones de centavo, se bloquea
esa aplicación y requiere definición institucional: no se inventa una política de redondeo.

Aprobar crea Beca y una AplicacionBeca por obligación y actualiza únicamente su descuento
y estado. No escribe monto_final, calculado por PostgreSQL. Se reutilizan
Obligacion.actualizar_estado(), importes() y estudiante_esta_solvente(); no se cambia
la función de solvencia. Otras deudas o incumplimientos pueden mantener insolvencia.
Una beca 100 % deja saldo cero en obligaciones elegibles sin crear Pago ni recibo.
Una beca 50 % sobre matrícula deja USD 10: si el concepto no admite abonos, solo puede
cobrarse el saldo neto completo, conservando el servicio de pagos original.

Beca.fecha_aprobacion es la fecha del servidor; fecha_inicio y fecha_fin delimitan
los vencimientos de las obligaciones seleccionadas. No hay aplicación periódica a
cargos nuevos ni retiro automático de descuentos al llegar a fecha_fin.

## Transacciones e historial

Orden común de escritura: Usuario → Estudiante → Matricula → Obligacion por PK →
SolicitudBeca. Cobros ya bloquea Usuario → Estudiante → Obligacion por PK; la fila
Estudiante serializa ambos flujos sin invertir sus bloqueos compartidos. No se
agregaron bloqueos tardíos sobre ciclos/cursos. La aprobación revalida matrícula,
conceptos, pagos, donaciones, convenios, descuentos y firmas bajo esos bloqueos.
La identidad/ciclo/número/fecha de matrícula se conserva al solicitar y se compara
antes de aprobar para evitar aplicar la beca sobre una matrícula reasignada.

Toda la selección, beca, aplicaciones, estados y resolución se confirman en la misma
transacción. Un fallo al guardar cualquiera revierte todo. UUID único evita reenvíos
con distintos datos; índice parcial limita una pendiente por matrícula. Una decisión
repetida idéntica devuelve el resultado original sin reaplicar; cambios sobre una
resolución decidida se rechazan. Al solicitar nuevamente tras una decisión, las
obligaciones ya descontadas siguen excluidas.

SolicitudBeca conserva solicitante/fechas/condiciones pedidas, directora/fecha/condiciones
resueltas y anteriores/aplicados por obligación: original, descuento previo, pagos,
donaciones, saldo previo, descuento, saldo resultante y estado. También conserva la
solvencia al resolver; el estado de cuenta calcula la actual. No se modifican pagos,
donaciones ni snapshots de recibos previos. Las cuentas muestran aplicaciones de beca
y, para usuarios financieros, enlaces al historial de solicitudes.

Django Admin: Beca y sus aplicaciones inline no admiten alta/cambio/borrado, incluso
con superusuario; monto_descuento de Obligacion es solo lectura. SolicitudBeca no se
registra en Admin. Los accesos privilegiados de SQL o QuerySet interno no constituyen
una vía institucional ni una garantía de inmutabilidad física frente al dueño de BD.

## Migración segura preparada

financiero/migrations/0001_initial.py registra los modelos managed=False mediante
SeparateDatabaseAndState(database_operations=[]). Solo CreateModel SolicitudBeca
produce DDL: tabla solicitud_beca, FK, índices y restricciones. No cambia tablas
financieras/académicas existentes. Depende del estado académico 0002 y del usuario.
No reemplaza la provisión externa de las tablas anteriores.

Django crea solicitud_beca al preparar SQLite :memory: de los tests; el runner existente
crea después las tablas no administradas solo allí. No usar migrate aislado para
suponer que se crearon también Beca, AplicacionBeca u Obligacion.

No se ha aplicado la migración sobre bases persistentes ni se ha conectado a Neon.
Antes de publicar: generar/revisar SQL PostgreSQL en un destino aislado, comprobar
FK e índices nuevos, restaurar allí un respaldo sintético, verificar permisos DML de
la cuenta web sobre solicitud_beca y secuencia y verificar esquema existente.
Mantener las guardias de settings_demo_pg y no añadir migrate automático al arranque.
La verificación de demo exige todas las tablas y no arrancará si falta solicitud_beca.
Si el esquema fue provisionado externamente, reconciliar historial Django de forma
separada; no usar --fake ni el inicializador de base vacía como atajo.

Quedan para PostgreSQL aislado: concurrencia real entre cobro/aprobación y doble
aprobación, bloqueos FK ante nuevos pagos/donaciones/convenios, tiempos DDL, regex de
restricciones, funciones de estado/solvencia y permisos del rol web. SQLite no demuestra
esos bloqueos ni la instalación real de funciones SQL. No ejecutar estos ensayos en Neon.

## Prueba manual en un ensayo nuevo y aislado

1. Usar el lanzador SQLite en memoria de las pruebas funcionales anteriores sobre este
   checkout actualizado. No reiniciar un ensayo con datos que se deseen conservar:
   al detenerlo se pierden. No usar settings de producción ni migrate sobre una BD real.
2. Secretaría: Finanzas → calendario y matrícula ficticia si faltan; entrar a Becas →
   Solicitar. Pedir 50 %, ambos conceptos, ambos alcances y justificación.
3. Administración: comprobar consulta y ausencia de acciones de autorización.
4. Dirección: abrir pendiente, seleccionar obligaciones explícitas, comparar y confirmar.
   En un ciclo ordinario de seis cargos de USD 20, descuento USD 10 por cargo.
5. Secretaría: cuenta del estudiante → comprobar descuentos, aplicaciones e historial.
   En matrícula que no admite abonos, intentar USD 5 (debe bloquear) y pagar USD 10
   (debe generar solo el recibo de ese pago real).
6. En otro estudiante/matrícula sin pagos, aprobar 100 % sobre las seis obligaciones:
   saldo cero, sin recibos nuevos y solvencia según las demás reglas vigentes.
7. En otra solicitud, rechazar con motivo; verificar ausencia de descuentos.
8. Pago previo USD 15 sobre mensualidad USD 20: pedir 50 % → descuento USD 10 excede
   saldo USD 5; debe bloquear TODA la aprobación y conservar recibo y saldo anteriores.
9. Reenviar una aprobación idéntica: misma resolución, sin becas/aplicaciones adicionales.
   Cambiar condiciones tras la comparación: exigir nueva revisión. Probar URLs con roles
   no autorizados y Admin; no deben permitir aplicar becas.

Comandos de regresión (variables DB ficticias y SECRET_KEY de pruebas):
python -B manage.py check --settings=academico.test_settings
python -B manage.py test --settings=academico.test_settings --noinput
python -B manage.py makemigrations --check --dry-run --settings=academico.test_settings
