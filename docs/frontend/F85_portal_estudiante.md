# F8.5 — Portal del estudiante: fuentes y permisos

Base `7bb4d0a21aeba633886037d79dc26cd703367583`, rama `semana-9-rutas-calificaciones`.

## Auditoría previa a la implementación

| Información / ruta | Fuente actual | Permiso y contrato que se conserva |
| --- | --- | --- |
| Identidad `/portal/` | `Estudiante.usuario_id = request.user.pk` | Solo cuenta ESTUDIANTE activa, expediente único. IDs, correos y filtros del cliente no cambian identidad. |
| Acceso académico | `financiero.consultas.solvente` → lectura canónica F6/SQL | Se comprueba en cada petición académica; insolvente 403, fallo de lectura 503. Sin datos académicos en inicio insolvente/desconocido. |
| Ciclo de referencia | Última matrícula propia, solo si habilitado | Sin consulta o presentación de matrícula cuando se restringe acceso. No se presume nivel. |
| Materias/notas/asistencia | Matrículas e inscripciones propias y prefetched asistencias/calificación | `/portal/academico/`, GET/HEAD; resultado registrado y estado del curso, sin recomputar reglas. |
| Cuenta | `cuenta(estudiante)` | `/portal/cuenta/` disponible aun insolvente; datos financieros propios, sin acciones de cobro. |
| Saldo / cargo / cobertura | `saldo_total`, `saldo_estudiante_total`, `cobertura_total` y celdas de `cuenta` | Solo formateo; no sumas de saldos en plantillas ni otra fórmula. Reserva no equivale a cobertura efectiva o dinero recibido. |
| Becas | Aplicaciones APLICADA propias de cada obligación (campo existente `becas`) | Exoneración/descuento de la obligación propia; no egreso ni recibo de pago inventado. |
| Avisos | `RevisionPadrinazgo.notificacion` dirigida al estudiante | No se muestran motivos privados, snapshots de donantes ni observaciones internas. |
| Recibos | Pago filtrado por estudiante de sesión; snapshot del presentador actual | `/portal/recibos/<pago_id>/`; ajenos 404. Misma impresión, sin endpoints de edición/anulación. |
| Convenios | Consulta `convenios_portal` filtrada por propietario | Reorganiza obligaciones; no se suma como segunda deuda. No concede cobro/resolución. |

El portal es de solo lectura, sin formularios de escritura. POST 405 y respuestas sin caché
pública. Otros roles no obtienen portal de un alumno ni se autovinculan cuentas sin expediente.
Se conserva la información financiera autorizada y el bloqueo académico original. Los enlaces
de navegación existentes siguen sujetos al control del servidor; no son autorización de acceso.

Compromisos futuros: leer únicamente coberturas propias activas/aprobadas con fecha de inicio
futura y su pendiente calculado por `financiero.aportes.pendiente`. Devolver una proyección
explícita (descripción de obligación, inicio/límite y asignación pendiente propia), nunca el
modelo de donante, su identidad/contactos/documentos o el compromiso global de otros alumnos.

No se modifican modelos, migraciones, servicios, reglas, solvencia, permisos, rutas ni LAN.

## Presentación implementada

Inicio: identificación propia, situación de acceso en texto, ciclo solo cuando está autorizado,
dos tareas principales y avisos públicos. No crea indicadores ni muestra matrícula cuando
la solvencia es negativa/desconocida. La navegación general conserva sus enlaces, sujetos a
los mismos 403 del servidor. No se convierte un enlace en permiso.

Materias: fichas por inscripción y ciclo, estado académico almacenado traducido a lenguaje
sencillo, curso activo/finalizado, nota provisional/definitiva y ausencia de registro claramente
diferenciadas. Una nota provisional no muestra el estado APROBADA de la calificación como
resultado definitivo del alumno. Componentes y asistencias completos en detalles nativos;
no se añade un cálculo de aprobación, ausencias o promedios. Sin formularios ni nuevas APIs.

Cuenta: plantilla específica del portal, separada de la interfaz operativa. Tres importes
canónicos: saldo financiero, cargo del estudiante y cobertura efectiva. Obligaciones con
vencimiento/saldo/estado visibles; movimientos, descuento, reserva, beca y conciliación de
cada obligación ampliables. No hay sumas en plantilla, totales estimados ni acciones de
cobro/anulación/solicitud financiera. Recibos y convenios propios conservan endpoints y
filtros anteriores. Reservas y futuros no se mezclan con cobertura efectiva ni efectivo.

