# F7.1 — Evidencias con datos totalmente ficticios

Semilla 711, referencia **2026-11-22** (El Salvador). No hay información personal real.
Los nombres incluyen «Ficticio/Ensayo» y los correos son `example.test`.
No se incluyen contraseñas, hashes de autenticación, cookies, recibos privados ni bases.

- [Resumen, controles independientes y tiempos de los ocho reportes](resultado_simulacion.json).
- [114 pantallas y tiempos HTTP](navegador.json): roles institucionales y estudiantes,
  390/768/1366 px; todas las consultas esperadas HTTP 200, sin desbordamiento exterior.
- [Medidas UX](metricas_ux.json): scroll vertical de Cuentas y ancho interno del libro docente.
- Panel: [escritorio](panel-1366.png), [tableta](panel-768.png), [celular](panel-390.png).
- [Cuentas: detalle móvil](cuentas-detalle-390.png).
- [Cobro de Secretaría en móvil](secretaria-390.png).
- [Libro docente en móvil](libro-detalle-390.png).
- [Portal de estudiante con padrinazgo](padrinazgo-390.png).

Se inició sesión realmente mediante el formulario y CSRF del navegador con cada cuenta
representativa. Se verificaron descarga CSV y generación PDF del reporte completo, acceso
académico del estudiante con cobertura F6 y rechazo del insolvente; exportaciones F7
rechazadas para Secretaría, Maestro, Estudiante y Pastor. No se alteraron registros mediante
la navegación visual. Los datos fueron creados por servicios antes de abrir el navegador.

Los tiempos HTTP son navegación local con Chromium, incluyendo red/render inicial;
las mediciones del JSON de simulación corresponden al constructor de datos en Python.
No compararlos como si fueran la misma métrica. Son observaciones locales, no un SLA ni
un ensayo de producción. El informe incluye cantidades, fuentes y limitaciones en
[el manual F7.1](../../financiero/simulacion_integral_F71.md).
