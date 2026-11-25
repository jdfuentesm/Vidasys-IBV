# F8.6 — Auditoría integral y cierre técnico de interfaces

Fecha: 2026-11-25 (El Salvador). Base: `4a9b86174d1f5b2ee105e4f72eeaf61f7ddb7f81`,
rama `semana-9-rutas-calificaciones`. Datos ficticios, SQLite exclusivamente en memoria.

## Dictamen

**F8 lista para cierre técnico de interfaces en el alcance ensayado. No lista para
despliegue.** No se reprodujeron defectos bloqueantes o altos de interfaz. Se corrigió
documentación que describía como pendientes flujos ya implementados y se añadió una
prueba de continuidad entre apoyos financieros y cierre/corrección académica. No fue
necesario modificar plantillas, CSS, JavaScript o código operativo.

La auditoría no certifica accesibilidad universal, concurrencia PostgreSQL, escalabilidad,
seguridad de una instalación productiva ni comprensión con usuarios reales. Los riesgos
abiertos tienen evidencia y siguiente paso, sin presentarlos como funcionalidades resueltas.

## Alcance y fuentes contrastadas

- Documentación y evidencias `docs/frontend/F81*` a `F85*`, backlog F8, manual y evidencias F7.1.
- Navegación `core/templatetags/navegacion.py`, estructura `core/aplicacion.html`,
  componentes y scripts compartidos; paneles y bandeja de solo lectura.
- Vistas/formularios académicos y servicios originales `academico/flujo.py`,
  `solicitudes.py`, `correcciones.py`; libro por lote, revisiones firmadas y cierre.
- Finanzas: cobros, caja, becas, convenios, anulaciones, operaciones y aportes;
  cálculos canónicos, validaciones por rol, resolución y recibos originales.
- Portal y reportes: identidad de sesión, solvencia en servidor, DTO públicos,
  propiedad de recibos, filtros de curso, CSV e impresión.
- Configuraciones de simulación y despliegue leídas sin conectarse a PostgreSQL.

## Resultados verificables

| Comprobación | Resultado y evidencia |
| --- | --- |
| Base automatizada | 748 pruebas aprobadas antes de cambios |
| Regresión final | 749 aprobadas: 748 conservadas + 1 integración transversal |
| Recorridos generales | 252 combinaciones rol/ruta/ancho/JS; HTTP esperado, sin desbordamiento exterior |
| Portal | 54 combinaciones adicionales: tres perfiles, tres anchos, con/sin JS; privacidad y propiedad |
| Docente | 48 pantallas más operaciones: lote, cálculo servidor, error 101, reintento, asistencia y guardado sin JS |
| Secretaría | 60 pantallas más operaciones: estudiante, cobro, recibo, error y reenvío; matrícula F7.1 bloqueada correctamente |
| Navegación/teclado | 200 controles y 47 destinos de menú autorizados; detalles, foco y salto al contenido |
| Resoluciones | 390, 768 y 1366 px; revisión adicional del menú a 320 px |
| Contraste | 12 pares de tokens presentes en CSS, recalculados; no sustituye evaluación completa de todas las combinaciones |
| Integridad | 619 comprobaciones de conciliación antes y después de consultas; huella lógica F7.1 idéntica |
| Rendimiento | 24 pantallas, tres peticiones secuenciales por pantalla con Django Client y conteo SQL |

La [carpeta de evidencias](../evidencias/F86/README.md) contiene registros, capturas y
resultados. Los tiempos Chromium incluyen navegación/render y algunos recorridos se
ejecutaron concurrentemente: **no** son una prueba de carga. Para comparar costos usar
las mediciones secuenciales de Django Client, que excluyen transporte y render del navegador.

## Hallazgos

