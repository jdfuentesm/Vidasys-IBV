# Frontend institucional integrado

## Estructura y alcance

`core/aplicacion.html` es la estructura común del inicio y las pantallas académicas.
Incluye logotipo existente, identidad y rol de la sesión, cierre de sesión, menú
por rol y navegación contextual del curso. No cambia las vistas de autorización,
modelos, reglas, esquemas, matrículas, docentes ni el módulo financiero.

El usuario mostrado proviene de Usuario.get_full_name(), que actualmente devuelve
numero_usuario: no se inventa un nombre personal ni se consulta otro perfil para
suponerlo. No hay estadísticas en el dashboard. Se retiraron las cifras literales,
comparaciones, próxima clase y mensaje general de construcción.

| Rol | Menú operativo |
| --- | --- |
| SECRETARIA | Inicio, Finanzas, Estudiantes, Matricular estudiante, Reportes institucionales |
| MAESTRO | Inicio, Reportes institucionales de sus cursos, Mis cursos |
| DIRECTORA | Inicio, Finanzas (consulta), Estudiantes, Matricular estudiante, Reportes institucionales, Autorizar extraordinarias |
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

## Funciones pendientes (sin enlaces operativos)

Ya están disponibles la gestión institucional de estudiantes y usuarios, la matrícula
con obligaciones, el cobro ordinario y recibos, ocho reportes con CSV/impresión y el
portal estudiantil con controles de identidad y solvencia. Véanse los manuales de
[estudiantes](../manuales/modulo_estudiantes.md), [usuarios](../manuales/administracion_usuarios.md),
[finanzas](../manuales/modulo_financiero.md), [reportes](../manuales/reportes_institucionales.md)
y [portal](../manuales/portal_estudiante.md).

Permanecen pendientes:

- Indicadores del dashboard basados en consultas y alcance institucional acordado.
- Preparación institucional del ciclo, asignaciones docentes y operación de estados de sesiones.
- Flujos institucionales completos de becas, cuotas de convenios y anulación de pagos.
- Supervisión académica general de Dirección/Administrador distinta de las rutas
  docentes actualmente autorizadas.
- Recuperación automática de contraseñas.
- Los pendientes académicos y de validación física/concurrencia en PostgreSQL
  documentados en Asistencia y Flujo Académico conservan su alcance.

No se crean botones para módulos futuros. La presencia de modelos, SQL o páginas
Admin no implica que exista una interfaz propia para esos roles. Las futuras
estadísticas requerirán definir el alcance y consultas reales con permisos; no se
sustituyen valores desconocidos por cifras de demostración.

## Verificación aislada

```powershell
.\venv\Scripts\python.exe manage.py test core academico --settings=academico.test_settings --noinput
.\venv\Scripts\python.exe manage.py check --settings=academico.test_settings
```

Pruebas nuevas de menú para seis roles, permisos existentes, navegación compartida,
logo, estado vacío, ausencia de enlaces/cifras ficticios y nombres/IDs de controles.
Chromium usa únicamente datos ficticios con SQLite en memoria. No se consultó ni
modificó PostgreSQL. Las capturas de revisión quedan fuera del repositorio.

No se amplía la configuración financiera ni se afirma validar aquí los permisos,
CHECK, disparadores o bloqueos del PostgreSQL real. La revisión con usuarios reales
y navegadores de sus instalaciones locales queda pendiente antes de integración.
