# Administración institucional de usuarios y accesos

Base `abbd0f3`, rama `semana-9-rutas-calificaciones`. Sin commit ni push. Se conservaron
los cambios pendientes de preparación PostgreSQL/despliegue de la tarea anterior.

## Recorrido disponible

ADMINISTRADOR → Inicio o menú **Usuarios y accesos** → buscar/filtrar → crear o editar
cuenta → vincular expediente si tiene rol ESTUDIANTE → restablecer acceso si corresponde.
El nuevo módulo usa sidebar azul marino, encabezado blanco, logo IBV y componentes
institucionales; el tema se limita a sus páginas y no rediseña los módulos anteriores.

El listado permite búsqueda por número/correo, filtros por rol/estado y paginación de 20.
No muestra claves, hashes, permisos técnicos ni datos personales de otros perfiles.
La creación y edición usan los campos existentes: numero_usuario, correo_acceso, rol y
estado_cuenta. No se inventan nombres/teléfonos en Usuario. El correo se valida como email.
Se impiden identificadores duplicados incluso por diferencias de mayúsculas y las
colisiones entre correo y número de otra cuenta, para no introducir ambigüedad en login.

Los roles y estados son exclusivamente los definidos en Usuario. No hay controles para
conceder is_staff/is_superuser. Las cuentas nuevas no reciben esos privilegios técnicos;
al cambiar una cuenta a un rol no administrativo se retiran esos flags si existían.
Los cambios no alteran perfiles académicos, registros financieros ni contraseñas salvo
la acción explícita de restablecimiento.

## Autorización y protección del último administrador

Todas las vistas de cuentas comprueban sesión, cuenta activa y rol ADMINISTRADOR antes
de consultar o modificar. Los servicios vuelven a comprobar al actor en la transacción.
SECRETARIA, DIRECTORA, MAESTRO, ESTUDIANTE y PASTOR_PRINCIPAL no reciben estos accesos.
No hay altas/cambios por GET; las escrituras requieren POST y protección CSRF.

Cada operación bloquea los administradores activos en orden de PK y vuelve a leer al
actor, antes de bloquear la cuenta objetivo. No se permite desactivar, bloquear ni cambiar
el rol del último ADMINISTRADOR ACTIVA. Si existe otro administrador activo se admite el
cambio; modificar el propio acceso administrativo cierra la sesión. No hay eliminación
de cuentas ni eliminación masiva de históricos.

Las escrituras antiguas de Usuario en Django Admin (incluido su endpoint de contraseña)
quedan cerradas: alta/cambio/eliminación no disponibles. La vinculación `Estudiante.usuario`
queda de solo lectura allí para centralizar su confirmación en este módulo. El bootstrap
administrativo por CLI y los cambios directos de un operador de BD están fuera del control
de estas vistas: no se ejecutaron ni se usan como vías de autoservicio.

Los bloqueos son compatibles con PostgreSQL, pero su comportamiento concurrente para
este módulo no se validó contra ese motor en esta tarea, por restricción explícita.
SQLite verifica los casos funcionales; no certifica bloqueos de fila concurrentes reales.

## Vinculación con el Portal del Estudiante

La cuenta debe tener rol ESTUDIANTE. ADMINISTRADOR selecciona explícitamente un expediente
por código/nombre y marca la confirmación de identidad. No se propone ni asigna por
coincidencias de correo/nombres. Si no confirma, no se guarda.

Se utiliza la relación OneToOne existente. Bajo bloqueo se comprueba que la cuenta no tenga
otro expediente y que el expediente seleccionado no tenga otra cuenta. Reconfirmar el mismo
vínculo es seguro; reasignar cualquiera de sus extremos se rechaza. Un vínculo equivocado
requiere revisión administrativa separada: no hay traslado ni desvinculación automática.
Se impide cambiar de rol una cuenta ya vinculada a Estudiante, y se conserva el rol de
una cuenta con perfil Maestro para no dejar huérfano el acceso a esos perfiles.

El portal continúa resolviendo identidad desde la sesión. Una cuenta vinculada puede
entrar después de completar el cambio inicial de contraseña, con las mismas restricciones
institucionales de solvencia. No se modificó la lógica académica/financiera del portal.

## Creación y restablecimiento de acceso

La creación requiere contraseña temporal confirmada. La acción **Restablecer acceso**
valida una nueva contraseña con los validadores Django, la guarda mediante set_password y
marca el campo existente debe_cambiar_password. Nunca muestra ni recupera la contraseña
anterior. El restablecimiento no cambia rol, estado o vínculo ni reactiva cuentas bloqueadas.

