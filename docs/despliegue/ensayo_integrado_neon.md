# Ensayo funcional integrado sobre Neon demo

Estado: preparado y revisado estáticamente. No ejecutado ni validado todavía en
PostgreSQL. No sustituye una prueba de concurrencia ni autoriza producción.

## Ejecución futura, solo después de autorización

Usar la rama `semana-9-rutas-calificaciones`, dependencias instaladas y las
variables de entorno demo ya configuradas de forma privada. No imprimirlas ni
incluir contraseñas en comandos. Con el esquema previamente instalado:

```bash
python manage.py probar_flujo_demo_pg --settings=config.settings_demo_pg --confirmar
```

**Este comando sí escribe temporalmente en PostgreSQL. No ejecutarlo todavía.**
No utilizar `migrate`, `test`, el instalador ni el sembrador para este ensayo.
Se requiere una demo sin datos de aplicación: si algún modelo académico,
financiero o Usuario contiene registros, el comando aborta sin borrarlos ni
completarlos. Las tablas técnicas de Django no necesitan estar vacías.
Ejecutar sin usuarios web ni otros procesos escribiendo en la demo.

## Controles y recorrido

Antes de la primera escritura se exige configuración `config.settings_demo_pg`,
PostgreSQL, nombre configurado y efectivo `vidasys_demo`, usuario configurado y
efectivo `vidasys_demo_limitado`, una sola conexión sin routers y calendario
PostgreSQL. La configuración existente rechaza roles administrativos y servidores
cuyo catálogo contenga `gestion_ibv`; no se conecta a esa base. Se fija
`search_path=public` y se comprueba el esquema con el verificador existente,
sin instalar ni corregir objetos. Si faltan permisos u objetos, aborta.

En una única transacción, con límites de espera y bloqueo compartido con el
sembrador, el comando:

1. Crea cuentas Secretaría, Dirección, Maestro y Estudiante con claves aleatorias
   solo en memoria y direcciones `example.test`; añade identidades sintéticas
   auxiliares para verificar accesos ajenos.
2. Crea ciclo del año actual, seis materias/cursos y calendario JSONB; comprueba
   su lectura. Los conceptos y fechas son escenarios sintéticos, no políticas
   nuevas. Los importes proceden del servicio financiero existente (actualmente
   20 por obligación); no se modifica esa regla ni se replica su cálculo.
3. Ejecuta `matricular`, comprueba seis inscripciones, seis obligaciones y
   repetición idempotente. Vence solo la obligación sintética de matrícula.
4. Comprueba insolvencia mediante la función existente y las tres vistas;
   comprueba bloqueo académico y cuenta disponible en el portal. Añade un
   convenio sintético con cuota futura para verificar la excepción vigente y
   su revocación por incumplimiento; descarta ese escenario antes del pago.
5. Reserva recibo y registra pago con los servicios actuales; verifica importe,
   saldo, repetición sin duplicados y solvencia. Anula y restaura únicamente
   ese pago sintético para comprobar exclusión de anulados y trigger SQL.
6. Crea una sesión y registra asistencia y calificación mediante las vistas
   existentes, con los tokens de revisión de sus formularios. Verifica que los
   datos se guardaron y que el modelo calculó la nota.
7. Usa autenticación Django y peticiones internas HTTPS del cliente de pruebas
   para verificar la matriz de acceso de los cuatro roles, denegaciones GET/POST,
   cuenta/recibo propios, manipulación de identidad y curso ajeno. No arranca un
   servidor ni realiza peticiones de red. Las denegaciones esperadas pueden
   producir mensajes 403/404/405 en los logs.
8. Valida las claves foráneas diferidas, fuerza rollback y comprueba ausencia de
   registros de aplicación. Un error también revierte la transacción.

La matriz respeta las reglas actuales: Dirección consulta finanzas pero no cobra;
Secretaría cobra; solo Maestro registra notas/asistencia; solo Dirección autoriza
clases extraordinarias; ninguno de estos cuatro roles administra usuarios.
Son comprobaciones representativas, no una auditoría exhaustiva de endpoints.

## Reversión y límites

No hay opción de conservar registros. Usuarios, sesiones de autenticación de este
ensayo (backend de sesiones Django en base), calendario JSONB y demás filas
sintéticas quedan sujetos a la transacción exterior. Se evita almacenamiento
financiero en archivos; correo se sustituye temporalmente por memoria y los
estáticos por un backend que no necesita `collectstatic`. No cambian los ajustes
de despliegue persistentes ni se generan archivos de credenciales.

**Las secuencias PostgreSQL no revierten con rollback.** El ensayo avanza IDs y
el correlativo reservado de recibo puede dejar huecos. No se ejecuta `setval`,
no se reinician secuencias ni se borran históricos para corregirlos. Tampoco es
una prueba de commit durable, de concurrencia, de HTTPS externo o de navegador.
La confirmación final depende de la ejecución autorizada. Un fallo muestra la
comprobación incumplida y revierte; no reintentar automáticamente ni desactivar
controles para hacerlo pasar.
