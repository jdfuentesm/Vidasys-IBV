# F7 — Centro de reportes financieros consolidados

Implementación sobre `7f9da2005b8cb485f35252d992920153109523da`, rama
`semana-9-rutas-calificaciones`. Solo consulta; sin tablas, migraciones ni ajustes de datos.
No representa contabilidad de partida doble ni balance general. No habilita F8 ni despliegue.

## Uso y alcance

Finanzas → **Centro de reportes financieros**, o Reportes institucionales → el mismo acceso.
Ruta inicial: `/reportes/finanzas/`. Hay ocho vistas:
`panel`, `resultados`, `cuentas`, `solvencia`, `beneficios`, `convenios`, `cajas`, `auditoria`.
Sus rutas son `/reportes/finanzas/<tipo>/`.

Dirección puede abrir cada indicador y consultar su detalle; no hay acciones financieras
ni botones de autorización nuevos. Los enlaces al expediente original conservan sus permisos
operativos. Los reportes y sus exportaciones no conceden facultades de resolución.
Los reportes anteriores siguen disponibles con sus permisos previos; F7 es el centro
consolidado compatible con F1–F6, no una sustitución silenciosa de los reportes antiguos.

Se distingue explícitamente:

- **Operaciones de un período:** fecha efectiva local inclusiva del cobro/desembolso;
  su estado es el vigente al generar. Una anulación posterior afecta hoy el resultado
  de aquel período; no se pretende reconstruir el estado que tenía en una fecha pasada.
- **Saldos y solvencia actuales:** al generar, sin reconstrucción histórica. Cuentas y
  solvencia rechazan filtros de corte temporal que no pueden cumplir.
- Beneficios: fechas de aprobación de beca/autorización de padrinazgo; recibido y pendiente
  actuales de esos compromisos. Convenios: fecha del convenio y saldos actuales.
- Cajas: fecha de apertura; foto histórica para cerradas y situación actual para abiertas.
- Auditoría: fecha de cada solicitud, decisión o revisión. Las anulaciones se filtran por
  fecha de la anulación, aunque el cobro sea anterior. Una situación física retenida sin
  fecha de regularización se presenta como situación, sin atribuirle una fecha inventada.

Panel, resultados y auditoría comienzan en el mes corriente. Fechas vacías explícitas
permiten consultar todo el registro. Los indicadores de situación actual no heredan el
período de flujos al abrir su detalle. Restablecer vuelve a los valores iniciales.

## Matriz de permisos

| Rol activo | Centro F7, HTML, CSV, impresión y URL directa | Operaciones financieras |
| --- | --- | --- |
| DIRECTORA | Todas las consultas F7 | Permisos existentes, sin cambios |
| ADMINISTRADOR | Todas las consultas F7 | Permisos existentes; no autoriza por F7 |
| SECRETARIA | Sin acceso F7 | Conserva operación y reportes previos |
| MAESTRO | Sin acceso F7 | Sin ampliación |
| ESTUDIANTE | Sin acceso F7 | Conserva su portal |
| PASTOR_PRINCIPAL | Sin acceso F7 | Sin ampliación |

Los permisos se validan antes de cargar opciones o consultar fuentes. Ser superusuario
con otro rol no sustituye esta autorización. Anónimos/inactivos no acceden. Los POST
son rechazados. Respuestas privadas sin caché. No se exportan contactos, documentos,
direcciones, notas privadas ni comprobantes binarios de donantes. Auditoría sí muestra
responsables y motivos institucionales a los dos roles autorizados.

## Fuentes únicas y fórmulas

Todas las sumas usan `Decimal`, sin conversión monetaria a `float`.

