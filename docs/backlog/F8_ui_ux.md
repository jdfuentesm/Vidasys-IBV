# F8 — Backlog de UI/UX institucional

Objetivo futuro: usuarios con conocimientos tecnológicos básicos puedan completar sus
operaciones sin asistencia, conservando la identidad institucional y los permisos.
Este archivo registra deuda y entregas. F8.1 está implementada como base visual y de navegación;
F8.2 incorpora paneles y consultas compactas; F8.3 mejora Secretaría y formularios operativos.
F8.4 mejora el recorrido docente y el libro; F8.5–F8.6 siguen pendientes de autorización.
Las entradas históricas conservan su contexto y las actualizaciones posteriores indican el estado vigente.

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


## Entrega F8.1 — Sistema visual y navegación general

Implementado: tokens visuales, estilos comunes, encabezado compacto, navegación agrupada
por rol, tres prioridades como máximo en inicio, selección activa por ruta, contexto de
sección, acceso a solicitudes del maestro y ayudas técnicas plegables. Componentes nativos
con teclado, foco, Escape, alternativa sin JS e impresión completa.

Validación: 636 pruebas (620 conservadas + 16 nuevas), 114 pantallas con datos F7.1 y
199 controles de navegación/accesibilidad, 46 destinos por rol y 12 pares de contraste.
[Diseño, matriz y recorrido](../frontend/F81_sistema_visual.md) ·
[Evidencias antes/después](../evidencias/F81/README.md).

| Estado | Trabajo | Seguimiento |
| --- | --- | --- |
| Base resuelta en F8.1 | Navegación y prioridades por rol, estilo y componentes comunes | Pendiente comprobar aprendizaje con usuarios reales y lectores de pantalla. |
| Base resuelta en F8.1 | Menú financiero y selector de reportes compactos; ayuda técnica accesible | Mantener criterios, filtros y avisos críticos visibles; impresión íntegra. |
| Pendiente | Libro docente y mensajes/acciones específicos de cursos cerrados | Sigue la tabla horizontal, no se reorganizaron sus campos ni reglas. |
| Pendiente | Cobros/formularios y totales dinámicos | No se modificaron contratos, cálculos ni confirmaciones operativas. |
| Pendiente | Bandeja unificada de Dirección | Accesos mejorados; no se fusionaron modelos ni procesos de aprobación. |
| Pendiente | Portal estudiantil y presentación condicional de acceso académico | Servidor conserva solvencia; no calcular otra regla en la navegación. |
| Pendiente | Detalle compacto y paginación cómoda en reportes | Cuentas sigue midiendo 30.430 px con 25 fichas en 390 px; hace falta rediseño específico. |
| Pendiente | Reducir CSS heredado gradualmente | Adoptar tokens/aliases por módulo con regresión, sin reestructurar tablas de forma global. |

En F8.1 no se implementaron F8.2–F8.6. La unificación de solvencia Django/SQL, PostgreSQL aislado y
el servicio formal de INCUMPLIDO conservan su estado pendiente; no son cambios visuales.


## Entrega F8.2 — Dirección, Administración y reportes compactos

Implementado: panel de Dirección con fuentes académicas y solvencia canónica; panel
administrativo con período y saldos actuales separados; bandeja exclusiva de Dirección,
solo lectura, nueve tipos y enlaces a resoluciones originales; F7 con indicadores prioritarios,
reportes agrupados y desgloses ampliables; cuentas agrupadas por estudiante y paginación doble.

Validación: 678 pruebas (649 anteriores + 29 específicas), 126 pantallas en 390/768/1366 px,
sin desbordamiento exterior; 49 solicitudes únicas y sus enlaces originales; operación esencial
sin JavaScript. Cuentas: 30.430 → 7.756 px en 390 px (74,51 % menos altura), mismo escenario
F7.1 y filtros. Antes 25 obligaciones; ahora 25 estudiantes con obligaciones plegables. CSV e
impresión conservan las 240 obligaciones y las 16 columnas. No se elimina información.

[Fuentes, permisos y recorrido](../frontend/F82_direccion_administracion.md) ·
[Evidencias y límites](../evidencias/F82/README.md).

| Estado vigente | Trabajo | Seguimiento |
| --- | --- | --- |
| Base resuelta F8.2 | Inicio de Dirección y Administración | Validar comprensión y prioridades con usuarios reales; no confundir inscripciones con personas. |
| Base resuelta F8.2 | Bandeja unificada y paginada | Mantiene procesos originales y estados de origen; sin solicitud verificable de clases extraordinarias o donaciones recibidas no inventa pendientes. |
| Base resuelta F8.2 | Panel F7 y detalle compacto de cuentas | Medir grandes volúmenes; CSV/impresión completos y advertencias conservadas. |
| Pendiente F8.3–F8.6 | Formularios operativos, totales dinámicos, libro docente y portal | Sin cambios en esta entrega; requieren autorización de su fase. |
| Pendiente | Paginación en origen de historiales grandes | Hoy materializa y filtra antes de paginar; consultas acotadas no equivalen a memoria constante. Medir PostgreSQL aislado. |
| Pendiente | Pruebas de comprensión, lector de pantalla y otros navegadores | Chromium con teclado/sin JS no sustituye pruebas con personas. |
| Obligatorio antes de despliegue | Solvencia Django/SQL, restricciones, transacciones y concurrencia PostgreSQL aislado | No abordado mediante cambios visuales; no desplegar sin validación. |
| Pendiente funcional | Servicio formal para declarar convenios INCUMPLIDO | No implementado; no inferir ni cambiar el estado desde la bandeja. |

No se implementan F8.3–F8.6. Lanzadores básico, integral y LAN sin modificaciones.


