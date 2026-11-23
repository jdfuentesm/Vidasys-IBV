# F8.1 — Sistema visual y navegación general

Base: `c2729286465c2036b3ae389a892344f554316233`, rama
`semana-9-rutas-calificaciones`. Entrega de presentación: sistema visual compartido,
navegación y componentes. Sin cambios en modelos, migraciones, servicios, permisos,
solvencia, contratos de formularios/rutas o estructura de datos de reportes.

## Auditoría y decisiones

Se revisaron `core/aplicacion.html`, el sidebar y dashboard, herencia de bases de
estudiantes/usuarios/Finanzas/Reportes/portal, estilos institucionales y de módulos,
JavaScript de navegación, controles reales de acceso y pruebas. Se contrastó con
`docs/backlog/F8_ui_ux.md` y las evidencias de F7.1.

Hallazgos tratados:

- El encabezado ocupaba varias filas en móvil; el logotipo y sus márgenes desplazaban
  contenido. Se compacta sin recortar, alterar ni sustituir los archivos originales.
- Inicio presentaba prácticamente el catálogo de funciones. Ahora ofrece como máximo
  tres tareas prioritarias y mantiene las secundarias en «Otras tareas disponibles».
- El menú no encontraba con claridad becas, caja, convenios o solicitudes del maestro.
  Se agrupan accesos existentes; se conservan sus validaciones en servidor.
- La selección activa dependía de coincidencias parciales del nombre de ruta: podía
  confundir reportes financieros con cobros o matrícula con estudiantes. Se explicita
  el destino por nombre/prefijo, con un enlace activo en el menú principal.
- Finanzas repetía siete enlaces al inicio; se sustituyen por contexto de sección y
  «Cambiar de sección», reutilizando el mismo listado del sidebar.
- F7 mostraba ocho reportes y el detalle técnico de cálculo de inmediato. La elección
  queda en «Elegir reporte financiero» y los criterios en una ayuda nativa accesible.
  Los filtros aplicados, período/saldo actual, base de efectivo, avisos, cifras y acciones
  permanecen visibles; impresión conserva los criterios íntegros.

Se conserva la información operativa necesaria. Las ayudas no contienen errores ni
advertencias de integridad escondidas. El aviso de padrinazgos por revisar se presenta
como advertencia: el texto mantiene explícitamente la protección hasta resolución.

## Identidad y tokens

`static/css/sistema_visual.css` se carga después de los estilos existentes. Es una capa
compartida con alias para componentes antiguos: evita reescribir pantallas de dominio
antes de F8.2–F8.6. Los estilos específicos del libro y de operaciones siguen funcionando.
La retirada gradual de CSS legado queda pendiente, con pruebas de cada módulo.

| Elemento | Definición |
| --- | --- |
| Marca principal/secundaria | `static/img/vidasys.png` y `static/img/logo.png`, originales intactos, proporciones automáticas |
| Azul institucional / marino | `--ui-azul: #1765A1` / `--ui-marino: #102C50` |
| Acento institucional | `--ui-acento: #E21D2B`; no se usa como único significado de estado |
| Fondo / superficie | `#F3F6FA` / `#FFFFFF` |
| Texto / secundario | `#24364B` / `#53657A` |
| Éxito | `#21643E` sobre `#EDF7F0` |
| Error | `#982C38` sobre `#FFF1F2` |
| Advertencia | `#79520A` sobre `#FFF6DF` |
| Tipografía | Sistema/Segoe UI, sin descarga externa; base 16 px y línea 1,5; títulos 24–32 px |
| Espaciado | Tokens 4, 8, 12, 16, 24 y 32 px |
| Controles | Altura mínima 44 px, etiquetas visibles, foco de 3 px |
| Tarjetas / campos | Radio 12 / 8 px, borde claro, sin sombras dominantes |
| Números | Cifras tabulares para tablas, listas de importes y campos numéricos; formatos monetarios existentes intactos |

Se comprobaron 12 pares de contraste: al menos 4,5:1 para texto normal y 3:1 para foco/
borde de campo. El contraste se calcula sobre los pares definidos, no certifica cada
píxel o todas las combinaciones históricas de los módulos. Estados conservan sus etiquetas
textuales; iconos decorativos están ocultos a lectores de pantalla.

## Componentes reutilizables

