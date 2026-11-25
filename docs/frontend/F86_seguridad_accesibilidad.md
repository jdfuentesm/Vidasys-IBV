# F8.6 — Checklist de seguridad y accesibilidad

Estados: **verificado** = evidencia del alcance ejercitado; **pendiente** = no certificado.
No equivale a una auditoría de penetración ni a conformidad total WCAG.

| Control | Resultado / evidencia |
| --- | --- |
| Sesión y menú de seis roles | Verificado: 47 enlaces autorizados responden 200; Pastor solo Inicio. `navegacion.json`. |
| Bandeja exclusiva y sin decisión por GET | Verificado: no Directora 403; GET manipulado no escribe, POST a bandeja 405. `core/test_paneles.py` y navegador. |
| Decisiones financieras/académicas | Verificado en tests HTTP/servicios: rol vigente, decisión por POST, firmas, snapshot y validación original; Administración técnica no suplanta a Dirección. |
| CSRF | Tests de cliente con `enforce_csrf_checks=True` conservados para solicitudes, cobro, portal, libro y LAN. No se desactiva middleware; login real por formulario con token. |
| Propiedad | Verificado: maestro ajeno 404; alumno no cambia identidad mediante parámetros; recibo ajeno 404; rutas institucionales 403 para Estudiante. |
| Insolvencia y fallo de lectura | Verificado: bloqueo 403 canónico del servidor; fallos de solvencia 503 y avisos sin saldos/estados inventados en casos cubiertos por tests. No se afirma disponibilidad ante cualquier fallo de infraestructura. |
| Métodos HTTP | Verificado: consultas protegidas rechazan POST con token válido (405); token ausente produce 403 CSRF donde corresponde. Un 403 CSRF no demuestra por sí solo un control de rol. |
| Privacidad | Verificado en portal: marcadores privados ausentes en HTML/atributos/contexto, formatos no abren JSON/CSV alternativos; no se exponen motivos internos del padrino. No hay exportación estudiantil nueva. |
| Totales y cálculo | Verificado: cálculo académico y financiero permanece en servidor; total cliente manipulado ignorado; 101 rechazado; no se cambian fórmulas ni redondeo. |
| Idempotencia/atomicidad | Suite: reenvíos, UUID ajeno/datos cambiados, decisiones contradictorias y rollback. Navegador: doble submit docente = 1 petición válida, pago reintentado = mismo recibo. SQLite no certifica bloqueo real. |
| Secretos/evidencias | Revisión de archivos de entrega y patrones de secretos; sin contraseñas, cookies, tokens, claves privadas, archivos de entorno o BD añadidos. Marcadores `example.test` son ficticios. |
| Menú accesible | 200 controles: Enter abre, Escape cierra y devuelve foco; aria-expanded/controls coherentes; menú nativo disponible sin JS; salto al contenido. |
| Libro y teclado | Tabla/encabezado de fila en árbol accesible Chromium; Tab entre componentes, foco visible y detalles con Espacio; encabezado fijo en escritorio. |
| Errores | Importe/nota inválidos conservan valor; resumen visible y foco; detalles del libro abren para permitir corrección. Tests existentes de asociación de errores a campos conservados. |
| Responsive | 390/768/1366, sin desbordamiento exterior en rutas registradas; tablas pueden tener región de desplazamiento propia. Un solo conjunto de campos del libro al cambiar resolución. |
| Sin JavaScript | Seis roles consultan rutas; menú/grupos nativos, pago y lote funcionan. No se confunde falta de cálculo orientativo con autorización para omitir validación del servidor. |
| Contraste | Doce pares de tokens actuales recalculados: texto ≥4,5:1, bordes/foco ≥3:1 en las combinaciones medidas. No cubre cada posible estado, imagen, zoom o combinación. |
| Tacto | Controles operativos ejercitados; enlaces secundarios de 19–22 px identificados para evaluación de separación y usabilidad, sin declaración automática de incumplimiento. |
| Impresión/exportación | CSV y vistas imprimibles originales accesibles a roles autorizados; PDF de reporte y recibo, sin navegación en impresión. Protecciones CSV originales conservadas. |
| Tecnologías de apoyo y usuarios | Pendiente: lectores de pantalla reales, personas con limitaciones motrices/visuales/cognitivas, navegadores/dispositivos físicos y comprensión del vocabulario. |
| Producción | Pendiente: PG aislado, TLS/proxy, cookies/hosts/CSRF reales, estáticos WhiteNoise y monitoreo. No se prueba una publicación desde runserver. |

La inspección visual corresponde a capturas de datos ficticios; no contiene evaluaciones
con usuarios reales. Los enlaces pequeños, altura vertical y volumen de historiales se
conservan en backlog para evaluación, sin eliminar información académica o financiera.
