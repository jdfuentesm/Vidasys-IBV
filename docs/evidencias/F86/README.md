# F8.6 — Evidencias de auditoría, 2026-11-25

Base `4a9b86174d1f5b2ee105e4f72eeaf61f7ddb7f81`, semilla **711**, referencia
**2026-11-22**. Datos ficticios exclusivamente, SQLite `:memory:`. No hay bases,
contraseñas temporales, cookies, claves, tokens CSRF o hashes de autenticación adjuntos.

## Pruebas y navegación

- [748 pruebas base](pruebas-base.txt), [749 finales](pruebas-finales.txt) y [Django check](django-check.txt).
- [252 combinaciones generales](regresion_navegador.json): seis roles y tres perfiles
  de estudiante, tres anchos, con/sin JS. HTTP 200 esperado; comprobaciones negativas
  adicionales (403) se ejecutan en el instrumental y suite.
- [54 casos del portal](portal_navegador.json): privacidad HTML/atributos, URLs/formatos
  manipulados, insolvente 403, recibos ajenos 404, POST con CSRF válido 405, PDF y teclado.
- [48 pantallas y operaciones docentes](docente_operaciones.json): campos únicos,
  FormData estable al cambiar ancho, filtro sin pérdida del lote, error101 y foco,
  guardado con/sin JS, asistencia, CSV/impresión. El contador inmediato del doble submit
  es **1**, el total con el posterior intento inválido es **2**. Esta distinción aclara
  la etiqueta ambigua histórica F8.4 sin reescribir sus resultados.
- [60 pantallas y operaciones de Secretaría](secretaria_operaciones.json): confirmación
  sin POST previo, 1 POST de cobro válido y 2 en total incluyendo el posterior error;
  replay mediante cliente HTTP vuelve al mismo recibo. Dos campos heredados del script
  antiguo sobre matrícula positiva fueron excluidos porque no eran mediciones del
  navegador: esa matrícula se prueba de verdad en el fixture separado del test F8.6.
- [200 controles y 47 enlaces](navegacion.json); [teclado/semántica del libro](teclado.json);
  [12 pares de contraste](contraste.json); [medidas y controles secundarios pequeños](capturas.json).
- [Validación LAN sin abrir socket](lan_comprobar.json) y [revisión de secretos](secretos.json).

Se inició sesión con el formulario real y credenciales aleatorias de consola; nunca se
guardaron esas credenciales en la evidencia. Chromium Linux no demuestra una conexión
física desde el teléfono Windows ni conformidad total de accesibilidad.

## Capturas actuales

| Rol | 390 px | 768 px | 1366 px |
| --- | --- | --- | --- |
| Directora | [móvil](inicio-directora-390.png) | [tableta](inicio-directora-768.png) | [escritorio](inicio-directora-1366.png) |
| Administración | [móvil](inicio-administracion-390.png) | [tableta](inicio-administracion-768.png) | [escritorio](inicio-administracion-1366.png) |
| Secretaría | [móvil](inicio-secretaria-390.png) | [tableta](inicio-secretaria-768.png) | [escritorio](inicio-secretaria-1366.png) |
| Maestro | [móvil](inicio-maestro-390.png) | [tableta](inicio-maestro-768.png) | [escritorio](inicio-maestro-1366.png) |
| Estudiante | [móvil](inicio-estudiante-390.png) | [tableta](inicio-estudiante-768.png) | [escritorio](inicio-estudiante-1366.png) |
| Pastor | [móvil](inicio-pastor-390.png) | [tableta](inicio-pastor-768.png) | [escritorio](inicio-pastor-1366.png) |

[Menú abierto](menu-390.png), [cuentas](cuentas-390.png),
[libro cerrado](libro-cerrado-390.png), [error de nota](libro-error-390.png),
[confirmación de cobro](cobro-confirmacion-390.png), [error de cobro](cobro-error-390.png).
[Reporte PDF](reporte-ficticio.pdf) y [recibo PDF](recibo-ficticio.pdf).

F8.6 no rediseña el producto: no se crean comparaciones antes/después artificiales.
Las comparaciones de F8.1–F8.5 permanecen en sus carpetas originales.

## Integridad y rendimiento

- [Integridad inicial/final](integridad.json): 619 comprobaciones antes y después de
  consultas, huella lógica idéntica a F7.1; ningún password del objeto escenario serializado.
- [Medición secuencial](rendimiento.json): 24 pantallas × 3 solicitudes Django Client,
  milisegundos y consultas SQL, sin transporte/render de Chromium. Sirve para localizar
  lecturas costosas; no es SLA ni medición PostgreSQL. El arranque incluye generación y
  validación en procesos independientes.
- La navegación general se ejecutó parcialmente en paralelo con otros lectores: sus
  tiempos HTTP observados incluyen contención y no deben compararse con los secuenciales.
- Las operaciones docentes y de Secretaría usan memorias separadas/regeneradas; los
  cambios deliberados y deltas están en [el informe de integridad](../../frontend/F86_integridad.md).

## Reproducción

La suite utiliza `manage.py test --settings=academico.test_settings --noinput`; el test
transversal es `core.test_integracion_f86`. El generador se valida con
`iniciar_simulacion.py --semilla 711 --fecha 2026-11-22 --comprobar`. Los recorridos de
navegador usaron Playwright/Chromium del entorno de revisión, sin añadir dependencias
a la aplicación. Los scripts temporales automatizan las rutas registradas en los JSON;
el [recorrido manual](../../frontend/F86_aceptacion_manual.md) permite verificarlas sin
esas herramientas. No se publica el log bruto del lanzador porque contiene una clave efímera.

Informe y límites: [auditoría](../../frontend/F86_auditoria_integral.md),
[matriz](../../frontend/F86_matriz_roles.md), [checklist](../../frontend/F86_seguridad_accesibilidad.md),
[requisitos PostgreSQL/despliegue](../../despliegue/F86_requisitos_pendientes.md).
