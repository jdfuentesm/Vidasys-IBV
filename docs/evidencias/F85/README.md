# F8.5 — Portal estudiantil

Antes: árbol exportado de `7bb4d0a21aeba633886037d79dc26cd703367583` en un directorio
independiente. Después: F8.5. Mismo lanzador F7.1, semilla **711**, referencia **2026-11-22**,
Chromium a 390/768/1366 × 900 px. Datos ficticios y SQLite exclusivamente en memoria.
No se incluyen credenciales, cookies ni bases persistentes.

## Validación

- [748 pruebas aprobadas](pruebas.txt): 729 anteriores y 19 específicas de F8.5.
- [54 pantallas y controles del portal](portal_navegador.json), con y sin JavaScript:
  estudiantes SIM-001, SIM-017 y SIM-029, tres resoluciones, inicio/cuenta/academia.
  HTTP esperado, sin desbordamiento exterior ni errores JS.
- [126 pantallas de regresión por rol](regresion_navegador.json): Dirección, Administración,
  Secretaría, Maestro, Estudiante y Pastor; permisos y restricciones previos conservados.
- ID de recibo ajeno: 404. Cambiar parámetros de estudiante/usuario/matrícula/formato no
  cambia identidad ni elude la restricción académica. Endpoints institucionales alternativos:
  403 para alumnos. POST con CSRF válido: 405 en las consultas del portal.
- SIM-017 conserva acceso financiero y sus recibos; academia sigue 403. No se incluye su
  matrícula o materias en el inicio restringido. SIM-029 conserva acceso académico por F6,
  saldo financiero USD 120, cobertura efectiva USD 120 y cargo propio USD 0. Un compromiso
  no genera pagos: ausencia de recibos propios se presenta como estado vacío real.
- Pruebas SQLite adicionales: futuro autorizado sin cobertura efectiva todavía, privacidad
  de datos del padrino, proyección de asignación propia sin objetos privados, cuenta coherente
  con F7, notas provisionales sin aprobación inferida, errores sin falsos ceros y lecturas sin
  escrituras. Las reglas canónicas y los contratos de autorización no cambian.
- Teclado: salto al contenido y apertura de detalles con Espacio. Detalles, navegación y
  recibos funcionan sin JS. [Recibo ficticio](recibo-ficticio.pdf) y [vista móvil](recibo-390.png).

[Conciliación inicial](simulacion_inicial.json): mismos conteos y valores esperados antes y
después; 40 estudiantes, 240 obligaciones, 132 pagos, ingresos USD 2.764, egresos USD 86,
resultado USD 2.678 y saldo USD 1.952. Validación CONCILIADO. Resultados académicos iniciales:
70 aprobadas, 38 reprobadas por nota, 12 por inasistencia y 120 cursando. El recorrido F8.5
es de lectura: no introduce nuevos cobros, asistencia, notas, solicitudes o autorizaciones.

## Comparación móvil

Mismo escenario, rutas, ancho 390 px y alto de viewport 900 px. Altura completa del documento,
detalles inicialmente plegados. Toda la información sigue disponible al ampliarlos; no se
pretende que se haya eliminado el costo de leer el historial completo.

| Alumno / pantalla | Antes px | Después px | Reducción |
| --- | ---: | ---: | ---: |
| SIM-001 / cuenta | 5.951 | 4.310 | 27,58 % |
| SIM-001 / materias | 6.165 | 2.437 | 60,47 % |
| SIM-017 / cuenta | 6.267 | 4.644 | 25,90 % |
| SIM-029 / cuenta | 4.770 | 2.870 | 39,83 % |
| SIM-029 / materias | 6.389 | 2.623 | 58,95 % |

[Comparación de las 27 vistas](comparacion.json), [medidas antes](medidas-antes.json) y
[después](medidas-despues.json). Los errores 403 no se cuentan como pantallas académicas
exitosas. No hay desbordamiento horizontal en ninguno de los tres anchos.

## Capturas

| Vista | Antes | Después |
| --- | --- | --- |
| Solvente: inicio móvil | [Antes](antes-01-inicio-390.png) | [Después](despues-01-inicio-390.png) |
| Solvente: cuenta móvil | [Antes](antes-01-cuenta-390.png) | [Después](despues-01-cuenta-390.png) |
| Solvente: materias móvil | [Antes](antes-01-academico-390.png) | [Después](despues-01-academico-390.png) |
| Insolvente: inicio móvil | [Antes](antes-17-inicio-390.png) | [Después](despues-17-inicio-390.png) |
| Insolvente: cuenta móvil | [Antes](antes-17-cuenta-390.png) | [Después](despues-17-cuenta-390.png) |
| Insolvente: acceso académico | [Antes 403](antes-17-academico-390.png) | [Después 403](despues-17-academico-390.png) |
| Padrinazgo: inicio móvil | [Antes](antes-29-inicio-390.png) | [Después](despues-29-inicio-390.png) |
| Padrinazgo: cuenta móvil | [Antes](antes-29-cuenta-390.png) | [Después](despues-29-cuenta-390.png) |
| Padrinazgo: materias móvil | [Antes](antes-29-academico-390.png) | [Después](despues-29-academico-390.png) |

Se conservan también todas las capturas en 768 y 1366 px con el mismo patrón de nombres.
[Fuentes, permisos y recorrido Windows/móvil](../../frontend/F85_portal_estudiante.md).

Pendientes: comprensión con estudiantes, lectores de pantalla reales y grandes historiales;
no se certifica una conexión física LAN nueva ni concurrencia PostgreSQL. La fuente SQLite
no sustituye la integración pendiente de solvencia Django/SQL. PostgreSQL aislado, convenios
INCUMPLIDO y despliegue web siguen registrados; no se implementa F8.6.
