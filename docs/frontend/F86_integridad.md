# F8.6 — Integridad académica y financiera

La validación original F7.1 se ejecutó en una nueva base SQLite `:memory:` con semilla
711 y referencia 2026-11-22. Se repitió tras las mediciones GET. No se mezcló con el
fixture de integración ni con las sesiones de navegador que registran operaciones.

| Fuente | Inicial y tras consultas |
| --- | ---: |
| Estudiantes / matrículas | 40 / 40 |
| Cursos / inscripciones | 12 / 240 |
| Cursos activos / finalizados | 6 / 6 |
| Sesiones / asistencias / calificaciones | 74 / 1.236 / 148 |
| Presencias / ausencias justificadas / injustificadas | 1.176 / 36 / 24 |
| Aprobadas / reprobadas académicamente / por inasistencia / cursando | 70 / 38 / 12 / 120 |
| Obligaciones / pagos | 240 / 132 |
| Ingresos vigentes / egresos | USD 2.764 / USD 86 |
| Resultado | USD 2.678 |
| Saldo financiero | USD 1.952 |
| Protección efectiva / a cargo del estudiante | USD 640 / USD 1.312 |
| En convenio / directo a cargo del estudiante | USD 320 / USD 992 |
| Compromisos pendientes | USD 760; no sumarlos a dinero recibido |

Las 619 comprobaciones independientes de `simulacion.validacion.validar` aprobaron
antes y después de las mediciones. La huella lógica de nombres/libro/cargos/notas es
`37e3d0aa11a3a050250883f513f5750e9e74277d51697b7ed350f4eed03d9f22`, idéntica a
`docs/evidencias/F71/resultado_simulacion.json`. No es una huella binaria de la BD ni
incluye credenciales aleatorias. Las sesiones HTTP efímeras de autenticación no forman
parte de las cifras institucionales. Ver [integridad.json](../evidencias/F86/integridad.json).

## Separación de ensayos que escriben

| Proceso independiente | Operaciones y efecto esperado |
| --- | --- |
| Simulación para consultas/capturas | Base inicial regenerada; recorridos GET no alteran las cifras. Cookies/sesiones solo en memoria. |
| Navegador docente, después de capturar la base | Una fila de libro activo queda en 80,00 provisional; edición de observación sin JS; una presencia cambia a ausencia justificada con motivo ficticio. Un POST 101 se rechaza y no persiste. Ningún cierre ni inasistencia injustificada nuevos. Finanzas conserva 2.764/86/2.678. |
| Navegador Secretaría, servidor regenerado | Cobros 12,60 + 1,00 = 13,60; reenvío devuelve mismo recibo y el intento 9.999 se rechaza. Ingreso 2.777,60 y resultado 2.691,60; egreso 86. Se registra/edita un alumno ficticio adicional sin matrícula: ciclo parcialmente cerrado bloquea la matrícula y no crea obligaciones. |
| Nuevo test F8.6, transacción de prueba aparte | Seis cursos activos, una matrícula/seis obligaciones por 120; beca 10, compromiso 10, cobro 100 y aporte recibido 10. Saldo final 0; ingresos 110, egresos 0. Nota provisional 80 → cierre APROBADA → corrección 69,99/REPROBADA_ACADEMICAMENTE con aprobación de Dirección. No cambian caja, recibo ni totales financieros al corregir. |

No se presenta el estado modificado de esos procesos como el escenario inicial. Cada
servidor conserva únicamente memoria; al detenerlo se descartan las operaciones.
No se cambia el generador, el calendario institucional ni la regla de seis cursos.

## Período, stock y fecha

El navegador usa el reloj actual después de generar el escenario. La referencia del
generador es 2026-11-22; la ejecución de auditoría es 2026-11-25. Los informes por defecto
pueden mostrar solo el mes, por ejemplo ingreso USD 300, sin contradecir el acumulado
USD 2.764. Para verificar este último se consultó `?desde=&hasta=`. Saldo, cobertura y
compromisos son conceptos distintos, no componentes adicionales del resultado del período.

La solvencia del portal sigue siendo `financiero.consultas.solvente`, que usa la lectura
canónica Django. El SQL histórico tiene otra implementación: su armonización y las
vistas dependientes permanecen como requisito previo al despliegue, no como validación F8.
