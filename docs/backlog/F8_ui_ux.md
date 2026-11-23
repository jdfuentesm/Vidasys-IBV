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

## Hallazgos comprobados en la simulación integral F7.1

Datos ficticios: 40 estudiantes, 240 obligaciones, 132 pagos. Chromium en 390/768/1366 px;
114 pantallas revisadas. Sin desbordamiento del documento; sí hay desplazamiento interno
obligatorio en el libro docente. No se hicieron entrevistas ni pruebas de comprensión con
usuarios reales. Estos hallazgos técnicos no autorizan modificar las reglas institucionales.

| Prioridad | Evidencia y problema observado | Trabajo futuro y aceptación |
| --- | --- | --- |
| Alta | Libro docente: 20 estudiantes; en móvil el contenedor mide 359 px y su tabla 2.192 px. Estado académico y nota final quedan alejados de la identidad. | Presentar identidad, nota y estado juntos; consulta individual/por componentes en móvil, sin perder edición por lote en escritorio. Mantener cierre y autorización excepcional. |
| Alta | Libro de curso cerrado conserva el texto «Escriba en las casillas»; muestra «Revisar corrección excepcional» también en filas cuya inasistencia impide ese trámite. El servidor sí lo bloquea. | Mensajes y acciones acordes al estado; explicar por qué una corrección no está habilitada y distinguir lectura de edición. |
| Alta | Cobro ordinario de SIM-017: varios importes por obligación y sin suma dinámica visible; el único JS financiero es el botón de impresión. | Mostrar importe total, saldo de cada obligación y confirmación comprensible antes de emitir; servidor conserva toda validación e idempotencia. |
| Alta | Cuentas F7: con 25 registros la página móvil mide 32.712 px de alto; no hay desbordamiento horizontal, pero exige mucho desplazamiento hasta paginar. | Resumen compacto con detalle desplegable y paginación accesible sin recorrer todas las fichas. Mantener todos los conceptos y controles de conciliación. |
| Media | Panel F7 en móvil: ocho accesos y criterios ocupan varias pantallas antes de los indicadores. | Navegación compacta y acceso directo a indicadores prioritarios, con filtros/criterios siempre identificables. |
| Media | Nombres completos de curso quedan truncados en el selector móvil del maestro. | Mostrar materia/nivel/estado con etiquetas breves y detalle accesible sin depender del desplegable nativo. |
| Media | Desde pendientes del panel se pasa por Auditoría y luego por el expediente del módulo para resolver; las bandejas siguen separadas. | Conservar permisos, aportar contexto y retorno a filtros; estudiar bandeja unificada ya prevista, sin aprobar desde GET. |

[Evidencias y medidas](../evidencias/F71/README.md). Los reportes F7 respondieron sin errores
en este volumen; sus tiempos locales no certifican rendimiento ni concurrencia PostgreSQL.
No se implementó ninguno de los rediseños de esta tabla durante F7.1.
