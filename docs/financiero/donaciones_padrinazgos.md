# F6 — Donaciones y padrinazgos

## Alcance y decisiones aprobadas

Base: `6e83176206921d2d869bea8d01a0b998faa890b7`, con 490 pruebas previas.
Se entregan gestión privada de donantes, donaciones generales/dirigidas, solicitudes y
coberturas autorizadas de padrinazgo, recepciones parciales, resoluciones posteriores,
anulaciones, consultas estudiantiles y reportes. Sin F7, rediseño F8, push ni despliegue.

Decisiones expresamente confirmadas durante F6:

1. Bloquear nuevas coberturas y donaciones dirigidas sobre obligaciones de convenios ACTIVO,
   INCUMPLIDO o CUMPLIDO hasta definir su conciliación con cuotas. No cambiar esos convenios.
2. Convertir a beca únicamente cuando todo el pendiente seleccionado coincida exactamente
   con una beca F2 del 50 % o 100 % sobre el original, sin acumular descuentos ni exceder
   saldos. Si falla, se revierte la operación completa y permanece la cobertura.
3. Guardar monto fijo total y asignaciones exactas en tablas nuevas. El Padrinazgo histórico
   conserva un porcentaje equivalente informativo sobre el saldo seleccionado, redondeado
   a dos decimales; no se convierte un total en monto mensual. Los importes exactos nuevos
   son la autoridad de cálculo, no ese porcentaje informativo.
4. Matrícula con saldo financiero 20 y cobertura pendiente 10: el estudiante puede pagar
   íntegramente sus 10. No se aceptan abonos menores ni se cobran los 10 reservados al padrino.
   El saldo financiero restante sigue siendo real; la cobertura no se registra como pago.

Porcentaje de padrinazgo se calcula sobre el saldo libre de las obligaciones seleccionadas,
una vez descontados pagos, donaciones, becas y reservas existentes. Los importes deben ser
representables exactamente en centavos: si un porcentaje requiere fracciones, se solicita
ajustar la propuesta o usar importes fijos; no se inventa un reparto o redondeo financiero.

## Esquema preparado y reutilización

`0005_donaciones_padrinazgos` crea exclusivamente siete tablas administradas:

| Tabla | Finalidad |
| --- | --- |
| `historial_donante` | UUID, operador, fecha y versiones privadas de altas/actualizaciones. |
| `solicitud_padrinazgo` | Solicitante, padrino/matrícula, propuesta, instantánea, resolución y vínculo único al Padrinazgo autorizado. |
| `cobertura_padrinazgo` | Importe exacto por obligación y solicitud; estado activo, unicidad de pareja e importe positivo. |
| `recepcion_donacion` | UUID, un Ingreso, donante, destino, compromiso opcional, documento y foto inmutable del comprobante. |
| `linea_donacion` | Una Donacion histórica por aplicación, vinculada una sola vez a su recepción y cobertura opcional. |
| `revision_padrinazgo` | Prórroga, sustitución, cancelación o conversión, con motivo, versiones y notificación. |
| `anulacion_donacion` | Solicitud/resolución auditable; una pendiente y una aprobada por recepción. |

Se reutilizan Donante, Donacion, Padrinazgo, Ingreso, Obligacion y MovimientoCaja. No hay DDL
sobre tablas `managed=False`, MovimientoCaja ni sus restricciones. Las migraciones 0001–0004
permanecen idénticas. Tampoco se modifican funciones o vistas SQL existentes.

Cada recepción genera exactamente un Ingreso y un MovimientoCaja de origen ingreso,
utilizando la extensión aprobada en F5. No hay Pago ni DetallePago ficticios. La numeración
institucional es `DON-<id_ingreso de diez dígitos>`; Caja muestra ese mismo comprobante.
El rubro fijo DONACIONES se obtiene/crea internamente para clasificar ese Ingreso, sin abrir
la configuración arbitraria de categorías a operadores. Una categoría desactivada requiere
que Administración la active antes de registrar más dinero. F5 sigue bloqueando donaciones
por su formulario de ingresos administrativos.

Una recepción dirigida a varias obligaciones crea varias Donacion RECIBIDA, cuyos importes
suman exactamente el único ingreso. No se crea una donación «cabecera» que duplique ese total.
En recepciones de varias líneas, el vínculo al ingreso está en RecepcionDonacion/LineaDonacion;
el campo histórico nullable Donacion.ingreso se utiliza solo cuando hay una línea. La función
SQL existente reconoce las aplicaciones reales porque siguen en Donacion.id_obligacion.

