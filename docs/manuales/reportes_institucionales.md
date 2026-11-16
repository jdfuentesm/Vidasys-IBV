# Reportes institucionales

Base `209b196`, rama `semana-9-rutas-calificaciones`. Sin commit ni push.
El módulo reportes anterior estaba vacío: sin rutas, consultas ni permisos implementados.
No se modificaron sus modelos ni se añadieron tablas.

## Recorrido

Inicio / sidebar **Reportes institucionales** → seleccionar reporte → aplicar filtros →
consultar tabla/totales → exportar CSV o abrir la vista imprimible para guardar PDF.
La pantalla pagina de 50 filas en 50; CSV e impresión incluyen todas las coincidencias,
con los mismos filtros y autorización. No se guardan archivos ni reportes históricos en BD.
Los resultados provienen exclusivamente de los registros existentes; los datos ficticios
se limitan a las pruebas y no son valores de reemplazo en las consultas.

Se ofrecen ocho reportes:

1. Estudiantes matriculados por ciclo (fecha de matrícula).
2. Materias y estudiantes inscritos (fecha de inscripción).
3. Calificaciones por materia/ciclo (fecha de matrícula de la inscripción).
4. Asistencia por curso/estudiante (fecha de la sesión).
5. Estado académico de inscripciones (fecha de matrícula de la inscripción).
6. Pagos recibidos por período (fecha local del pago).
7. Obligaciones pendientes/saldos (vencimiento de la obligación y saldo actual).
8. Resumen financiero (pagos/ingresos por registro, obligaciones por vencimiento).

Los filtros son ciclo, curso, estudiante, desde y hasta, con validación de fechas e
incompatibilidad curso/ciclo. Los filtros de fecha son inclusivos. El uso de la fecha
se indica en cada pantalla/exportación: no se presenta un saldo actual como corte histórico.
Se muestran estados vacíos, conteos y totales calculados de las filas reales, sin porcentajes
inventados. Se reutilizan el tema de encabezado blanco/sidebar azul y estilos institucionales,
sin rediseñar pantallas existentes.

## Permisos

| Rol | Reportes autorizados |
| --- | --- |
| ADMINISTRADOR / DIRECTORA | Los ocho reportes |
| SECRETARIA | Matrículas, inscripciones (operación de matrícula), pagos, pendientes y resumen financiero |
| MAESTRO | Inscripciones, calificaciones, asistencia y estados, solo de cursos cuyo maestro está vinculado a su usuario |
| ESTUDIANTE / PASTOR_PRINCIPAL | Ninguno |

Las vistas, exportaciones y constructor de datos comprueban el rol en el servidor. Las
cuentas deben estar activas. Los maestros solo reciben opciones de sus propios cursos,
ciclos y estudiantes en los filtros. Manipular un identificador ajeno produce HTTP 400
sin resultados; pedir un reporte no autorizado devuelve HTTP 403, también para CSV/impresión.
Los POST se rechazan: el módulo es de solo lectura y no genera ni modifica matrículas,
asistencias, notas, pagos, obligaciones o estados. Las respuestas son privadas/no-store.

## Reglas reutilizadas

- Matrículas, cursos e inscripciones se consultan directamente de sus modelos. Las notas
  finales y estados de Calificacion se leen almacenados; no se aplica otra fórmula.
- Asistencia muestra los registros y etiquetas existentes, sin convertir un registro
  ausente en falta ni producir porcentajes. Los estados de inscripción se conservan
  literalmente. No hay un estado «incompleto» uniforme en el modelo: no se inventa ni
  se deriva de una calificación faltante.
- Los saldos usan `financiero.consultas.importes`: monto final/descuento existente, menos
  pagos REGISTRADO y donaciones RECIBIDA, con piso cero. Las obligaciones ANULADA se
  excluyen de cuentas por cobrar; las PAGADA con saldo real remanente no se ocultan solo
  por la etiqueta almacenada.
- La solvencia usa `financiero.consultas.solvente` y la función SQL existente, incluyendo
  las excepciones y cuotas de convenios. Se muestra solvencia global actual del estudiante,
  no una deducción a partir de la deuda del ciclo filtrado. La cobertura ACTIVO/CUMPLIDO se
  informa, pero no sustituye la comprobación de solvencia ni borra saldo.
- Un pago se lista una vez por encabezado, sin multiplicarlo por los detalles. Sin filtros
  de ciclo/curso, se informa monto_total. Al filtrar por ciclo/curso, se suman solo las
  aplicaciones de las matrículas coincidentes y el total del recibo queda informativo;
  así un recibo aplicado a dos ciclos no se atribuye completo a ambos.
