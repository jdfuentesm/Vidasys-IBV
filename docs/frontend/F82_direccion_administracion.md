# F8.2 — Dirección, Administración y consultas compactas

Base: `9be4d344ad38594497ac674252d2d486395c1f96`, rama
`semana-9-rutas-calificaciones`. Presentación y lectura; no cambia decisiones,
contratos de formularios operativos, servicios, modelos, migraciones ni solvencia.

## Indicadores y fuentes

| Panel / indicador | Fuente existente | Alcance y enlace |
| --- | --- | --- |
| Dirección: estudiantes activos | `Estudiante.estado=ACTIVO` | Expedientes activos; no equivale a matrícula ni solvencia. |
| Cursos activos | `Curso.estado=ACTIVO` | Materia, ciclo y docente; detalle de inscripciones del reporte académico. |
| Resultados académicos | Agrupación de `InscripcionCurso.estado` almacenado | Todas las inscripciones/ciclos, no estudiantes distintos; desplegable. No recalcula notas. |
| Solventes/insolventes | F7 `solvencia` con `EstadoFinanciero` compartido | Todos los expedientes, incluida protección F6; no otra fórmula local. |
| Asuntos por revisar | Filas únicas de la bandeja | Separa decisiones PENDIENTE de seguimientos de solicitudes APROBADA. |
| Alerta de padrinazgo vencido | F7 `beneficios(PADRINAZGOS,VENCIDO)` | Protección efectiva pendiente; mantiene alerta visible y cobertura hasta resolución. |
| Administración: ingresos, egresos, resultado | Los tres `totales` del `panel` F7 | Período seleccionado, base de efectivo y estado vigente al generar. Mes actual por defecto; fechas vacías consultan todo. |
| Saldo financiero, cargo estudiante, protección | Tres tarjetas actuales del mismo panel F7 | Saldos actuales, separados del período. No suman compromisos a los ingresos. |
| Cajas y efectivo retenido | F7 `cajas` | Abiertas/cerradas, retenido conocido y fotografías con diferencias; no calcula caja disponible ni pérdidas nuevas. |
| Solicitudes financieras y autorizado sin desembolso | Tarjetas originales F7 | Enlaces de consulta; no amplía facultades de Administración. |

Los adaptadores ejecutan lectura consistente del servicio existente. Si falla una fuente,
se devuelve HTTP 503 sin indicadores parciales. Filtros inválidos: HTTP 400. Respuestas sin
caché pública. Fechas de generación visibles; los saldos actuales no son cortes históricos.

## Bandeja de Dirección y permisos

Nueva ruta de consulta: `/direccion/pendientes/`. No recibe decisiones; solo GET/HEAD.
POST devuelve 405. Permisos revisados en vista y adaptador antes de consultar.

| Fuente / tipo | Expediente original | Decisión o seguimiento |
| --- | --- | --- |
| `SolicitudAcademica`: cancelación/corrección | `solicitud_academica` | Pendiente o historial; propuesta calculada y almacenada por el servicio original. |
| `SolicitudBeca` | `becas_detalle` | Condiciones solicitadas; Dirección determina aplicación definitiva. |
| `SolicitudConvenio` | `convenios_solicitud` | Plan de cuotas, no ingreso ni deuda adicional. |
| `SolicitudEgreso` | `operaciones_egreso` | Pendiente; APROBADA sin desembolso sigue visible como seguimiento. |
| `SolicitudPadrinazgo` | `aportes_solicitud` / `aportes_revision` | Pendiente; aprobada y vencida con cobertura pendiente sigue en revisión. No retira protección. |
| `SolicitudAnulacion` | `anulaciones_detalle` | Pago; sin devolución automática de efectivo. |
| `SolicitudAnulacionOperacion` | `operaciones_anulacion` | Ingreso/egreso; sin devolución o recuperación física. |
| `AnulacionDonacion` | `aportes_anulacion` | Acceso al historial y efectos originales. |

Una fila por tipo y PK de origen. El seguimiento actualiza esa misma fila de presentación;
no duplica la solicitud, no cambia su estado ni crea tablas. APROBADA continúa APROBADA.
La bandeja ofrece tipo, fecha, persona/expediente, estado, consecuencia y enlace al trámite.
Motivo, decisión, fecha y responsable están en un desplegable. Filtros por atención/historial,
tipo, estado, búsqueda y fecha original de solicitud (inclusive). Veinte solicitudes por
página; controles arriba y abajo, conservando filtros. Los importes no se totalizan.

Clases extraordinarias tienen autorización directa, sin modelo de solicitud pendiente:
se conserva un enlace al flujo existente. Donaciones recibidas no son solicitudes por
aprobar; solo se incluyen las anulaciones y revisiones con fuente verificable. Revisiones
resueltas directamente siguen consultables en los historiales originales.