## Compromiso, saldo y solvencia

Solicitar no protege ni mueve dinero. Dirección compara, confirma y autoriza importes exactos
por obligación. Una cobertura autorizada, activa y ya iniciada protege su pendiente aunque
la fecha límite haya vencido. El vencimiento muestra alerta en el inicio de Dirección y
el panel de F6; nunca elimina automáticamente la protección del estudiante.

Se distinguen en cuenta y portal:

- Saldo financiero real: original menos descuentos, pagos registrados y donaciones recibidas.
- Cobertura pendiente: importe autorizado menos recepciones vigentes de ese compromiso,
  limitado al saldo real; no puede duplicarse con otras coberturas.
- Saldo a cargo del estudiante: saldo financiero menos cobertura efectiva.
- Dinero recibido/aplicado: únicamente Donacion RECIBIDA, nunca el compromiso original.

La función SQL original sigue intacta. `consultas.solvente` la consulta primero y agrega
la excepción F6 en Python cuando corresponde. La excepción conserva las reglas anteriores:
no ignora otras obligaciones vencidas sin cobertura, convenios formalmente incumplidos ni
cuotas vencidas pendientes. El inicio de cobertura se respeta; su fecha límite no cancela.
El portal y los reportes institucionales que usan este servicio consideran la nueva regla.
**Los consumidores directos de la función/vistas SQL todavía ven la política anterior**:
no deben presentarse como una evaluación completa de F6 sin armonización autorizada.
Esta diferencia debe comprobarse/documentarse en PostgreSQL aislado antes de desplegar.

Caso obligatorio probado: último ciclo enero–junio 2027, compromiso 100 % por 120 hasta
julio. En junio hay deuda financiera 120, recibido 0, cobertura 120 y cargo estudiantil 0;
solvencia de la aplicación verdadera. En julio, después del fin del ciclo, se reciben los
120, se aplica una vez, se emite un comprobante y se registra una sola entrada de caja.
La consulta académica del portal se prueba también con cobertura y sin dinero recibido.

Becas parciales previas pueden complementarse sobre el saldo libre. Las becas o convenios
ordinarios posteriores no consumen silenciosamente un saldo reservado: requieren resolver
la cobertura. Los pagos del estudiante se limitan a su parte. La matrícula conserva la
exigencia de pago íntegro de esa parte, según la decisión aprobada arriba.

## Recepciones y resoluciones

General: funcionamiento institucional, sin obligación. Dirigida: matrícula y aplicaciones
explícitas. Padrinazgo: compromiso autorizado activo, matrícula y padrino actual coherentes,
con importes no superiores a su pendiente. Se admiten recepciones parciales y posteriores
al fin del ciclo; no se admite fecha efectiva futura. No hay reparto automático, excedentes,
créditos, devoluciones ni cruces con convenios no definidos.

La recepción requiere caja propia abierta y un donante activo. Dinero, aplicaciones,
documento y movimiento se guardan en una sola transacción. UUID y datos canónicos reconocen
reenvíos y rechazan reutilización con otros datos. Se bloquea un aporte del mismo operador
con idénticos datos y nueva clave para evitar duplicación accidental. Los compromisos
pueden existir con donante después desactivado: esa desactivación no castiga al estudiante.

Dirección puede prorrogar, sustituir padrino, cancelar cobertura pendiente o convertirla.
Cada resolución se compara y confirma con firma ligada al actor, condiciones y versiones.
Prorrogar no borra recepciones; sustituir conserva sus donantes originales. Cancelar o
convertir exige un mensaje al estudiante: aparece dentro de su portal, sin enviar correo
externo ni mostrar datos privados. Las resoluciones originales no se reescriben.

La conversión compatible crea una solicitud de beca cuyo iniciador real es Dirección y
utiliza la comparación y el servicio de aprobación F2. La solicitud ordinaria de F2 sigue
siendo exclusiva de Secretaría. No se atribuyen solicitudes a una persona que no las hizo.
La liberación de cobertura y la beca son atómicas: cualquier incompatibilidad, descuento
existente, solicitud de beca pendiente o error devuelve todo al estado anterior.

## Anulaciones y cierres

El operador solicita la anulación de su recepción; solo Dirección decide. Rechazar exige
motivo y no cambia dinero. Aprobar exige caja abierta, originales consistentes, solicitante
con permisos vigentes y comparación firmada. Se anula el Ingreso y sus Donacion, sin borrar
líneas ni documentos, y se recalculan obligaciones y cobertura pendiente.

