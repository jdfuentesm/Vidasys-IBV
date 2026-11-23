# F8.1 — Evidencias antes y después

Datos totalmente ficticios de F7.1: semilla 711, referencia 2026-11-22. Los «antes» se
capturaron desde una exportación independiente del commit c272928, sin modificar el
repositorio; los «después», desde el árbol F8.1. Ambas instancias usan SQLite en memoria.
No hay contraseñas, cookies ni datos personales reales en estas evidencias.

| Escenario | Antes | Después |
| --- | --- | --- |
| Dirección, celular 390 px | [Antes](antes-directora-390.png) | [Después](despues-directora-390.png) |
| Dirección, escritorio 1366 px | [Antes](antes-directora-1366.png) | [Después](despues-directora-1366.png) |
| Secretaría, tableta 768 px | [Antes](antes-secretaria-768.png) | [Después](despues-secretaria-768.png) |

La captura completa del inicio de Dirección en 390 px pasa de 2570 a 1374 px; en escritorio,
de 1387 a 952 px. Secretaría en tableta, de 1208 a 952 px. Son medidas de la página capturada
con esas condiciones, no una medición de productividad o comprensión de usuarios.
[Dimensiones de capturas](comparacion_capturas.json).

Otras vistas: [menú móvil abierto](menu-390.png), [reporte financiero en móvil](reporte-financiero-390.png),
[portal del estudiante](portal-estudiante-390.png), [impresión con criterios completos](impresion.png).

## Comprobaciones

- [114 pantallas en 390/768/1366](pantallas.json): consultas esperadas HTTP 200,
  sin desbordamiento exterior. Se mantienen rechazos por rol y restricción académica por
  insolvencia comprobados en el recorrido.
- [199 controles y matriz de 46 enlaces](navegacion_teclado.json): los seis roles,
  apertura/cierre, ARIA, foco, Escape, grupos, salto, cambio de tamaño, impresión y
  navegación sin JavaScript. Inicios adicionalmente revisados en 320 px.
- [12 pares de contraste](contraste.json): umbral 4,5:1 en texto, 3:1 en foco/borde.
- [Medidas de tablas y páginas](metricas.json): Cuentas todavía alcanza 30.430 px con
  25 registros en móvil; libro docente mantiene un contenedor de 360 px con contenido de
  1961 px. La reducción por escala tipográfica no resuelve esos diseños; siguen en backlog.

Se revisaron visualmente las capturas de inicio/menú móvil y la impresión. Se comprobaron
filtros, descarga CSV y PDF con los criterios completos. El resultado financiero íntegro
sigue siendo USD 2.678,00; no hubo operaciones académicas/financieras durante la navegación.

Las capturas no equivalen a entrevistas, certificación WCAG, pruebas de lectores de pantalla
ni ensayo PostgreSQL. El seguimiento de mejoras está en [backlog F8](../../backlog/F8_ui_ux.md).
