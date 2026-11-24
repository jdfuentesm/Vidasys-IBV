# F8.4 — Evidencias docentes

Antes: exportación aislada de `5057a8283bdec999ba39c9b65e4abcb52ece25c1`; después:
F8.4. F7.1 sin modificar, semilla **711**, referencia **2026-11-22**, Chromium a
390/768/1366 × 900 px. Datos ficticios, SQLite exclusivamente en memoria. Sin credenciales,
cookies ni bases en estas evidencias. Cada comparación visual parte del escenario inicial,
antes de las operaciones adicionales de navegador.

## Resultados

- [729 pruebas aprobadas](pruebas.txt): las 706 anteriores intactas y 23 nuevas.
- [48 pantallas y operaciones docentes](operaciones_navegador.json): dos maestros,
  cursos activo/finalizado, libro, asistencia, calendario, cierre, solicitudes y reportes;
  390/768/1366 px; sin desbordamiento exterior ni errores JavaScript.
- [126 pantallas de regresión por rol](regresion_navegador.json): preservan estados HTTP
  y protección de cursos, portal insolvente, reportes y bandeja restringida.
- [Teclado y accesibilidad](teclado.json): salto al contenido, apertura con Espacio,
  Tab entre componentes, foco visible, semántica table/rowheader en Chromium y encabezado
  fijo durante el desplazamiento. No equivale a prueba con lector de pantalla real.
- Un solo DOM por lote: 180 campos numéricos (20 × 9), antes y después. IDs y nombres de
  controles únicos; el nombre multivaluado `inscripciones` conserva su lista original.
- Cambio 390→768→1366→390 conserva FormData. Buscar un estudiante no cambia ni reduce
  el lote enviado. Doble intento de submit: un solo envío de guardado.
- Cálculo y guardado de una nota 80,00 desde los componentes originales, inscripción
  CURSANDO y etiqueta provisional. Vista previa del servidor; filas sin editar conservan
  su estado mostrado. Sin guardado individual ni fórmula nueva.
- POST manipulado con 101: rechazo, valor conservado, foco al error y componente abierto;
  al recargar continúa 75,00 en tarea y 80,00 final. Ninguna actualización parcial.
- Asistencia: modificación permitida a AUSENTE_JUSTIFICADA con observación y confirmación.
  Guardado de observación de calificación sin JS, mismo lote y nota conservada.
- CSV/impresión académica responden correctamente; cursos ajenos rechazados. Las filas
  por inasistencia del curso cerrado no tienen enlace de corrección; las disponibles abren
  el procedimiento original. Pruebas SQLite cubren también pendientes, nota faltante,
  incoherencia, dos injustificadas con estado inconsistente y fallos de lectura.

[Conciliación inicial](simulacion_inicial.json): mismos conteos y esperados académicos y
financieros antes/después. 40 estudiantes, 12 cursos (6 activos/6 finalizados), 240 obligaciones,
132 pagos, 1.236 asistencias y 148 calificaciones. Resultados de inscripción: 70 aprobadas,
38 reprobadas por nota, 12 por inasistencia y 120 cursando. Ingresos USD 2.764, egresos USD 86,
resultado USD 2.678, saldo USD 1.952. Las operaciones docentes posteriores no cambian las cifras
financieras; la nota provisional y la asistencia modificada son cambios deliberados del ensayo.

## Medidas del libro

[Comparación completa](comparacion_libro.json), [antes](medidas-antes.json) y
[después](medidas-despues.json). Anchos en píxeles; la columna horizontal mide desplazamiento
interno necesario, no desbordamiento exterior del documento.

| Curso / ancho de pantalla | Tabla antes | Tabla después | Horizontal antes → después |
| --- | ---: | ---: | ---: |
| Finalizado 1 / 390 | 1.960,86 | 360 | 1.601 → 0 |
| Activo 4 / 390 | 1.931,59 | 360 | 1.572 → 0 |
| Finalizado 1 / 768 | 2.008,86 | 738 | 1.271 → 0 |
| Activo 4 / 768 | 1.979,59 | 738 | 1.242 → 0 |
| Finalizado 1 / 1366 | 2.008,86 | 1.052 | 957 → 0 |
| Activo 4 / 1366 | 1.979,59 | 1.052 | 928 → 0 |

Identidad, nota y estado quedan visibles juntos sin desplazamiento horizontal. La cifra
histórica de 2.192 px corresponde a F7.1; esta comparación usa el commit base F8.3 y la
configuración actual, con sus medidas reales, sin sustituirlas por la cifra histórica.

En móvil aumenta la altura del documento: finalizado **1.805 → 8.209 px**, activo
**1.792 → 7.054 px**. Antes la lista estaba dentro de una región de alto limitado y scroll
horizontal/vertical; ahora las 20 fichas forman parte del documento. No se afirma reducción
vertical. Hay índice nativo, búsqueda local y componentes plegables, conservando información
y lote. Escritorio mantiene scroll vertical interno y componentes abiertos con JS. Sin JS,
se abren manualmente. Validar comprensión y comodidad con personas reales.

## Capturas

| Pantalla | Antes | Después |
| --- | --- | --- |
| Libro activo móvil | [Antes](antes-04-libro-390.png) | [Después](despues-04-libro-390.png) |
| Libro activo tableta | [Antes](antes-04-libro-768.png) | [Después](despues-04-libro-768.png) |
| Libro activo escritorio | [Antes](antes-04-libro-1366.png) | [Después](despues-04-libro-1366.png) |
| Libro finalizado móvil | [Antes](antes-01-libro-390.png) | [Después](despues-01-libro-390.png) |
| Libro finalizado tableta | [Antes](antes-01-libro-768.png) | [Después](despues-01-libro-768.png) |
| Libro finalizado escritorio | [Antes](antes-01-libro-1366.png) | [Después](despues-01-libro-1366.png) |
| Inicio maestro, activo | [Antes](antes-04-inicio-390.png) | [Después](despues-04-inicio-390.png) |
| Inicio maestro, finalizado | [Antes](antes-01-inicio-390.png) | [Después](despues-01-inicio-390.png) |
| Mis cursos, activo | [Antes](antes-04-cursos-390.png) | [Después](despues-04-cursos-390.png) |

También se conservan capturas de inicio/Mis cursos en 768 y 1366 para ambos maestros.
[Edición móvil](edicion-390.png), [error con valor preservado](error-390.png) y
[asistencia](asistencia-390.png).

[Inventario, fuentes, permisos y recorrido Windows/móvil](../../frontend/F84_maestros_libro.md).

Pendientes: evaluación con usuarios/lectores reales, rendimiento de elegibilidad para cursos
grandes y validación PostgreSQL aislado; no se modifica el validador institucional para optimizar
la interfaz. No se prueba nueva conexión física LAN ni concurrencia de producción. Continúan
solvencia Django/SQL, convenios INCUMPLIDO y despliegue posterior; F8.5/F8.6 sin implementar.