Anular no devuelve efectivo: la entrada física permanece en el arqueo y queda retenida,
fuera del disponible para egresos. Se bloquea si financió desembolsos posteriores. Después
de cancelación/conversión de cobertura o sustitución de padrino se requiere revisión del
tratamiento y no se anula automáticamente. No se modifican cajas cerradas ni sus fotos.

La foto inmutable del comprobante conserva nombre/anónimo, destino, operador y descripciones
originales aunque se actualice el donante. Los documentos reutilizan almacenamiento privado,
validación PDF/PNG/JPEG, límites, hash y descarga autenticada de F5. No hay documentos en Git.

## Permisos

| Operación | Secretaría | Administración | Dirección | Estudiante | Maestro/Pastor |
| --- | --- | --- | --- | --- | --- |
| Registrar/actualizar donante | Sí | Sí | Consulta | No | No |
| Consultar directorio e historial interno | Sí | Sí | Sí | No | No |
| Preparar padrinazgo | Sí | Sí | Consulta/resuelve | No | No |
| Autorizar/rechazar/revisar cobertura | No | No | Sí | No | No |
| Recibir dinero y operar su caja | Sí | Sí | Consulta | No | No |
| Solicitar anulación propia | Sí | Sí | Resuelve | No | No |
| Reportes/CSV consolidados | No | Sí | Sí | No | No |
| Consultar cobertura y saldo propios | Institucional | Institucional | Institucional | Solo propios, sin padrino | No |

La identidad procede de sesión; los servicios vuelven a leer permisos activos. Admin deja
Donante, Padrinazgo y Donacion solo consulta, incluidos sus inlines; los modelos nuevos no
se registran. Superusuario técnico no puede autorizar por las rutas institucionales.
La privacidad del estudiante se implementa con datos explícitos de saldo/cobertura y
notificación: no se envían objetos de donante ni se ofrece descarga de sus documentos.

## Transacciones y validación

Orden de bloqueos compartido: Usuario → Caja si hay dinero → Estudiante → Matricula →
Obligacion por PK → Donante por PK → Padrinazgo → solicitud/coberturas → Ingreso/anulación.
Las ediciones de donante no toman Caja/Estudiante después de Donante. La sustitución bloquea
ambos donantes ordenadamente. Se conservan bloqueos de F2/F3/F4/F5 y no se eliminan para
resolver concurrencia. Guardas e idempotencia están en servicios, no solo en plantillas.

**560 pruebas aprobadas: 490 anteriores y 70 nuevas F6.** Se prueban permisos, anonimato,
historial, general/dirigida, importes exactos, parciales/totales, padrinazgo sin dinero,
2027 y julio posterior al ciclo, vencido sin bloqueo, prórroga/sustitución/cancelación,
conversión compatible e incompatible, becas/convenios, pagos del estudiante, duplicados,
caja, anulaciones, rollback, privacidad, CSV, modelos/DDL y formularios HTTP.

Chromium/Playwright: 75 pantallas, roles Secretaría/Administración/Dirección/Estudiante,
anchos 390, 768 y 1366, HTTP 200 sin desbordamiento; no se expone el padrino en el portal.
Se completa desde navegador móvil: donante → solicitud 100 % con cálculo dinámico →
autorización → aporte parcial 10 → anulación sin devolución → prórroga → cierre cuadrado
20 (fondo 10 más efectivo original recibido 10). Los controles de fecha y formularios
con desglose tienen pruebas de regresión para los problemas encontrados en ese recorrido.
Las pruebas usan exclusivamente SQLite efímero; no acceden a Neon.

## Recorrido manual

1. Iniciar un ensayo nuevo del checkout actualizado con SQLite en memoria, usando el
   lanzador anterior, en un único proceso sin autoreload ni hilos. El runner crea 0005
   en memoria; no ejecutar migrate con la configuración normal ni sobre Neon.
2. Secretaría/Admin: matricular al estudiante ficticio si el ensayo todavía no tiene matrícula.
   Finanzas → Donaciones y padrinazgos → registrar donante; abrir caja.
3. Buscar estudiante por nombre → preparar padrinazgo. Elegir donante, inicio y límite
   (puede superar fin del ciclo). Para porcentaje, marcar obligaciones y escribir 100;
   para fijo, escribir importes. Revisar resumen dinámico y enviar.