| Pieza | Archivo o clase | Uso y contrato |
| --- | --- | --- |
| Modelo de navegación de presentación | `core/templatetags/navegacion.py` | Sin consultas ni concesión de permisos; refleja rutas existentes, tareas, grupos y selección actual |
| Enlace de menú | `core/componentes/enlace_menu.html` | URL, icono y título; `aria-current` según el destino |
| Encabezado de página | `core/componentes/encabezado_pagina.html` | Sección, un h1 y bajada breve; aplicado al inicio |
| Tarjeta de tarea | `core/componentes/tarjeta_tarea.html` | Un único enlace con título y descripción; aplicada al inicio |
| Aviso | `core/componentes/aviso.html` | Contenido escapado; errores con `role=alert`, confirmación/información con `role=status` |
| Ayuda ampliable | `core/componentes/ayuda.html` | `<details>/<summary>`; sin necesidad de JS, criterios completos al imprimir |
| Selector de sección | `core/componentes/menu_seccion.html` | Contexto y enlaces del mismo grupo; no cambia formularios ni filtros |
| Botones | `.ui-boton`, `.ui-boton--secundario`, aliases `.est-boton` y botones existentes | Tamaño, contraste, foco y estados uniformes; ningún cambio en tipo/name/value |
| Paneles | `.ui-panel`, `.panel-curso`, `.acceso-tarjeta` | Superficie, radio, borde y espaciado |
| Formularios | Estilos de label/input/select/textarea, `aria-invalid`, `.errorlist` | Conservan widgets, valores, campos ocultos, errores y CSRF originales |
| Estados | `.ui-estado` y aliases `.estado--*` | Color de apoyo a etiqueta textual; sin recalcular estado |
| Tabla base | `.ui-tabla` y numerales tabulares compartidos | Clase disponible para futuras adopciones; no se reestructura el libro ni sus columnas |

En las rutas de plantilla los componentes están bajo `templates/`. Ejemplo para una
ayuda de presentación, con texto escapado y sin mover advertencias de integridad:

```django
{% include 'core/componentes/ayuda.html' with titulo='Más información' texto=explicacion %}
```

No hay nueva tecnología, librería, fuente ni iconografía externa. Se reutilizan los SVG
institucionales existentes. El menú de presentación debe revisarse junto con las pruebas
si cambian autorizaciones en futuras entregas; los servicios siguen siendo autoridad.

## Matriz de navegación por rol

| Rol | Tareas de inicio | Navegación y otros accesos |
| --- | --- | --- |
| Secretaría | Estudiantes, Matrículas, Cuentas y cobros | Inicio, Estudiantes, Matrículas; Finanzas y Reportes institucionales. Sin Usuarios ni F7 consolidado ni decisiones de Dirección. |
| Directora | Solicitudes académicas, Reportes financieros, Estudiantes | Inicio, Estudiantes, Matrículas; Dirección académica (solicitudes y extraordinarias), Finanzas y ambos centros de Reportes. |
| Administración | Cuentas y cobros, Reportes financieros, Usuarios y accesos | Inicio, Estudiantes, Matrículas, Usuarios; Finanzas y ambos centros de Reportes. Sin autorización académica exclusiva de Dirección. |
| Maestro | Mis cursos | Inicio, Mis cursos, Mis solicitudes, Reportes académicos. Conserva contexto del curso y sus cuatro accesos de asistencia/notas/programación/cierre. |
| Estudiante | Portal existente | Inicio, Mis materias, Mi cuenta. El servidor conserva el control financiero para consultar el expediente académico; no se calcula solvencia en el menú. |
| Pastor Principal | Estado vacío honesto | Solo Inicio y salida de sesión; ningún módulo financiero añadido. |

Finanzas tiene siete destinos: cuentas/cobros, caja/cierres, ingresos/egresos, becas,
convenios, donaciones/padrinazgos y anulaciones de pagos. Son accesos de consulta/operación
existentes para Secretaría, Dirección y Administración; los botones y servicios de resolución
mantienen el rol autorizado. Categorías y calendario siguen en sus pantallas actuales.

El sidebar incluye 14 enlaces para Dirección, 13 para Administración, 11 para Secretaría,
4 para Maestro, 3 para Estudiante y 1 para Pastor, agrupados para no desplegarlos todos
simultáneamente. En el inicio los grupos están plegados; en una sección se abre el grupo
actual. La selección de estudiante también reconoce sus propios recibos y convenios.

Que el estudiante tenga una entrada a «Mis materias» no elude la solvencia: la consulta
sigue devolviendo el mensaje de restricción cuando corresponde. La presentación condicional
más detallada del portal se revisará en su etapa posterior, sin crear una segunda regla.

## Accesibilidad y adaptación

- Encabezado compacto con logotipos, usuario, rol, salida directa y botón de menú móvil.
- En escritorio, sidebar lateral; hasta 1000 px, menú en el flujo, sin cubrir formularios.
- Al abrir con teclado, foco al primer enlace; Escape cierra y devuelve foco al botón.
  Al cambiar entre móvil y escritorio se conserva un destino de foco visible, incluso
  cuando el navegador desenfoca automáticamente un control oculto por media query.
- Botón con `aria-controls/aria-expanded`; enlaces reales, grupos nativos plegables,
  salto a contenido y main enfocable. Sin JavaScript el menú queda visible y las secciones
  funcionan mediante controles HTML nativos; no se depende de un botón sin funcionalidad.
- Movimiento reducido respetado. Sin trampas de foco, bloqueo de scroll ni modal de navegación.
- Ayudas de F7 plegadas por defecto, abiertas en la vista imprimible. `beforeprint` abre
  sus criterios y `afterprint` restaura el estado elegido. Los filtros siguen visibles.