## Entrega F8.3 — Secretaría y formularios operativos

Implementados: inicio de tareas de Secretaría, registro directo y secundarios agrupados;
formularios de estudiante por secciones, búsqueda/filtros originales con paginación doble,
expediente con solvencia canónica y contacto plegable; matrícula con vista de cursos/calendario;
cobro con totales orientativos en centavos, revisión progresiva y retorno directo al expediente;
componentes compartidos para becas, convenios, caja, ingresos/egresos y anulaciones.
F6 conserva sus componentes y lógica sin duplicarlos. Contratos y servicios intactos.

Validación: 706 pruebas (678 conservadas + 28 nuevas), 60 pantallas operativas y 126 de
regresión por rol; 390/768/1366 px, sin desbordamiento exterior ni errores JS. Cobros con y
sin JavaScript, reenvío del mismo recibo, datos/foco ante errores y cifras independientes.
Mismos datos iniciales F7.1; los dos cobros ficticios posteriores suman USD 13,60.

[Inventario, permisos y recorrido](../frontend/F83_secretaria_operaciones.md) ·
[Evidencias, medidas y límites](../evidencias/F83/README.md).

| Estado vigente | Trabajo | Seguimiento |
| --- | --- | --- |
| Base resuelta F8.3 | Estudiantes, matrícula y cobro | Validar aprendizaje con usuarios; sin alterar sus reglas. |
| Base resuelta F8.3 | Formularios operativos comunes | Componentes de secciones, errores con foco, teclado y búsqueda local; no rediseño integral de todos los listados/resoluciones. |
| Base resuelta F8.3 | Totales orientativos de cobro y cuotas | Servidor conserva autoridad, centavos, reserva, caja, idempotencia y transacciones. F6 conserva su resumen previo. |
| Pendiente | Compacidad del cobro y pruebas de comprensión | El cobro crece por saldos/resumen; medir con personas, sin ocultar condiciones necesarias. |
| Limitación de ensayo F7.1 | No permite nueva matrícula en sus dos ciclos parcialmente finalizados | Prueba positiva con seis cursos activos en SQLite; preparar ciclo adicional para ensayo manual. No reabrir ni modificar el generador. |
| Pendiente | Grandes selectores e historiales | Búsqueda local sobre opciones existentes; futura búsqueda remota requiere diseño/permisos y regresión. |
| Pendiente F8.4–F8.6 | Libro docente, portal y siguientes alcances | Sin implementar ni autorización implícita en F8.3. |
| Obligatorio antes de despliegue | PostgreSQL aislado y unificación solvencia Django/SQL | Restricciones, transacciones y concurrencia siguen pendientes. |
| Pendiente funcional | Servicio formal de convenios INCUMPLIDO | Sin implementar ni inferir estados desde UI. |

Sin cambios en modelos, migraciones, reglas, servicios, permisos ni lanzador LAN. Sin acceso
a Neon, migraciones persistentes o despliegue. Conservar stash y ZIP; publicación requiere autorización.


## Entrega F8.4 — Maestros y libro de calificaciones

Implementados: inicio y tarjetas con cursos propios/pendientes verificables; contexto de curso
único y catálogo de nombres completos; libro con identidad/nota/estado juntos, componentes
ampliables y un solo formulario/DOM por lote; vista previa desde servidor sin alterar estados
mostrados de filas sin editar/bloqueadas; asistencia adaptable y estados de consulta coherentes;
calendario ordinario/extraordinario y mensajes de cursos cerrados; disponibilidad de corrección
por validador original e historial de pendiente propia; retorno desde reportes al libro.

Validación: 729 pruebas (706 conservadas + 23 nuevas), 48 pantallas docentes y 126 de regresión,
390/768/1366 px, sin desbordamiento exterior ni errores JS. Operaciones con y sin JS, cambio de
resolución conservando FormData, campos únicos, errores con valores/foco y un envío ante doble
submit. Mismos datos iniciales académicos/financieros de F7.1. Sin cambios en modelos, migraciones,
formularios, servicios, permisos, reglas ni lanzador LAN.

[Inventario y recorrido](../frontend/F84_maestros_libro.md) ·
[Evidencias y mediciones](../evidencias/F84/README.md).

| Estado vigente | Trabajo | Seguimiento |
| --- | --- | --- |
| Base resuelta F8.4 | Libro docente adaptable y edición por lote | En 390 px, ancho real base 1.932–1.961 → 360 px; scroll horizontal 1.572–1.601 → 0. Misma cantidad de campos. |
| Base resuelta F8.4 | Cursos cerrados y correcciones | No confunde solo lectura con inasistencia; usa elegibilidad canónica sin reparar historia. |
| Base resuelta F8.4 | Asistencia, sesiones y reportes propios | Presentación coherente, permisos/validaciones originales; sin nuevas acciones masivas ni estados. |
| Pendiente | Comprensión/lector de pantalla y altura móvil | 20 fichas aumentan altura; índice y búsqueda no eliminan información. Medir con docentes reales antes de otra simplificación. |
| Pendiente | Elegibilidad por lotes y cursos de gran volumen | El validador original consulta por inscripción; diseñar lectura común/medir PostgreSQL sin duplicar reglas. |
| Pendiente F8.5–F8.6 | Siguientes alcances, incluido portal | No implementados ni autorizados implícitamente por F8.4. |
| Obligatorio antes de despliegue | PostgreSQL aislado, solvencia Django/SQL | Restricciones, transacciones y concurrencia; despliegue pendiente, sin acceso a Neon. |
| Pendiente funcional | Servicio formal de convenios INCUMPLIDO | Sin implementar. |

Conservar evidencias anteriores, stash y ZIP. Commit local tras validación; sin push hasta autorización.
