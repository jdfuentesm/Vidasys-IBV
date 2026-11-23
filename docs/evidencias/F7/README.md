# Evidencias de F7

Chromium con datos **exclusivamente ficticios**, usando `academico.test_settings` y el
runner aislado SQLite `:memory:`. Sin Neon ni base persistente. Capturas de una misma
prueba: cobro académico USD 20, ingreso administrativo USD 30, donación general USD 10,
egreso desembolsado USD 5; resultado USD 55. Fondo de apertura USD 10, separado del resultado.
Solicitud de padrinazgo pendiente sin cobertura efectiva y egreso autorizado USD 99 sin desembolso.
No son indicadores ni operaciones reales del instituto.

- [Panel en celular, 390 px](panel-390.png).
- [Panel en tableta, 768 px](panel-768.png).
- [Panel en escritorio, 1366 px](panel-1366.png).
- [Resultado de efectivo en celular](resultados-390.png).
- [Primera página de impresión institucional](impresion-resultados.png).
- [Matriz de 48 comprobaciones](comprobaciones_navegador.json): 8 pantallas × Dirección y
  Administración × 390/768/1366 px; todas HTTP 200, sin desbordamiento horizontal.

También se verificó aplicar filtros desde móvil, descargar CSV, generar PDF mediante
impresión (menús ocultos) y rechazar CSV de Secretaría con HTTP 403. Se inspeccionaron
visualmente el panel móvil, escritorio y la salida de impresión. Los artefactos de sesión,
cookies, CSV de ensayo y el servidor temporal no forman parte del repositorio.

La prueba automatizada de navegador se ejecutó contra un servidor temporal `runserver`
sin recarga ni hilos, para conservar una única conexión SQLite en memoria. Se usaron
las fixtures institucionales de prueba, no credenciales ni registros de producción.
Las capturas no prueban concurrencia ni restricciones PostgreSQL.