- El curso selecciona matrículas inscritas: las obligaciones pertenecen a la matrícula,
  no a una materia. No se divide una tarifa ni se inventa un costo por curso.

### Ingresos administrativos y resumen

Ingreso y Pago son registros independientes y el modelo no tiene una relación de
conciliación entre ellos. El resumen informa pagos registrados y saldo por cobrar por
separado. Con alcance global también muestra Ingreso REGISTRADO, excluyendo ANULADO,
pero no suma esa cifra con Pago para no duplicar dinero ya registrado por otra vía.
Con filtros de ciclo/curso/estudiante, los ingresos administrativos se marcan **No disponible**:
no tienen esas relaciones y no se atribuyen por nombre o referencia. Un total consolidado
futuro requerirá definir una conciliación explícita; esta etapa no inventa una.

## Exportaciones

CSV UTF-8 con BOM, título, filtros, columnas, resultados y totales. Se neutralizan prefijos
de fórmula en datos de texto para no ejecutar contenido como fórmula al abrir la hoja;
los registros de origen no cambian. Se utilizan nombres de descarga fijos por tipo de reporte.

No existe un motor PDF de servidor entre las dependencias actuales. **Vista para imprimir /
Guardar PDF** ofrece el mismo reporte autorizado, completo, con estilos A4 horizontal,
encabezados de tabla y sin sidebar/filtros al imprimir. El navegador genera el PDF; no hay
un endpoint que entregue un binario application/pdf ni se añadieron dependencias nuevas.
Se generó un PDF real con Chromium durante la comprobación visual.

## Validación indispensable

```sh
python manage.py test reportes.tests --settings=academico.test_settings --noinput
```

**6 pruebas esenciales aprobadas**: permisos por reporte/rol y formato, alcance docente y
parámetros ajenos, filtros/fechas, importes sin multiplicación por detalles y exclusión de
anulados, saldo/resumen sin consolidación ficticia, CSV seguro/impresión y lectura sin
cambios en registros académicos/financieros. Se corrigió la preparación de fechas de objetos
ficticios antes de ejecutar los seis casos; no se alteraron las reglas de modelos.

Una comprobación de integración de navegación por roles también pasó:

```sh
python manage.py test core.test_frontend.FrontendInstitucionalTests.test_menu_exacto_por_rol_sin_enlaces_ficticios --settings=academico.test_settings --noinput
```

`manage.py check --settings=academico.test_settings` y `git diff --check` correctos.
No se repitieron baterías anteriores. Todo se ejecutó con SQLite efímero y personas ficticias.
No se ejecutó manage.py migrate ni se realizaron consultas/escrituras en PostgreSQL.

Chromium/Playwright: panel → reporte de pagos → fechas → CSV descargado → PDF imprimible;
verificados escritorio 1440 px y móvil 390 px sin desbordamiento en panel, pagos, pendientes,
asistencia y calificaciones. Docente sin registros ajenos y exportación financiera HTTP 403.
Capturas/CSV/PDF de pruebas fuera del repositorio: `/workspace/artifacts/reportes/`.

## Archivos añadidos o modificados

- `reportes/catalogo.py`: catálogo y permisos comunes.
- `reportes/forms.py`: filtros y opciones limitadas por rol.
- `reportes/consultas.py`: lecturas, conteos e importes sin duplicación.
- `reportes/views.py`, `reportes/urls.py`: consulta/generación y exportación autorizada.
- `reportes/tests.py`: pruebas esenciales del módulo.
- `core/urls.py`: inclusión de rutas, sin tocar config/urls.py compartido con despliegue.
- `templates/reportes/base.html`, `panel.html`, `reporte.html`;
  `static/css/reportes.css`, `static/js/reportes.js`: presentación y vista imprimible.
- `templates/core/partials/sidebar.html`, `templates/core/dashboard.html`: navegación integrada.
- `core/test_frontend.py`: expectativas del menú actualizado.
- Este documento.

## Estado y límites

Los cambios pendientes de PostgreSQL y despliegue se conservaron íntegramente, comprobando
huellas de contenido antes/después. No forman parte de los cambios de reportes. No se
modificó main ni se hizo commit/push. No hay migraciones nuevas ni cambios de esquema.
La compatibilidad específica de estas consultas en PostgreSQL queda pendiente; no se
utilizó la base real ni la base de demostración PostgreSQL de la tarea anterior.

Los reportes son síncronos; se recomienda aplicar filtros en volúmenes elevados. No crean
instantáneas contables históricas ni reconstruyen saldos al corte. La exportación PDF es
mediante navegador y no un archivo generado por una biblioteca del servidor. Esta entrega
no constituye autorización de producción o publicación pública.