La contraseña temporal se entrega manualmente por un canal institucional seguro, tras
verificar a la persona. No se configuraron correo, SMS ni servicios externos. No hay
caducidad temporal nueva: el modelo existente solo dispone del indicador de cambio.

El middleware obliga a reemplazar la clave antes de usar cualquier módulo. Solo permite
login, logout y `/mi-cuenta/contrasena/` mientras esa marca está activa. La persona debe
conocer la contraseña temporal y confirmar otra nueva, distinta de la anterior. No puede
quitar la marca enviando datos extra en una edición de cuenta. El cambio conserva su
sesión con update_session_auth_hash y restablece la marca únicamente tras guardar.

Los hashes de sesión de Django invalidan las sesiones anteriores tras un reset. Las
pantallas de contraseña usan PasswordInput sin volver a incluir valores, filtros de
parámetros sensibles en errores y respuestas privadas/no-store. No se imprimen claves
ni se incluyen en mensajes. Un restablecimiento de la propia cuenta también exige el
paso de cambio; no deja una sesión administrativa operando con la clave temporal.

## Validación esencial realizada

```sh
python manage.py test core.test_usuarios --settings=academico.test_settings --noinput
```

**8 pruebas esenciales aprobadas**: permisos GET/POST y servicio; creación con rol y sin
privilegios técnicos/vínculo automático; filtros/edición/duplicados; vínculo confirmado y
rechazo de reasignaciones; desactivación y conservación del perfil docente; protección del
último administrador (inactivación, bloqueo y cambio de rol); reset, invalidación de sesión
y cambio obligatorio; cierre de vías antiguas de escritura de Django Admin.

Se refinó la comprobación del endpoint antiguo de contraseña para exigir HTTP 403 sin
omitir rutas, y se comprobó que no se acepta reutilizar la misma clave temporal. Se
repitieron solo esos casos afectados, ambos correctos. Una comprobación adicional de
navegación por roles también aprobó:

```sh
python manage.py test core.test_frontend.FrontendInstitucionalTests.test_menu_exacto_por_rol_sin_enlaces_ficticios --settings=academico.test_settings --noinput
```

`manage.py check --settings=academico.test_settings` y `git diff --check`: correctos.
No se repitieron las baterías completas académica o financiera.

Comprobación visual Chromium/Playwright con SQLite en memoria: listado → crear cuenta →
vincular expediente explícito → login estudiantil → cambio obligatorio → portal con el
perfil seleccionado. Escritorio 1440 px y móvil 390 px; sin desbordamiento en listado,
alta, edición, vínculo y restablecimiento. Capturas en `/workspace/artifacts/usuarios/`,
fuera del repositorio. Solo cuentas y expedientes ficticios.

## Archivos añadidos o modificados para este módulo

- `core/usuarios_forms.py`, `usuarios_servicios.py`, `usuarios_views.py`: formularios,
  autorización, transacciones y recorrido de cuentas.
- `core/middleware_acceso.py`, `config/settings.py`: cambio obligatorio de contraseña.
- `core/urls.py`: rutas de administración y cambio personal de contraseña.
- `core/admin.py`, `academico/admin.py`: cierre de escrituras/vinculación alternativas.
- `templates/core/usuarios/base.html`, `listado.html`, `formulario.html`, `vinculo.html`,
  `restablecer.html`, `cambiar_password.html`; `static/css/usuarios.css`: interfaz.
- `templates/core/dashboard.html`, `templates/core/partials/sidebar.html`: acceso por rol.
- `core/test_usuarios.py`, `core/test_frontend.py`: pruebas esenciales y menú actualizado.
- `docs/manuales/portal_estudiante.md` y este documento: procedimiento de vinculación.

## Límites y estado

No se añadieron campos, modelos ni migraciones. No se ejecutó `manage.py migrate` ni se
realizaron escrituras en PostgreSQL. Los tests usan el runner existente de SQLite aislado,
que construye únicamente tablas efímeras. No se modificaron cuentas reales, claves reales
ni registros reales de docentes; no se cambió main ni se hizo commit/push.

El esquema PostgreSQL real debe respetar las unicidades de identificadores y del vínculo
OneToOne ya declaradas en los modelos. La creación de cuentas institucionales iniciales,
corrección de un vínculo previo erróneo y entrega de credenciales siguen requiriendo un
operador autorizado y verificación de identidad; no hay autoasignación ni recuperación
pública. Esta entrega no constituye autorización de despliegue o producción.
