# Frontend institucional integrado

## Estructura y alcance

`core/aplicacion.html` es la estructura común del inicio y las pantallas académicas.
Incluye logotipo existente, identidad y rol de la sesión, cierre de sesión, menú
por rol y navegación contextual del curso. No cambia las vistas de autorización,
modelos, reglas, esquemas, matrículas, docentes ni el módulo financiero.

El usuario mostrado proviene de Usuario.get_full_name(), que actualmente devuelve
numero_usuario: no se inventa un nombre personal ni se consulta otro perfil para
suponerlo. Los paneles actuales de Dirección y Administración muestran consultas reales
(F8.2); Secretaría, Maestro y Estudiante muestran sus tareas y datos autorizados. Se
retiraron las cifras literales de demostración. Esta guía se actualiza con F8.6;
las evidencias de cada entrega conservan su fecha y alcance original.

| Rol | Menú operativo |
| --- | --- |
| SECRETARIA | Inicio, Finanzas, Estudiantes, Matricular estudiante, Reportes institucionales |
| MAESTRO | Inicio, Reportes institucionales de sus cursos, Mis cursos |
| DIRECTORA | Inicio, Pendientes de Dirección, Finanzas y resoluciones autorizadas, Estudiantes, Matrícula, Solicitudes académicas, Extraordinarias y Reportes |
| ADMINISTRADOR | Inicio, Finanzas, Estudiantes, Matricular estudiante, Usuarios y accesos, Reportes institucionales |
| ESTUDIANTE | Portal, Mis materias y resultados (según solvencia), Mi estado de cuenta y recibos propios |
| PASTOR_PRINCIPAL | Inicio; estado informativo sin módulos operativos |

Cerrar sesión está disponible en el encabezado para todos. Los accesos docentes
son por curso: asistencia, calificaciones, programación y cierre. Al cambiar de
tarea se conserva el ID del curso, no se inventa una sesión. Cada vista mantiene
sus comprobaciones actuales; Administrador no recibe privilegios de Maestro.

## Estilos, accesibilidad y formularios

`institucional.css` centraliza los componentes antes compartidos desde
calificaciones.css y agrega la estructura institucional. calificaciones.css queda
solo con estilos propios del libro. Asistencia y el flujo académico conservan sus
hojas específicas. El área autenticada no carga el CSS demostrativo del dashboard
ni dependencias CDN nuevas. El login reutiliza los estilos institucionales y muestra
el logotipo original VidaSYS y el escudo IBV, conservando POST, validaciones y CSRF.
La recuperación automática no existe: se ofrece ayuda administrativa.

El menú móvil se despliega en el flujo normal, sin tapar formularios. El botón
expone aria-expanded/aria-controls, funciona con teclado y cierra con Escape.
Sin JavaScript el menú sigue visible. La sección y tarea activas usan aria-current.
Se conserva el enlace de salto real a #contenido; no existen enlaces href="#".

Los formularios y tablas mantienen nombres, IDs, CSRF, revisiones firmadas y métodos
de envío. Los mensajes se presentan una sola vez desde la estructura compartida.
Los scripts de datos académicos no se modifican: sus advertencias y cálculos siguen
funcionando. El menú móvil no envía formularios ni deshabilita las advertencias de
cambios pendientes.

## Funciones verificadas y límites actuales

Están disponibles la gestión institucional de estudiantes y usuarios, matrícula con
obligaciones, cobro y recibos, caja, becas, convenios y sus cuotas, anulaciones,
ingresos/egresos, donaciones/padrinazgos, reportes y portal estudiantil. Las solicitudes
se resuelven por los servicios originales y solo con el rol autorizado; no toda opción
de Finanzas implica facultad de aprobación. El menú aplica la matriz por rol.

El maestro programa sesiones, gestiona sus estados permitidos, registra asistencia y
notas provisionales, finaliza cursos y solicita excepciones. Dirección resuelve las
cancelaciones elegibles y correcciones definitivas existentes. No se implementó una
reapertura general ni corrección de asistencia posterior al cierre.

Consultar las entregas [F8.2](F82_direccion_administracion.md),
[F8.3](F83_secretaria_operaciones.md), [F8.4](F84_maestros_libro.md),
[F8.5](F85_portal_estudiante.md) y la [auditoría F8.6](F86_auditoria_integral.md).
Los manuales de [estudiantes](../manuales/modulo_estudiantes.md),
[usuarios](../manuales/administracion_usuarios.md),
[finanzas](../manuales/modulo_financiero.md),
[reportes](../manuales/reportes_institucionales.md) y
[portal](../manuales/portal_estudiante.md) detallan sus contratos.

Permanecen pendientes, fuera del cierre visual:

- Preparación institucional completa de ciclos/asignaciones mediante interfaz propia.
- Supervisión académica general distinta de las rutas docentes autorizadas.
- Recuperación automática de contraseñas.
- Servicio formal para declarar convenios INCUMPLIDO.
- Unificación de solvencia Django/SQL y validación PostgreSQL de la versión completa,
  restricciones, concurrencia y despliegue; consultar el [plan F8.6](../despliegue/F86_requisitos_pendientes.md).
- Comprensión con usuarios reales, tecnologías de apoyo e historiales de gran volumen.

La existencia de un modelo, SQL o página Admin no demuestra una interfaz institucional
terminada. Los indicadores actuales proceden de consultas reales; no se sustituyen
valores desconocidos por cifras de demostración.

## Verificación aislada

```powershell
.\venv\Scripts\python.exe manage.py test --settings=academico.test_settings --noinput
.\venv\Scripts\python.exe manage.py check --settings=academico.test_settings
```

Pruebas nuevas de menú para seis roles, permisos existentes, navegación compartida,
logo, estado vacío, ausencia de enlaces/cifras ficticios y nombres/IDs de controles.
Chromium usa únicamente datos ficticios con SQLite en memoria. No se consultó ni
modificó PostgreSQL. Las capturas F8 y los resultados se conservan en `docs/evidencias/`;
F8.6 distingue evidencia histórica de las comprobaciones actuales.

No se amplía la configuración financiera ni se afirma validar aquí los permisos,
CHECK, disparadores o bloqueos del PostgreSQL real. La revisión con usuarios reales
y navegadores de sus instalaciones locales queda pendiente antes de integración.