4. Dirección: abrir solicitud, revisar cada obligación, comparar y confirmar. Comprobar
   que no se generó Ingreso y que el estudiante ve cobertura y acceso académico, sin padrino.
5. Secretaría/Admin: registrar aporte del estudiante, seleccionar el compromiso (completa
   padrino/modalidad automáticamente), indicar dinero recibido y desglose exacto. Emitir DON.
6. Verificar que deuda financiera y pendiente protegido bajan, y que Caja recibe solo el
   dinero real. Reenviar el mismo formulario no genera otro recibo.
7. Dirección: resolver prórroga o sustitución, conservar historia. Probar cancelación con
   mensaje al estudiante o conversión compatible con F2; una incompatible no retira cobertura.
8. Solicitar/aprobar anulación mientras caja siga abierta; se restablece deuda/cobertura,
   pero el efectivo original sigue en Caja, retenido. Cerrar contando efectivo real y
   comprobar que una anulación posterior al cierre se bloquea.
9. Dirección/Admin: consultar donantes, compromisos pendientes/vencidos, recibidos, CSV e
   impresión. Nunca sumar compromisos a ingresos. Secretaría ve historial interno, no CSV
   consolidado. Verificar que roles ajenos no abran formularios, recibos ni documentos.

## Pendientes antes de PostgreSQL/despliegue

No se ejecutaron migraciones persistentes ni se modificó infraestructura. Falta ensayar en
PostgreSQL aislado: restricciones reales de Donante/Padrinazgo/Donacion/Ingreso, incluyendo
RECIBIDA/ANULADA y el vínculo histórico nullable a Ingreso; FK nuevas, índices, secuencias,
triggers de saldos, precisión, rollback y concurrencia real (pago/cobertura/recepción/revisión/
anulación/cierre). SQLite no certifica bloqueos de fila ni PL/pgSQL. Ante incompatibilidad,
no alterar tablas/funciones/restricciones históricas sin autorización expresa.

Verificar respaldo/restauración, migraciones 0001–0004 aplicadas y SQL de 0005: solo siete
tablas nuevas, sin DDL sobre las anteriores. No desactivar guardias de demo ni usar el
inicializador de base vacía sobre una existente. No hay cambios a main, Neon ni despliegue.

La función/vistas SQL antiguas no incluyen compromisos F6; la aplicación añade esa regla.
Se requiere validar consumidores directos y, si se quiere unificar la política en SQL,
proponer y autorizar expresamente ese cambio antes de incorporarlo. Los cruces con convenios,
excedentes/redistribuciones y regularizaciones después de cierres siguen bloqueados.
Datos históricos sin metadatos F6 no se importan o reinterpretan automáticamente.

El backlog UI/UX versionado para F8 está en `docs/backlog/F8_ui_ux.md`. F7/F8 no se implementan.

## Inventario de archivos de esta entrega

- `docs/backlog/F8_ui_ux.md`
- `docs/financiero/donaciones_padrinazgos.md`
- `financiero/aportes.py`
- `financiero/aportes_forms.py`
- `financiero/aportes_models.py`
- `financiero/aportes_views.py`
- `financiero/migrations/0005_donaciones_padrinazgos.py`
- `financiero/test_aportes.py`
- `static/js/aportes.js`
- `templates/financiero/aportes/anulacion.html`
- `templates/financiero/aportes/base.html`
- `templates/financiero/aportes/buscar.html`
- `templates/financiero/aportes/donante.html`
- `templates/financiero/aportes/form.html`
- `templates/financiero/aportes/panel.html`
- `templates/financiero/aportes/recibo.html`
- `templates/financiero/aportes/reporte.html`
- `templates/financiero/aportes/solicitud.html`
- `core/portal.py`
- `core/views.py`
- `docs/manuales/modulo_financiero.md`
- `financiero/admin.py`
- `financiero/becas.py`
- `financiero/caja.py`
- `financiero/consultas.py`
- `financiero/convenios.py`
- `financiero/forms.py`
- `financiero/models.py`
- `financiero/operaciones_views.py`
- `financiero/servicios.py`
- `financiero/urls.py`
- `static/css/financiero.css`
- `templates/core/dashboard.html`
- `templates/core/portal/inicio.html`
- `templates/financiero/caja/detalle.html`
- `templates/financiero/caja/totales.html`
- `templates/financiero/cuenta.html`
- `templates/financiero/panel.html`