| Indicador del panel | Fórmula y fuente |
| --- | --- |
| Ingresos académicos recibidos | Suma de aplicaciones de `Pago REGISTRADO` conciliadas con su total. Se distribuyen por concepto: matrícula, mensualidad u otro; un pago con `AplicacionPagoCuota` se clasifica exclusivamente como convenio. |
| Ingresos administrativos | `Ingreso REGISTRADO` con `RegistroIngreso`, una vez por ingreso. |
| Donaciones recibidas | `Ingreso REGISTRADO` con `RecepcionDonacion`, o vínculo histórico verificable con Donacion; una vez por ingreso. Donaciones históricas independientes RECIBIDA, sin ingreso ni línea F6, solo con fecha efectiva verificable. |
| Egresos desembolsados | `Egreso REGISTRADO` vinculado a `DesembolsoEgreso`; agrupación por categoría. Autorizar una solicitud no constituye desembolso. |
| Resultado financiero verificado | Ingresos efectivos vigentes verificados menos egresos efectivos vigentes verificados. |
| Becas otorgadas en el período | Suma de `AplicacionBeca APLICADA.monto_aplicado` de becas cuya aprobación corresponde al período. Es exoneración, no egreso. |
| Cuentas pendientes | Suma del saldo financiero de obligaciones no ANULADA. |
| Saldo a cargo de estudiantes | Saldo financiero menos protección efectiva pendiente; incluye obligaciones no vencidas y convenios. No equivale íntegramente a deuda vencida. |
| Compromisos activos de padrinos pendientes | Suma de cobertura activa autorizada menos aportes RECIBIDA aplicados, piso cero; puede incluir compromiso cuyo inicio todavía no llega. Informativo, no ingreso. |
| Cobertura pendiente efectiva | Compromiso pendiente con fecha de inicio alcanzada, limitado por saldo de cada obligación. No se retira automáticamente por vencer su fecha límite; se conserva F6. |
| Convenios vigentes/incumplidos | Conteos distintos de `ConvenioPago` ACTIVO / INCUMPLIDO almacenados. Las cuotas vencidas se identifican también en el detalle, sin cambiar automáticamente el estado del convenio. |
| Egresos autorizados pendientes | Conteo y suma de `SolicitudEgreso APROBADA` sin `DesembolsoEgreso`; enlace al filtro específico de auditoría, sin incluir los ya desembolsados. |
| Solicitudes pendientes | Conteo de las siete bandejas financieras pendientes: beca, convenio, egreso, padrinazgo, anulación de pago, anulación de operación y anulación de donación. No incluye solicitudes académicas. |
| Cajas abiertas/cerradas | Conteos de Caja por estado; detalle por operador y apertura. |

Un mismo pago puede tener varias filas por categoría, pero sus aplicaciones se particionan;
no se vuelve a sumar el encabezado. `AplicacionPagoCuota`, `DetallePago`, `LineaDonacion`
y `MovimientoCaja` explican o aplican el dinero, **no son ingresos adicionales**.
Una recepción F6 con varias líneas sigue siendo un único ingreso. Las becas y compromisos
no se incorporan al resultado. Fondos iniciales tampoco son ingresos.

Con filtro de ciclo/estudiante, resultados solo atribuye aplicaciones verificables de ese
ciclo/estudiante. No distribuye arbitrariamente ingresos generales o gastos institucionales.
Categorías de cargo académico, ingreso y egreso son filtros separados por su origen.
Anulados aparecen identificados, fuera de los totales vigentes. Sus importes son informativos.

### Datos históricos sin conciliación suficiente

Ingreso sin procedencia verificable, egreso sin evidencia de desembolso, conflicto entre
procedencias o Pago cuyo total no concilia con aplicaciones se muestran como
**pendientes de conciliación**, excluidos del resultado verificado y con aviso visible.
Una donación sin fecha efectiva verificable se advierte y no se atribuye al período.
No se deduce procedencia por texto ni se inventan fechas, recibos o distribuciones.
Esto evita duplicar cobros históricos que podrían estar representados en dos tablas.
Si hay advertencias, el resultado verificado puede no ser el resultado íntegro de toda la
historia: es necesaria una conciliación institucional separada. F7 no repara esos registros.

### Cuentas por cobrar y solvencia

Para cada obligación no anulada:

```
neto = original - descuento almacenado
saldo = max(neto - pagos REGISTRADO - donaciones RECIBIDA, 0)
protección = min(saldo, compromiso activo autorizado pendiente con inicio alcanzado)
en convenio = saldo - protección, si hay convenio ACTIVO/CUMPLIDO/INCUMPLIDO; si no, 0
directo = saldo - protección - en convenio
a cargo del estudiante = en convenio + directo
```

Control excluyente: **protección + en convenio + directo = saldo financiero**.
No sumar nuevamente «a cargo», cuotas o compromisos informativos. Se muestran original,
descuento, pagos, donaciones, vencimiento y saldo; un saldo PAGADA incorrectamente etiquetado
no desaparece solo por la etiqueta. Sobreaplicaciones se advierten sin generar crédito.
El vencido exigible por obligación excluye convenios vigentes ACTIVO/CUMPLIDO; sus cuotas
vencidas se consultan en Convenios, sin sumar cuotas y originales como deudas distintas.

`financiero.lectura.EstadoFinanciero` centraliza lectura por lotes, sin guardar estados.
`consultas.solvente`, `aportes.detalle_solvencia`, portal y F7 usan el mismo servicio.
Preserva la autoridad SQL base original y aplica en el servicio la excepción F6 con las
mismas condiciones: protección, exigible no cubierto cero, sin convenio INCUMPLIDO ni
cuotas vencidas de ACTIVO. No sustituye políticas de acceso o reglas académicas.
F7 no usa por separado la función SQL antigua para decidir solvencia sin esa excepción.