| Rol | Panel nuevo | Bandeja unificada | F7 | Operaciones |
| --- | --- | --- | --- | --- |
| Directora | Académico + solvencia + atención | Exclusivo | Consulta | Decide solo en sus procedimientos originales. |
| Administración | Operación financiera | 403 | Consulta | Ingreso, solicitud de egreso, caja; sin nueva autorización. |
| Secretaría | Inicio previo | 403 | 403 | Sus operaciones anteriores. |
| Maestro | Inicio previo | 403 | 403 | Sus cursos/solicitudes anteriores. |
| Estudiante | Portal previo | 403 | 403 | Sus datos, restricciones F6 intactas. |
| Pastor Principal | Inicio previo | 403 | 403 | Sin nuevos módulos. |

Se conservan CSRF, confirmaciones, permisos, idempotencia y validaciones de las rutas
originales. El enlace de lectura no concede permiso para decidir. Cuentas inactivas y
sesiones anónimas conservan la protección. No se muestran indicadores institucionales a
otros roles ni se aceptan decisiones manipuladas en parámetros GET.

## Centro F7 y cuentas por cobrar

- Primero tres indicadores del período; selector de reportes agrupado por finalidad.
- Período identificable; cambio de fechas y criterios técnicos ampliables. Advertencias
  críticas visibles. Desgloses y gráficos conservados en detalles nativos.
- Cuentas: 25 estudiantes por página, agrupados por URL/identidad del expediente, no por
  nombre. Sumas de las celdas canónicas de F7, sin nueva fórmula financiera.
- Cada estudiante muestra saldo, cargo y protección de la selección. Sus obligaciones
  conservan las 16 columnas originales dentro del detalle ampliable, incluidas conciliación,
  fechas y conceptos. Los filtros delimitan tanto el resumen como el detalle.
- Los constructores y datos originales `columnas`, `filas`, `totales`, `cantidad`,
  `pagina` y `filas_visibles` se conservan; la presentación añade `pagina_cuentas`.
- CSV e impresión consultan todas las obligaciones originales de la selección sin agrupar
  ni paginar. Desgloses del panel abiertos en impresión, incluso sin JavaScript.
- Paginación doble, filtros GET, detalles nativos y enlaces funcionan sin JavaScript.
  Se reutilizan tokens, foco, salto de contenido y navegación de F8.1; sin dependencias nuevas.

Componentes reutilizables: métricas de lectura, filas de seguimiento, filtros GET,
paginación doble, cuentas compactas, filas completas para impresión y desgloses financieros.
No se convierten en servicios de negocio ni sustituyen componentes operativos.

## Recorrido Windows y móvil

Tras publicar y actualizar la rama (este trabajo solo prepara commit local):

```powershell
$env:PYTHONUTF8 = '1'
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22
# Alternativa ya existente, únicamente en Wi-Fi privada y con esa IP en Windows:
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22 --lan
```

Ejecutar una alternativa, no ambas simultáneamente. Entrar en
`http://127.0.0.1:8000/login/`, o `http://192.168.1.154:8000/login/` en LAN.
Contraseña temporal mostrada por el lanzador; no se guarda en Git. Los datos desaparecen
al detenerlo. No ejecutar `manage.py migrate` sobre la configuración de demostración.

1. `sim-directora`: comprobar 40 activos, 6 cursos activos, 8 decisiones y 2 seguimientos;
   abrir situación académica y solvencia (31/9). Confirmar alerta de padrinazgo.
2. Abrir Pendientes, filtrar correcciones, abrir expediente y volver. Cambiar a historial,
   paginar y comprobar que aprobación y seguimiento mantienen el estado original.
3. `sim-administrador`: cambiar período a fechas vacías; ingresos 2.764, egresos 86,
   resultado 2.678 USD. Saldos actuales 1.952, cargo 1.312, protección 640 USD.
4. F7 → Cuentas: abrir las obligaciones de un estudiante, comprobar conciliación,
   filtrar y paginar; descargar CSV y abrir impresión completa (240 obligaciones sin filtro).
5. Móvil: menú, teclado, filtros y detalle; repetir sin JavaScript. Otros roles no deben
   acceder a la bandeja ni a F7 por URL. Ninguna visita GET aprueba solicitudes.

## Validación y pendientes

[Medidas, capturas y resultados verificables](../evidencias/F82/README.md).
Pruebas de consulta sin escritura, roles, fuentes, seguimientos sin duplicados, filtros,
paginación, errores, consultas acotadas, campos completos, CSV e impresión.

La bandeja materializa las fuentes y luego pagina; las consultas no crecen por solicitud,
pero memoria y tiempos sí crecen con el historial. Optimización para grandes volúmenes y
PostgreSQL aislado pendiente. La simulación no prueba concurrencia, SQL de producción,
comprensión de usuarios ni lectores de pantalla reales. No certifica LAN física: el lanzador
LAN previamente validado permanece idéntico y las comprobaciones visuales usan loopback.

Siguen obligatorias antes de despliegue la unificación de solvencia Django/SQL y las pruebas
PostgreSQL de restricciones, transacciones y concurrencia. Sigue pendiente el servicio formal
INCUMPLIDO. F8.3–F8.6 (formularios, libro docente, portal y otras mejoras) no implementadas.
