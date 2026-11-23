# F8 — Backlog de UI/UX institucional (sin implementar F8)

Objetivo futuro: usuarios con conocimientos tecnológicos básicos puedan completar sus
operaciones sin asistencia, conservando la identidad institucional y los permisos.
Este archivo registra deuda; no autoriza ni implementa un rediseño integral.

| Prioridad | Trabajo futuro | Criterio verificable |
| --- | --- | --- |
| Alta | Navegación y tareas prioritarias por rol | Dirección, maestro y estudiante identifican desde su inicio el siguiente paso de su flujo; sin enlaces no autorizados. |
| Alta | Bandeja de Dirección unificada y paginada | Filtrar pendientes, comparar consecuencias, confirmar y consultar historial sin recorrer módulos diferentes. |
| Alta | Formularios amigables en F1–F5 | Secciones breves, valores precargados, estados claros y errores que indiquen cómo resolverlos. |
| Alta | Totales dinámicos en cobros, becas, convenios y egresos | Mostrar total, saldo y diferencias antes de confirmar; servidor sigue siendo autoridad e idempotencia permanece. |
| Alta | Portal estudiantil comprensible | Mostrar saldo financiero, saldo a cargo, cobertura y notificaciones sin información privada de terceros. |
| Media | Búsqueda asistida de donantes/estudiantes en formularios largos | Selección por nombre, resultados paginados; sin solicitar identificadores internos. |
| Media | Formularios condicionales de resolución | Mostrar únicamente fecha, nuevo padrino o beca según la acción, sin debilitar validaciones del servidor. |
| Media | Accesibilidad y pruebas con usuarios | Navegación con teclado, foco después de errores, lectores de pantalla y flujo completo en 390/768/1366 px. |
| Media | Paginación avanzada y optimización de consultas | Historiales extensos y cálculos con muchos beneficiarios no cargan todos los registros a la vez. |

F6 ya incorpora, dentro de su alcance: búsqueda por nombre, selección sin IDs manuales,
secciones, cálculo orientativo dinámico, selección automática del padrino de un compromiso,
confirmaciones de Dirección, mensajes al estudiante y pantallas responsivas. No se rediseñan
los módulos anteriores. Permanecen pendientes las mejoras integrales de esta tabla.

## Actualización tras F7

F7 incorpora exclusivamente su centro de consulta para Dirección/Administración:
indicadores con enlaces, criterios visibles, filtros, gráficos etiquetados, detalle adaptable,
CSV e impresión. No resuelve la navegación ni los formularios operativos de F1–F6.

| Prioridad | Trabajo futuro | Criterio verificable |
| --- | --- | --- |
| Alta | Pruebas de comprensión de reportes con Dirección | Distingue resultado del período, saldo actual, compromiso y efectivo retenido sin asistencia. |
| Media | Navegación compacta y selección de reportes favoritos por rol | Accede a sus consultas frecuentes en móvil con menos desplazamiento, sin ampliar permisos. |
| Media | Grandes volúmenes en F7 | Medir en PostgreSQL aislado y reducir memoria/latencia de totales y exportaciones sin perder exactitud ni snapshot. |
| Media | Integrar bandeja operativa y reportes | Enlaces de ida y vuelta conservan filtros y contexto sin habilitar decisiones desde GET. |

La unificación definitiva de solvencia Django/SQL y la validación PostgreSQL son requisitos
de integración previos al despliegue, no tareas cosméticas que puedan posponerse en F8.
