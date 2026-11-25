# F8.6 — Matriz de recorridos y permisos reales

Ensayo: semilla 711, referencia 2026-11-22, SQLite en memoria. Navegador Chromium a
390/768/1366 px. Los seis roles se probaron con y sin JavaScript. Una opción de menú
no concede autorización: las vistas y servicios mantienen su comprobación original.

| Rol | Recorrido y operaciones autorizadas | Límites comprobados / evidencia |
| --- | --- | --- |
| Directora | Inicio con datos reales; `/direccion/pendientes/`, filtros/historial y origen único; solicitudes académicas, becas, convenios, egresos, padrinazgos y anulaciones; reportes financieros/institucionales; estudiantes/matrícula | GET de bandeja y expediente no decide; POST en bandeja 405. Decide mediante servicios/vistas originales. No opera como docente ni se le concede cobro por ser Directora. `core/test_paneles.py`, pruebas de servicios/HTTP y navegador. |
| Secretaría | Inicio → estudiantes → búsqueda/registro/edición → expediente → matrícula; Finanzas/caja propia → cuenta → cobro → revisión JS → confirmación → recibo; solicitudes permitidas, consulta y reportes limitados | No aprueba becas/convenios/anulaciones ni accede al consolidado F7. Matrícula válida en fixture con seis cursos activos; F7.1 rechaza ciclos parcialmente cerrados. Cobro sin JS permitido con mismas validaciones. `core/test_operativa.py`, navegador Secretaría y test F8.6. |
| Administración | Inicio con período/saldo/compromisos separados; usuarios/accesos, estudiantes/matrícula; caja y operaciones permitidas; configuración de categorías y consulta/seguimiento financiero; reportes F7/auditoría | No recibe bandeja unificada ni autorización académica, becas u otras decisiones exclusivas de Dirección. Puede solicitar anulaciones propias donde está permitido, no resolverlas. `core/test_paneles.py`, tests financieros y navegación. |
| Maestro | Inicio → cursos propios → sesiones/asistencia → libro activo → cálculo servidor/lote → requisitos/cierre; consulta de cerrados → comparación y solicitud excepcional → historial propio; reportes de sus cursos | Curso ajeno 404, Dirección/finanzas 403; cerrados sin edición ordinaria. Una sola colección de campos POST al cambiar resolución. Corrección usa validador original; inasistencia no se convierte en aprobación por cambiar notas. `academico/test_presentacion_docente.py`, correcciones y navegador docente. |
| Estudiante | Portal propio → materias/componentes/asistencia autorizadas → cuenta/apoyos propios → recibo e impresión; perfiles 01 solvente, 17 insolvente y 29 con padrinazgo | Insolvente académico 403 desde servidor; recibo ajeno 404; POST a consultas 405; parámetros/formatos no cambian identidad ni abren rutas institucionales. Sin datos privados del padrino, incluidos HTML y atributos. Puede no haber recibo cuando solo existe un compromiso. `core/test_portal*` y 54 casos navegador. |
| Pastor Principal | Inicio de sesión, identificación de rol, pantalla de sesión activa y salida | Solo Inicio en menú. No hay módulo operativo propio; rutas financieras, académicas y Dirección denegadas según contratos. No se inventan capacidades. Navegación por seis roles y pruebas existentes de permisos. |

## Muestras de integración conservadas en la suite

| Riesgo / tramo | Prueba verificable |
| --- | --- |
| Alta/matrícula y seis obligaciones, reintento y rollback | `core.test_operativa.EstudiantesOperativosF83Tests`, `academico.test_flujo.FlujoAcademicoTests` |
| Beca neta de matrícula, saldos y cobro duplicado | `core.test_operativa.CobrosOperativosF83Tests` y `financiero.test_becas` (consultar nombres en el código) |
| Convenio, autorización, abono desglosado y recibo | `financiero.test_convenios.ConveniosTests.test_http_solicitud_autorizacion_abono_recibo_y_reenvio` |
| Apoyos, privacidad, recepción/desglose y reintento | `financiero.test_aportes.AportesTests` |
| GET manipulado no decide / POST en bandeja no permitido | `core.test_paneles.PanelesF82Tests` (métodos `test_get_manipulado_no_aprueba_y_post_es_rechazado`, `test_consultas_sin_escritura_y_sin_cache_publico`) |
| Libro único, lote completo/atómico, cálculo servidor | `academico.test_presentacion_docente.LibroPresentacionF84Tests` |
| Seis presencias, aprobación y corrección sin reabrir ni alterar dinero | `core.test_integracion_f86.ContinuidadInstitucionalF86Tests` |
| Corrección: 69,99/70, rechazo, reenvío, UUID ajeno, roles, rollback y bloqueos | `academico.test_correcciones.CorreccionesTests` |

Los nombres de clase indicados en esta tabla se contrastan con los archivos; la suite
completa es el comando de referencia y no depende de seleccionar manualmente esas muestras.
La comprobación física desde Windows/teléfono y la evaluación con usuarios quedan como
aceptación manual, no como resultados de Chromium en Linux.