Clasificación excluyente por estudiante: insolvente primero; si solvente, combinado cuando
coexisten al menos dos de beca aplicada, protección de padrino o convenio que ampara saldo;
en los demás casos padrinazgo, convenio o solvente. Becas y padrinazgos no duplican personas.
Filtrar ciclo selecciona sus estudiantes; la solvencia considera **todo su expediente**,
no solo las obligaciones del ciclo. No tener deuda no equivale a tener matrícula activa.

### Beneficios, convenios, caja y auditoría

Beneficios separa exonerado de beca y comprometido histórico, recibido aplicado, compromiso
activo pendiente y protección de padrinazgo. Vencidos conservan protección según F6 y
muestran revisiones de Dirección. Los beneficiarios combinados se cuentan una vez.

Convenios compara saldo de cuotas (`monto_cuota - AplicacionPagoCuota vigente`, piso cero,
anuladas con saldo cero) con saldo de obligaciones originales enlazadas. Se muestra la
diferencia y se advierte sin ajustar importes. Un cancelado mantiene historia, no deuda
adicional. Si un convenio contiene varios ciclos y se filtra uno, se muestra el convenio
íntegro y se explica que no hay distribución implícita de cuotas.

Caja abierta usa movimientos originales físicos, incluso si se anula su origen:
`esperado = fondo inicial + entradas efectivo - salidas efectivo`.
Una anulación no devuelve ni recupera dinero. Efectivo de entradas anuladas queda retenido
por separado. Transferencias recibidas y realizadas se informan aparte, sin llamarlas saldo
bancario. Caja cerrada usa **exclusivamente su JSON de cierre** para magnitudes de foto;
no consulta sus movimientos vivos para reconstruirla. Campos históricos ausentes muestran
«No consta», con aviso, nunca un cero supuesto. Contado/diferencia son los guardados al cerrar.

Auditoría distingue eventos de solicitudes, decisiones, revisiones y anulaciones de la
situación física retenida. Un pago multiconcepto anulado tiene una sola referencia y su
importe íntegro. Filtrar operador en eventos selecciona el responsable del evento, no el
cajero original. Los importes repetidos de eventos relacionados **no se totalizan como dinero**.

## Filtros, presentación y lectura consistente

Filtros pertinentes: fechas, ciclo, estudiante, categoría, método, operador, estado y origen.
No se piden IDs manuales. Valores inválidos dan HTTP 400 sin cifras; fallo de fuente da
HTTP 503 sin totales parciales ni detalles internos del error. Consultas vacías son explícitas.
CSV aplica la misma validación/permisos/alcance; neutraliza fórmulas también en etiquetas,
filtros y textos de usuarios. Incluye alcance, generación, advertencias y totales. HTML
pagina 25 registros; CSV e impresión incluyen todas las coincidencias. Impresión institucional
oculta menús, filtros y acciones, conserva criterios y permite Guardar PDF del navegador.

Gráficos sin dependencias nuevas: ingresos y egresos mensuales (hasta últimos 24 meses de
la selección; totales del período completo) y distribución de ingresos por origen exclusivo.
Tienen nombres, importes y patrón para egresos; no dependen solo del color. Detalles usan
listas de etiquetas adaptables en vez de tablas anchas. Formato monetario USD con dos decimales.

La lectura agrupada usa `select_related`, prefetch y sumas por obligación/cuota/cobertura;
la función base de solvencia se invoca por lotes de hasta 400 estudiantes, sin una consulta
de red por estudiante. Los totales requieren materializar la selección completa; paginar
no elimina ese costo. Antes de grandes volúmenes, medir planes, memoria y tiempo real.
No hay escrituras de reporte ni creación de archivos financieros en BD.
En PostgreSQL, F7 abre una transacción `REPEATABLE READ, READ ONLY` al ser dueño de la
transacción; bajo una transacción externa conserva el aislamiento del llamador. La
configuración actual no activa ATOMIC_REQUESTS. Esta garantía debe ensayarse en PostgreSQL
antes de desplegar; SQLite no demuestra aislamiento ni concurrencia PostgreSQL.

## Validación realizada

- **605 pruebas aprobadas**: 560 anteriores + 45 nuevas; exclusivamente SQLite en memoria.
- Django `check`: sin problemas; `makemigrations --check --dry-run`: sin cambios detectados.
- Migraciones financieras 0001–0005, modelos, SQL y configuración intactos.
- `git diff --check`: sin errores.
- Pruebas: permisos de los seis roles, URL/CSV/impresión, inactivo/superusuario de otro rol,
  POST rechazado, GET sin INSERT/UPDATE/DELETE/DDL; totales exactos y centavos, fuentes únicas,
  matrícula/mensualidad/convenios, donaciones multilínea, becas, padrinazgos, combinados,
  conservación de fotos, retención, transferencias, filtros, CSV protegido, fechas de auditoría,
  privacidad, paginación, indisponibilidad de fuente y crecimiento de consultas por lotes.