| ID / prioridad | Evidencia, consecuencia y resolución |
| --- | --- |
| F86-01 / Medio, resuelto | `integracion_institucional.md` afirmaba que no había indicadores y que becas, cuotas y anulaciones seguían pendientes. Podía inducir pruebas o planificación incorrectas. Guía actualizada con alcance vigente y enlaces F8.2–F8.6. |
| F86-02 / Medio, cubierto | Riesgo de integración: los módulos tenían pruebas específicas, pero faltaba un único recorrido que conciliara beca + padrinazgo + cobro/reenvío + cierre + corrección de resultado sin alterar finanzas. `core/test_integracion_f86.py` lo comprueba con seis cursos activos, fuera de la semilla. |
| F86-03 / Medio, abierto | Libro cerrado de 20 alumnos: 172 consultas, 102 SELECT idénticos repetidos, mediana 88,86 ms en este ensayo. La elegibilidad invoca validaciones por inscripción. No impide operar con 40 alumnos; diseñar lectura compartida y medir PostgreSQL sin duplicar reglas. No se modificó servicio alguno. |
| F86-04 / Medio, abierto | Bandeja unificada pagina después de materializar los orígenes; reportes e historiales propios cargan conjuntos completos. En este tamaño la bandeja usa 29 consultas, sin SELECT idénticos repetidos; el riesgo es volumen/materialización, no un N+1 demostrado en ella. Ensayar historial grande antes de optimizar. |
| F86-05 / Bajo, abierto | Enlaces secundarios de los inicios D/A/S miden 19–22 px de alto; muchos son enlaces en línea. Revisar tamaño, separación y comprensión con personas en teléfono. El tamaño aislado no demuestra incumplimiento: considerar excepciones de texto y separación. Ningún botón inaccesible se reprodujo. |
| F86-06 / Bajo, aclarado | El contador histórico F8.4 `envios_doble_submit` se serializó después de un POST inválido adicional; su aserción inmediata sí comprobó un envío. Evidencia F8.6 separa `envios_doble_submit=1` y total incluyendo error=2. No se alteran las evidencias históricas. |
| F86-07 / Fuera de F8, requisito previo al despliegue | Solvencia Django/SQL, esquema histórico, PostgreSQL aislado, transacciones/concurrencia/idempotencia y configuración productiva siguen sin validación integral de esta versión. Ver plan separado; ninguna conclusión SQLite los resuelve. |
| F86-08 / Fuera de F8, pendiente funcional | No existe servicio formal de transición de convenios a INCUMPLIDO. La simulación conserva ACTIVO con cuotas vencidas; no se cambia esa regla ni se inventa una pantalla. |

No se identificó un defecto funcional reproducible que exigiera modificar las capas
protegidas dentro de esta auditoría. Si aparece, requiere evidencia, clasificación
alta/bloqueante y autorización separada; no debe resolverse debilitando validaciones.

## Continuidad e integridad

Ver [informe de integridad](F86_integridad.md). El nuevo test parte de un fixture académico
con seis cursos activos y matrícula con seis obligaciones por USD 120. Aplica beca de
USD 10, reserva de padrinazgo de USD 10, cobra USD 100 y recibe USD 10 del padrino.
El reenvío no duplica pago ni movimiento. Registra nota provisional 80, cierra con seis
presencias, obtiene APROBADA y tramita corrección autorizada a 69,99: cambia el resultado
a REPROBADA_ACADEMICAMENTE, conserva cierre/asistencia y mantiene los mismos totales
financieros. Las interfaces y servicios originales siguen siendo la autoridad.

El test cruza capas usando HTTP para cobro, libro, cierre, comparación/envío de corrección
y decisión. Los apoyos se autorizan mediante sus servicios originales y las sesiones/
presencias se preparan como fixture explícito; no se presenta todo el recorrido como
una prueba E2E exclusivamente de navegador. La cobertura HTTP específica de apoyos,
permisos, CSRF y rollback se conserva en los tests anteriores.

## Reproducción y límites

Consultar [matriz por rol](F86_matriz_roles.md), [checklist](F86_seguridad_accesibilidad.md),
[aceptación Windows/teléfono](F86_aceptacion_manual.md) y
[requisitos PostgreSQL/despliegue](../despliegue/F86_requisitos_pendientes.md).

Incidencias del instrumental, no del producto: se lanzaron dos scripts antes de terminar
la generación y no encontraron la clave temporal; se repitieron tras esperar al servidor.
Un selector del script de teclado fue renombrado accidentalmente a `.f86-libro` al copiarlo;
se corrigió al selector existente `.f84-libro` y aprobó. El test nuevo usó inicialmente un
nombre de URL inexistente; se ajustó a `solicitar_correccion` sin cambiar rutas del producto.
Ninguna de las 748 pruebas preexistentes falló. Los resultados publicados corresponden a
las ejecuciones completadas, no a esos intentos del instrumental.

Las credenciales aleatorias se leyeron en memoria desde la consola temporal para iniciar
sesión, nunca se incorporaron a Git. No hubo usuarios reales, Neon, migraciones persistentes,
PostgreSQL, despliegue, modificaciones a main ni aplicación/eliminación de stash o ZIP.
