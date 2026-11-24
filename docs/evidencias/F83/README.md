# F8.3 — Evidencias de Secretaría y operaciones

Base antes: `51511119aa0d24991b5bda9dcae0b92a5f992348`, exportada con `git archive`
a un directorio temporal independiente. Después: F8.3. Mismo lanzador sin modificar,
semilla **711**, referencia **2026-11-22**, Chromium, 390/768/1366 × 900 px. Sin información
personal real, contraseñas, cookies ni bases persistentes en las evidencias.

## Resultados

- [706 pruebas](pruebas.txt): 678 anteriores conservadas sin modificar sus casos y 28 nuevas.
- [Conciliación inicial](simulacion_inicial.json): antes/después con los mismos conteos y
  esperados. 40 estudiantes, 240 obligaciones, 132 pagos; ingresos USD 2.764, egresos USD 86,
  resultado USD 2.678, saldo USD 1.952. Validación CONCILIADO antes de operaciones nuevas.
- [60 pantallas y operaciones de Secretaría](operaciones_navegador.json): registro, edición,
  selección buscable conservando el valor, formulario de matrícula y bloqueo por cursos
  finalizados, pago con revisión sin POST prematuro, error con valor/foco conservados,
  reenvío del mismo recibo y cobro sin JS. Sin errores JavaScript ni desbordamiento exterior.
- [126 pantallas de regresión por rol](regresion_navegador.json): Dirección, Administración,
  Secretaría, Maestro, Estudiante, cobertura F6 e insolvencia, Pastor; 390/768/1366 px,
  HTTP esperado y sin desbordamiento exterior. F7/bandeja/Usuarios continúan restringidos.
- Dos cobros ficticios adicionales: **USD 12,60 con JS + USD 1,00 sin JS**. El primer
  reenvío conserva el mismo recibo. Comprobación independiente en F7 después: ingresos
  **USD 2.777,60**, egresos **USD 86**, resultado **USD 2.691,60**. Registrar/editar un
  estudiante y rechazar una matrícula no agregan ingresos ni obligaciones.
- [Recibo PDF ficticio](recibo-ficticio.pdf), [confirmación móvil](confirmacion-390.png)
  y [error con importe preservado](error-390.png). Impresión utiliza el recibo original.
- En fixtures SQLite: matrícula válida crea una matrícula, seis inscripciones y seis
  obligaciones por USD 120; repetición no duplica. Casos con excedente, parcial de matrícula,
  beca parcial, padrinazgo, convenio, caja cerrada, CSRF, permisos y rollback conservados.

## Medidas honestas de desplazamiento y pasos

Comparación sin realizar pagos todavía, mismas rutas y datos iniciales. Altura total del
documento en 390 px; [todos los anchos y medidas](comparacion.json),
[antes](medidas-antes.json), [después](medidas-despues.json).

| Pantalla móvil | Antes px | Después px | Observación |
| --- | ---: | ---: | --- |
| Inicio Secretaría | 1.162 | 1.113 | Tres prioridades, registro directo y otras operaciones agrupadas. |
| Estudiantes (20 por página) | 4.870 | 3.976 | 18,36 % menos altura; paginación también arriba. |
| Expediente SIM-017 | 2.231 | 1.916 | 14,12 % menos altura; contacto plegable y solvencia visible. |
| Matrícula SIM-017 | 1.122 | 1.469 | Aumenta al incorporar cursos/estados y calendario antes de confirmar. |
| Cobro SIM-017 | 1.495 | 2.694 | Aumenta al incorporar saldos, condiciones y resumen; no se reclama reducción. |

Inicio → registro nuevo: antes dos enlaces (Estudiantes → Registrar), ahora uno.
Recibo → expediente: antes dos enlaces (Cuenta → Expediente), ahora uno. Cobrar con JS
incorpora un paso deliberado de revisión antes del POST; no se presenta como reducción de
clics. Sin JS se conserva la confirmación directa del formulario original. La mejora del
cobro es la información disponible antes de emitir, no una página más corta. Validar este
compromiso con personas reales; todos los campos monetarios permanecen accesibles.

## Antes/después

| Flujo | Móvil | Tableta | Escritorio |
| --- | --- | --- | --- |
| Inicio | [Antes](antes-inicio-390.png) / [Después](despues-inicio-390.png) | [Antes](antes-inicio-768.png) / [Después](despues-inicio-768.png) | [Antes](antes-inicio-1366.png) / [Después](despues-inicio-1366.png) |
| Estudiantes | [Antes](antes-estudiantes-390.png) / [Después](despues-estudiantes-390.png) | [Antes](antes-estudiantes-768.png) / [Después](despues-estudiantes-768.png) | [Antes](antes-estudiantes-1366.png) / [Después](despues-estudiantes-1366.png) |
| Expediente | [Antes](antes-expediente-390.png) / [Después](despues-expediente-390.png) | [Antes](antes-expediente-768.png) / [Después](despues-expediente-768.png) | [Antes](antes-expediente-1366.png) / [Después](despues-expediente-1366.png) |
| Matrícula | [Antes](antes-matricula-390.png) / [Después](despues-matricula-390.png) | [Antes](antes-matricula-768.png) / [Después](despues-matricula-768.png) | [Antes](antes-matricula-1366.png) / [Después](despues-matricula-1366.png) |
| Pago | [Antes](antes-pago-390.png) / [Después](despues-pago-390.png) | [Antes](antes-pago-768.png) / [Después](despues-pago-768.png) | [Antes](antes-pago-1366.png) / [Después](despues-pago-1366.png) |

## Límites

F7.1 conserva tres cursos finalizados en **cada** ciclo. Por la regla existente, una
matrícula nueva en cualquiera se rechaza. La prueba de navegador verifica ese bloqueo y la
conservación de valores, no simula un éxito. El éxito se prueba con seis cursos activos en
SQLite aislado. Para ensayarlo manualmente hace falta un ciclo adicional preparado mediante
la administración existente; no se reabren cursos ni se modifica la simulación determinista.

No son entrevistas, pruebas de comprensión, ensayo de lector de pantalla real ni validación
PostgreSQL/concurrencia. El lector financiero SQLite de ensayo no certifica unificación SQL
con producción. Las lecturas nuevas se prueban exclusivamente en memoria. No se certifica
una conexión física LAN nueva; el lanzador y sus pruebas originales se conservan.

[Inventario, permisos, fuentes y recorrido Windows/móvil](../../frontend/F83_secretaria_operaciones.md).
F8.4–F8.6 sin implementar. Siguen PostgreSQL aislado, solvencia Django/SQL y convenios INCUMPLIDO.