- Chromium, datos ficticios en SQLite en memoria: **48 pantallas** (8 vistas × 2 roles ×
  390/768/1366 px), HTTP 200 y sin desbordamiento horizontal; filtros móviles, descarga CSV,
  impresión PDF y rechazo de exportación por Secretaría. Evidencias en
  [F7](../evidencias/F7/README.md). No se ensayó con datos personales reales ni Neon.

Comandos desde la raíz, con dependencias existentes y variables de configuración ficticias
(no cargar credenciales de producción):

```bash
python -B manage.py check --settings=academico.test_settings
python -B manage.py makemigrations --check --dry-run --settings=academico.test_settings
python -B manage.py test --settings=academico.test_settings --noinput
```

El runner aislado comprueba SQLite `:memory:` antes de preparar tablas. No usar `migrate`
sobre una base persistente para probar F7. No hay tablas nuevas: el lanzador temporal F6
sigue siendo válido al disponer del código F7; no se necesita ampliar su lista de tablas.
El código aún no publicado no puede obtenerse mediante `git pull` hasta autorizar el push.

## Recorrido manual condensado

1. Abrir el entorno temporal en memoria de F6 con datos ficticios; entrar como Directora.
2. Finanzas → Centro. Verificar período actual y separar las tarjetas de situación actual.
3. Registrar por las interfaces existentes, en una caja propia abierta: cobro académico,
   ingreso administrativo, donación y egreso autorizado/desembolsado. Volver a Resultados:
   deben aparecer una vez; una autorización aún sin desembolso no es gasto.
4. Filtrar por método/categoría; descargar CSV y abrir la vista imprimible. Comparar
   filtros, detalle y totales. En celular todos los campos y acciones deben ser accesibles.
5. Autorizar beca/padrinazgo por sus flujos vigentes. El compromiso no suma ingresos ni la
   beca egresos; revisar Cuentas, Beneficios y Solvencia frente al portal del mismo estudiante.
6. Revisar un convenio y comparar cuotas con obligaciones; no sumar ambas deudas.
7. Solicitar/aprobar anulación válida con caja abierta: resultado excluye la operación,
   arqueo conserva dinero físico/retención. Revisar auditoría y posteriormente la foto al
   cerrar. No alterar cierres históricos para hacer esta prueba.
8. Entrar como Administración: mismas consultas sin facultades nuevas de autorización.
   Secretaría conserva su operación; URL directa F7 y CSV deben rechazarla.

## Requisitos obligatorios pendientes antes de despliegue

1. **Unificar definitivamente solvencia Django/SQL incluyendo F6**. La función original
   `database/scripts/15_funcion_solvencia_estudiante.sql` y las vistas de scripts 16/17 siguen
   sin representar por sí solas las coberturas F6. Ningún reporte, integración o autorización
   futura debe utilizar esas salidas como criterio completo. Revisar consumidores SQL y
   permisos de acceso en la integración; F7 no modifica esas funciones ni autoriza tal DDL.
2. **PostgreSQL aislado**: restricciones F2–F6, bloqueos, rollback, concurrencia y fuentes
   concurrentes; verificar lectura repetible/solo lectura y función por lotes con fechas
   locales. Medir planes/costos con volumen representativo. SQLite no satisface este requisito.
3. Conciliar datos históricos advertidos antes de certificar un resultado financiero
   exhaustivo. F7 no crea créditos, devoluciones ni reparaciones automáticas.
4. F8 permanece en [backlog](../backlog/F8_ui_ux.md); no se rediseñan módulos anteriores.

Sin autorización estructural pendiente para F7: no cambia esquema, restricciones ni políticas.
Commit local autorizado, push y despliegue pendientes de autorización expresa.

## Archivos de implementación

Nuevos: `financiero/lectura.py`; `reportes/financiero_fuentes.py`,
`financiero_consultas.py`, `financiero_forms.py`, `financiero_views.py`,
`test_financieros.py`; `static/css/reportes_financieros.css`;
`templates/reportes/financiero.html`; este documento y evidencias F7.

Modificados: `financiero/consultas.py` y `aportes.py` solo para delegar la lectura compartida;
`reportes/urls.py`; accesos en `templates/financiero/panel.html` y
`templates/reportes/panel.html`; manuales de Finanzas/Reportes y backlog F8.
