# Revisión de identidad visual VidaSYS-IBV

Base: `69b4973`, rama `semana-9-rutas-calificaciones`. Cambios visuales autorizados para commit y push en esta rama.

## Cambios

- `templates/core/login.html`: presentación institucional adaptable, logotipo VidaSYS original como marca principal, escudo original completo, etiquetas, autocompletado y mensajes de error; conserva POST, nombres de campos, campos obligatorios y CSRF.
- `templates/core/base.html`: el login reutiliza el CSS institucional y deja de depender de Bootstrap, Google Fonts e iconos externos. Es la única pantalla que extiende esta plantilla.
- `templates/core/aplicacion.html`: encabezado con logotipo VidaSYS, escudo IBV secundario, identificación del usuario y rol y pie institucional.
- `static/img/vidasys.png`: nuevo archivo oficial, extraído íntegramente del ZIP proporcionado.
- `templates/core/partials/sidebar.html`: iconos de navegación locales, manteniendo enlaces, orden, condiciones por rol y estados activos existentes.
- `templates/core/partials/icono.html`: nuevo componente SVG para iconos de interfaz; no representa ni sustituye logotipos.
- `templates/core/dashboard.html`: bienvenida y tarjetas con iconos; conserva las funciones y condiciones existentes, sin estadísticas añadidas.
- `static/css/institucional.css`: paleta, espaciados, tarjetas, navegación, login y adaptación móvil compartidos; conserva estilos de los formularios y tablas académicas.

## Recursos oficiales

`static/img/logo.png` es el escudo oficial IBV y permanece sin modificaciones. Se muestra completo, respetando su proporción.

El logotipo oficial VidaSYS se extrajo de `vidasys-logo-original.zip` a `static/img/vidasys.png` y se compararon sus bytes con la entrada del ZIP: idénticos. SHA-256: `c44cc53be6626475190cfc84493e3ebae72adca3b0499b4663539c66cccabe6e`.

Se utiliza como marca principal en el login y en el encabezado compartido del dashboard y los módulos. El escudo IBV permanece como identificación secundaria. Se conservan los archivos íntegros: sin recortes, redibujo, filtros ni modificación de sus elementos. La presentación usa ancho adaptable y alto automático.

## Verificación

Se instalaron las dependencias existentes en un entorno virtual temporal, sin cambiar los requirements.

```bash
DB_NAME=unused DB_USER=unused DB_PASSWORD=unused DB_HOST=127.0.0.1 \
python manage.py test --settings=academico.test_settings --noinput
```

- 172 pruebas: 166 aprobadas, 5 fallos y 1 error en `core.tests.UsuarioAdminTests`. Los mismos 6 problemas se reprodujeron ejecutando `core.tests` sobre una copia limpia de `69b4973`; son preexistentes, relacionados con respuestas 403 en administración de usuarios.
- Verificación final: 12 pruebas aprobadas (las 11 de `core.test_frontend` y una comprobación temporal integral del login). Incluyen accesos exactos por rol, contexto docente, campos y CSRF; rechazo de POST sin token, error de contraseña, login correcto, acceso al dashboard, logout y redirección posterior.
- System check sin incidencias.
- `collectstatic` con `whitenoise.storage.CompressedManifestStaticFilesStorage`, con salida y configuración temporales: correcto. WhiteNoise responde `200 OK` para los dos logotipos, tanto en las rutas originales como en las versionadas del manifiesto; sus cuerpos son idénticos a los archivos fuente.
- Chromium/Playwright: 32 combinaciones de login, error de login y los seis roles a 320, 360, 768 y 1440 píxeles. Sin desbordamiento horizontal ni imágenes rotas; un h1 por vista; ambos logotipos presentes y proporción original de VidaSYS verificada en cada vista. Comprobados campos obligatorios, presencia del token CSRF y apertura/cierre del menú móvil, incluida la tecla Escape.
- Inspección visual de capturas de login y dashboard en móvil y escritorio.
- `git diff --check`: correcto.

Las vistas de revisión del navegador se renderizaron con usuarios de muestra sin guardar y sin consultas a BD. No equivalen a una prueba integral sobre Render. Todas las pruebas de datos usaron SQLite en memoria y archivos financieros temporales del runner existente. No se consultó ni modificó Neon, ni se cambiaron modelos, migraciones, permisos, vistas, autenticación, lógica financiera, credenciales o `.env`.

## Estado para publicación

Integración gráfica completa y comprobaciones específicas aprobadas. Publicación del código autorizada por el usuario; alcance limitado a esta rama. La suite completa anterior conserva 6 problemas preexistentes en administración de usuarios, documentados arriba; no se corrigieron ni se modificaron permisos. La configuración existente de `render.yaml` conserva `autoDeploy: false`; no se modifican los ajustes de despliegue. El resultado remoto se informa después del push.

## Comprobación previa al push

Se repitieron las 12 pruebas específicas y las 32 vistas de interfaz. Se verificaron alcance exclusivo de 9 archivos visuales/documentales, originalidad de los logotipos, conservación de rutas y condiciones por rol, CSRF, autoescape, ausencia de patrones de credenciales en los archivos incluidos y las cuatro respuestas de WhiteNoise. Sin incidencias en estas comprobaciones. No se ejecutó el arranque de producción ni `/healthz/`, porque ambos acceden a PostgreSQL.
