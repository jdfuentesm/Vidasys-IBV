# F8.2 — Evidencia de paneles y consulta

Simulación F7.1, **semilla 711, referencia 2026-11-22**, 40 estudiantes ficticios,
240 obligaciones, 132 pagos. Sin datos personales reales, credenciales, cookies ni base.
Antes: árbol exportado del commit `9be4d344ad38594497ac674252d2d486395c1f96` en
un directorio temporal separado. Después: implementación F8.2. Dos procesos sucesivos,
el mismo lanzador sin modificar, SQLite `:memory:`. Sin acceso a Neon ni migraciones persistentes.

Chromium, 390/768/1366 × 900 px, zoom normal, misma ruta y filtros. Capturas de cuentas
muestran la primera pantalla; la altura corresponde al documento completo, no al recorte.

| Pantalla, Dirección | 390 antes/después | 768 antes/después | 1366 antes/después |
| --- | --- | --- | --- |
| Cuentas, altura px | 30.430 / 7.756 | 14.779 / 6.492 | 11.828 / 6.428 |
| Panel F7, altura px | 5.845 / 2.360 | 3.586 / 1.768 | 3.035 / 1.587 |

Cuentas reduce **74,51 %** la altura móvil. Misma selección sin filtros (240 obligaciones):
antes se paginaban 25 obligaciones; ahora 25 estudiantes con todas sus obligaciones en
detalles nativos. Este cambio de unidad de paginación es deliberado; no equivale a quitar
obligaciones. Segunda página: 15 estudiantes. Todos los campos siguen accesibles; CSV e
impresión contienen las 240 obligaciones y 16 columnas originales.

El inicio crece respecto al antiguo selector de tareas porque ahora muestra información
verificable, con detalle académico plegable; no se reclama reducción de su altura.
[Medidas antes](medidas-antes.json) y [después](medidas-despues.json) contienen todas las rutas,
roles y anchos medidos. Ninguna anchura de documento supera su viewport.

## Capturas

| Vista | Antes | Después |
| --- | --- | --- |
| Dirección escritorio | [Antes](antes-directora-1366.png) | [Después](despues-directora-1366.png) |
| Dirección tableta | [Antes](antes-directora-768.png) | [Después](despues-directora-768.png) |
| Dirección móvil | [Antes](antes-directora-390.png) | [Después](despues-directora-390.png) |
| Administración escritorio | [Antes](antes-administrador-1366.png) | [Después](despues-administrador-1366.png) |
| Administración tableta | [Antes](antes-administrador-768.png) | [Después](despues-administrador-768.png) |
| Administración móvil | [Antes](antes-administrador-390.png) | [Después](despues-administrador-390.png) |
| Panel financiero móvil | [Antes](antes-panel-390.png) | [Después](despues-panel-390.png) |
| Cuentas móvil | [Antes](antes-cuentas-390.png) | [Después](despues-cuentas-390.png) |

Bandeja [escritorio](bandeja-1366.png) y [móvil](bandeja-390.png);
[obligaciones ampliadas sin JavaScript](cuentas-detalle-390.png).
No se simula una bandeja anterior inexistente.

## Comprobaciones

- [678 pruebas aprobadas](pruebas.txt): 649 conservadas + 29 nuevas. Django check sin incidencias.
  La expectativa visual del menú de Dirección incorpora el nuevo destino; no se quitan casos.
- [126 pantallas HTTP 200](navegador.json), datos abundantes y roles institucionales; sin
  desbordamientos exteriores. Rechazo de bandeja a todos los roles distintos de Dirección,
  F7 a roles restringidos y portal académico insolvente conservados.
- [Ocho controles sin JavaScript](sin_javascript.json): alerta visible, filtros GET,
  desplegables, paginación doble, enlaces originales de 49 solicitudes únicas, 16 columnas
  por obligación, PDF de 240 filas, desgloses abiertos al imprimir y salto por teclado.
- [Conciliación de la simulación](simulacion.json): mismo resumen y esperados antes/después,
  validación CONCILIADO; ingresos 2.764, egresos 86, resultado 2.678, saldo 1.952,
  protección 640, cargo estudiante 1.312 USD; solvencia 31/9.
- [Controles de integridad de presentación](controles.json): 49 solicitudes del historial,
  diez asuntos por atender (ocho decisiones y dos seguimientos), exportación completa.
- Prueba de crecimiento 1 → 25 solicitudes: lecturas acotadas, sin consulta por cada fila.
  Permisos en adaptador y vista, GET sin escritura y POST de bandeja rechazado. Formularios
  y servicios de decisión originales conservados, incluidos CSRF e idempotencia.

No se prueba concurrencia PostgreSQL, producción, lector de pantalla real ni comprensión de
personas. Se prueba loopback, no una conexión física LAN nueva. La simulación temporal utiliza
el adaptador de pruebas de solvencia; la unificación Django/SQL sigue siendo requisito previo
al despliegue. La bandeja carga el historial completo antes de paginar: optimización pendiente
para volumen grande. F8.3–F8.6 y servicio INCUMPLIDO no implementados.