No es una certificación WCAG ni una prueba con usuarios o lectores de pantalla reales.
Se verificó semántica, foco, teclado, contraste definido, tamaño y destinos mediante pruebas.
Las tablas de dominio con desplazamiento interno conservan ese comportamiento hasta su etapa.

## Validaciones

- **636 pruebas aprobadas**: 620 casos existentes conservados y 16 nuevos. En
  `core/test_frontend.py` se actualizó la expectativa del orden/enlaces del menú para
  la nueva organización; se conservan todos sus casos y comprobaciones de campos/permisos.
- Las nuevas pruebas abren los destinos con cada rol, verifican prioridades/alternativas,
  selección activa sin coincidencias incorrectas, semántica, cuentas inactivas, ausencia
  de consultas del constructor, contenido escapado y contratos de filtros/formularios.
- Django check y migraciones sin cambios; `git diff --check` correcto. Servicios, modelos,
  rutas, SQL, formularios Python, cálculos y logotipos intactos.
- Simulación F7.1, semilla **711**, referencia **2026-11-22**, 40 estudiantes y 240 obligaciones,
  exclusivamente SQLite en memoria. La suite vuelve a comprobar las cifras independientes.
- **114 pantallas** en 390/768/1366 px sin desbordamiento exterior; las tablas con scroll
  interno no se consideran corregidas. CSV, filtros, PDF y acceso por rol preservados.
- **199 controles de navegador**, incluidos 46 destinos por rol; 320 px adicional en
  los inicios y menú abierto/cerrado, teclado, Escape, grupos, salto, cambio de tamaño,
  restauración del foco, ayudas/impresión y recorrido sin JavaScript.
- **12 pares de contraste** verificados y evidencias antes/después con datos ficticios.
  No se guardan contraseñas, cookies ni documentos financieros reales.

[Antes/después, matriz de enlaces y controles](../evidencias/F81/README.md).
Los datos antes se sirvieron desde una exportación independiente del commit base; después
se utilizó el checkout de trabajo. Ambas instancias generaron F7.1 en memoria con la misma
semilla/fecha; nunca se aplicó el stash ni se restauraron archivos sobre el árbol principal.

## Recorrido manual condensado

Con los archivos disponibles en su checkout y el entorno virtual existente activo:

```powershell
$env:PYTHONUTF8 = '1'
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22
```

Abrir `http://127.0.0.1:8000/login/`, usar la contraseña temporal de esa ejecución. Si otro
ensayo ocupa el puerto, detenerlo antes. No se inicia Django en otro proceso ni se migran
bases persistentes. El commit F8.1 será local hasta autorizar su push; Windows no puede
obtenerlo por pull antes de esa publicación.

1. Directora: comprobar las tres tareas y el aviso de padrinazgo por revisar; abrir
   «Otras tareas». Abrir Finanzas, cambiar de sección y volver al inicio.
2. Reportes financieros: elegir un reporte, aplicar filtros, abrir criterios, descargar
   CSV e imprimir. El resultado de todo el escenario continúa siendo USD 2.678,00.
3. Secretaría: acceder a matrícula y cobros; confirmar que no aparezcan Usuarios o F7.
4. Administración: comprobar usuarios y reportes; no debe aparecer autorización académica.
5. Maestro: Mis cursos, contexto de un curso y Mis solicitudes; sin finanzas internas.
6. Estudiante: materias y cuenta; con insolvencia conserva la restricción y el acceso a su
   cuenta. Pastor mantiene el estado sin módulos habilitados.
7. Móvil/tableta: abrir menú con teclado, recorrer grupos, Escape, salida y cambio de
   orientación. Desactivar JavaScript y comprobar navegación nativa. Verificar impresión.

El lanzador básico y el integral F7.1 permanecen sin modificaciones. La simulación se
elimina al detener el proceso. El stash original y ZIP se conservan íntegros.

## Pendientes y límites

- F8.2–F8.6 sin implementar: formularios, totales dinámicos, libro docente compacto,
  bandeja unificada, portal y reducción del detalle largo de reportes. Los estilos base
  no sustituyen esos rediseños ni corrigen sus reglas o procesos.
- Cuentas con 25 registros aún requiere mucho scroll; libro docente conserva tabla
  horizontal. No se oculta información para reducir artificialmente su tamaño.
- Pruebas de comprensión con usuarios, lectores de pantalla reales y otros navegadores.
- Migración gradual de CSS específico hacia tokens y componentes sin duplicaciones de dominio.
- Siguen obligatorias la unificación de solvencia Django/SQL y la validación de restricciones,
  transacciones y concurrencia en PostgreSQL aislado antes de desplegar.
- Sigue pendiente el servicio formal para declarar convenios INCUMPLIDO. No se implementa aquí.

No se accedió a Neon, ejecutaron migraciones persistentes, modificó main ni se desplegó.
Commit local autorizado tras validación; no hacer push sin autorización.