El adaptador `portal_presentacion.compromisos_futuros` retorna solo diccionarios con
`obligacion`, `inicio`, `limite` y `asignacion_propia`, obtenida de `pendiente(cobertura)`.
No retorna el objeto donante, solicitud/snapshot, porcentajes globales o compromiso de otros
alumnos. Solo se muestra la asignación propia pendiente de inicio futuro.

Errores: no se presume solvencia, cero de deuda o falta de matrícula por un fallo de lectura.
Inicio avisa si no puede leer ciclo/cobertura/notificaciones. El permiso continúa dependiendo
de la llamada canónica original, revalidada por el endpoint académico. Fallo de historial:
503 sin contenido académico parcial. Cuenta conserva el error original y recibos disponibles;
si solo falla la lectura adicional de futuros, muestra el aviso sin inventar más cobertura.

Se reutilizan estilos/tokens F8.1–F8.4, foco, navegación, detalles nativos y expansión para
impresión. F8.5 no añade JavaScript ni dependencias. Los recibos siguen usando el presentador
y plantilla originales, incluida su impresión. Operación esencial completa sin JavaScript.

## Validación y recorrido Windows/móvil

[Resultados, medidas y capturas](../evidencias/F85/README.md). Las pruebas cubren fuentes,
privacidad de padrinazgo efectivo/futuro, pertenencia, formatos/IDs manipulados, errores,
lectura sin escrituras y conciliación con F7. No se modifica el escenario de simulación.

Después de autorizar la publicación y actualizar la rama, ejecutar una alternativa:

```powershell
$env:PYTHONUTF8 = '1'
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22
# Alternativa LAN existente: solo con esa IP en Windows y Wi-Fi privada de confianza.
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22 --lan
```

Abrir `http://127.0.0.1:8000/login/` o `http://192.168.1.154:8000/login/`.
Contraseña temporal de consola; no guardarla en Git. Solo SQLite en memoria, sin migrar una
base persistente. Detener el lanzador descarta el ensayo; el lanzador no se modifica.

1. `sim-estudiante-01`: identificar nombre/código, solvencia y ciclo. Abrir materias;
   distinguir cursos activos/cerrados, notas y estados registrados. Ampliar componentes
   y asistencia; volver al inicio.
2. Cuenta: revisar los tres importes sin sumarlos como tres deudas. Abrir movimientos y
   apoyos de una obligación; consultar un recibo propio e imprimir/guardar PDF.
3. `sim-estudiante-17`: comprobar mensaje respetuoso y cuenta/recibos disponibles. El
   acceso directo a `/portal/academico/` debe seguir siendo 403, incluidos CSV/imprimir
   por parámetros. No hay calificaciones/asistencia en el inicio restringido.
4. `sim-estudiante-29`: comprobar cobertura efectiva de USD 120, cargo propio USD 0 y saldo
   financiero USD 120. La cobertura no es un pago: este alumno puede no tener recibos de
   pago propios. No fabricar comprobantes por la promesa de padrinazgo.
5. No debe aparecer identidad, correo, teléfono, documento o importe global del padrino.
   Compromisos futuros, cuando existan, no habilitan automáticamente acceso académico.
6. Teléfono a 390 px, tableta y escritorio: detalles, regreso, menú y estados legibles;
   repetir sin JS. Con teclado, Tab, salto al contenido y Espacio en detalles nativos.
   Una URL de recibo de otro estudiante debe responder 404.

## Límites y pendientes

Se cargan los historiales propios completos como antes; grandes historiales y paginación
futura requieren medición. Los detalles conservan toda la información y la impresión del
recibo no depende de ellos. Validar comprensión de saldo/reserva/cobertura con estudiantes
y lectores de pantalla reales. Chromium/teclado no certifican todas las tecnologías de apoyo
ni una nueva conexión física LAN. No se cambia el tratamiento de notificaciones públicas,
que siguen separadas de motivos y observaciones institucionales privadas.

Permanecen críticos PostgreSQL aislado, restricciones/transacciones/concurrencia, unificación
de solvencia Django/SQL, servicio formal de convenios INCUMPLIDO y despliegue web posterior.
F8.6 y trabajos PostgreSQL no implementados. Sin Neon, datos reales, bases persistentes,
cambios a main o publicación automática; commit local y push pendiente de autorización.
