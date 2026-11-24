# F8.3 — Secretaría y formularios operativos

Base `51511119aa0d24991b5bda9dcae0b92a5f992348`, rama
`semana-9-rutas-calificaciones`. Prioridad: estudiantes, matrícula y cobros. Esta entrega
cambia presentación y lecturas auxiliares; no modifica modelos, migraciones, formularios
Python, rutas, permisos, servicios, reglas financieras/académicas ni lanzador LAN.

## Diagnóstico y decisiones de presentación

El sistema ya disponía de búsqueda por palabras/código, filtros, expediente, matrícula
transaccional e idempotente, reserva de recibo, caja y validaciones de cobertura. No se
reimplementaron. Los obstáculos eran formularios sin secciones, selección larga de estudiantes,
campos de cobro sin total visible, navegación de retorno indirecta y ayudas repetidas.

Se reutilizan tokens y navegación F8.1, paginación F8.2 y los servicios existentes como
fuente de verdad. Se conserva el máximo de tres tareas principales. Secretaría obtiene
un acceso directo adicional a registrar estudiante y agrupación de sus otras operaciones,
sin indicadores consolidados ni acceso a Usuarios o bandeja de Dirección.

## Operaciones y permisos

| Operación | Secretaría | Dirección | Administración | Otros roles |
| --- | --- | --- | --- | --- |
| Buscar, registrar, editar y consultar estudiantes | Sí | Sí | Sí | Sin acceso institucional |
| Matricular en seis materias | Sí | Sí | Sí | Sin acceso |
| Estado de cuenta y recibos institucionales | Sí | Consulta | Sí | Solo los endpoints del portal propio, si corresponden |
| Cobrar obligaciones o cuotas | Caja propia abierta | No | Caja propia abierta | No |
| Solicitar beca o convenio | Sí | Resuelve con flujos originales | Consulta | No |
| Caja | Propia | Consulta institucional | Facultades originales | No |
| Ingresos / solicitud de egreso | Facultades originales | Consulta/resolución original | Facultades originales | No |
| Anulación de pago | Solicita, sin devolución automática | Decide | Consulta original | No |
| Donaciones y padrinazgos | F6 original | Resuelve según F6 | F6 original | Portal propio según permisos |
| F7 consolidado / bandeja unificada | No / No | Sí / Sí | Sí / No | No |

La tabla resume las facultades previas; no crea permisos. Las vistas y servicios originales
siguen verificando cuenta, rol, pertenencia, reservas, caja, obligaciones y autorización.
No se conceden facultades nuevas al mostrar enlaces. Se conserva CSRF.

## Inventario de formularios

| Pantalla | Mejora F8.3 | Contrato preservado |
| --- | --- | --- |
| Registro/edición de estudiante | Identificación, contacto y registro; teclado/teléfono; errores con enlaces y foco; retorno al expediente | Nueve campos originales; código/fecha de ingreso deshabilitados al editar; validaciones originales |
| Listado de estudiantes | Fichas compactas, búsqueda original y paginación arriba/abajo | `q`, `estado`, `ciclo`, `page`; 20 por página; filtros conservados |
| Expediente | Solvencia canónica visible, contacto plegable, historial y accesos | No recalcula resultados; detalle financiero sigue en su cuenta |
| Matrícula | Estudiante/ciclo y datos de matrícula; vista previa de cursos, estados y calendario; confirmación con accesos | Mismos cinco campos, número institucional manual y estudiante fijo desde expediente; seis inscripciones/obligaciones por servicio original |
| Cobro ordinario | Saldo, descuento/reserva, parte disponible, método, total orientativo en centavos, revisión JS antes del POST, retorno desde recibo | `token`, `metodo`, `referencia`, `importe_<pk>`; no envía total, saldo ni datos calculados |
| Solicitud de beca | Estudiante/ciclo, condiciones y justificación; selección buscable | Clave, campos y aprobación exclusiva de Dirección intactos |
| Solicitud de convenio | Obligaciones/motivo, cuotas separadas y suma orientativa | Clave, revisión y management form; fechas/importes individuales; sin reparto automático |
| Cobro de convenio | Método, abonos por cuota y desglose por obligación separados; ambas sumas y diferencia | Token y nombres originales; no suma ambos desgloses como dos cobros |
| Apertura/arqueo/cierre de caja | Secciones, campos monetarios y errores claros | UUID/revisión, comparación y confirmación originales; botones `accion` conservados |
| Ingreso / solicitud de egreso / formularios de anulación | Concepto/destinatario, importe/pago, motivo/respaldo | Claves, archivos multipart, acciones y validaciones originales; solicitudes no equivalen a dinero efectivo |
| Donaciones/padrinazgos F6 | Se reutiliza su formulario por secciones, búsqueda y resumen existentes | No se duplica ni modifica `aportes.js`, contratos o servicios F6 |

Se usa un renderizador común de BoundFields: conserva campos visibles, ocultos, valores
POST, errores, ayudas y selección. No añade validadores ni modifica clases de formulario.
La búsqueda progresiva se añade a selectores largos (al menos ocho opciones); no tiene
nombre POST y conserva la selección actual aunque no coincida con el texto buscado. Sin
JavaScript permanece el selector completo. No requiere escribir IDs internos. El número
de matrícula es el identificador institucional vigente; no se inventa un generador.

## Cobro, integridad y accesibilidad

El adaptador de lectura añade la caja propia y las condiciones que ya consulta el servicio.
`parte = saldo - reserva_padrinazgo`, acotada a cero, es orientación del cobro ordinario
existente, no una fórmula de solvencia. La reserva puede diferir de la cobertura efectiva;
no se unifican ambas mediante la interfaz. Las obligaciones con convenio conservan su
advertencia visible y rechazo en servidor. No se ocultan controles al reconocer reenvíos.

JavaScript convierte importes válidos a centavos enteros. Muestra suma, método y saldo
financiero restante estimado. No distribuye montos, aplica descuentos, calcula cambio,
registra efectivo recibido ni cambia la parte cubierta. El paso «Confirmar pago ahora»
produce el POST original; revisar o volver a editar no envía un pago. Cambiar valores
invalida la revisión. Durante el envío se bloquean reenvíos del formulario sin deshabilitar
campos/botones, para conservar `accion`, `paso`, CSRF y claves. La idempotencia real sigue
siendo del servidor, incluso sin JS o con una solicitud manipulada.

Sin JavaScript el cobro conserva su envío directo original; el usuario revisa los importes
y método antes de confirmar. El servidor calcula el total definitivo y emite el recibo.
No se promete confirmación dinámica sin JS. Errores conservan valores y tokens; archivos
requieren selección nuevamente, como en Django. Resúmenes de error con enlaces, foco,
labels monetarias identificables, teclado decimal, detalles nativos y controles móviles.
Lecturas auxiliares fallidas muestran advertencias o 503 sin habilitar cobro con información
incompleta. No se corrigen reglas ni datos históricos ante errores.

## Simulación y recorrido en Windows/móvil

Después de publicar esta entrega y actualizar la rama:

```powershell
$env:PYTHONUTF8 = '1'
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22
# Alternativa LAN existente, solo con esa IP de Windows y Wi-Fi privada:
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22 --lan
```

Ejecutar solo una alternativa. Abrir `http://127.0.0.1:8000/login/` o
`http://192.168.1.154:8000/login/`. Usar `sim-secretaria` y la contraseña temporal de esa
consola; no se versionan contraseñas. SQLite exclusivamente en memoria, sin migraciones
persistentes. Al detener el proceso se descarta el ensayo. El lanzador no se modifica.

1. Inicio → Registrar estudiante nuevo. Completar datos ficticios; comprobar un error de
   fecha y su conservación. Registrar, editar teléfono y volver al expediente.
2. Buscar por nombre/código; paginar desde arriba/abajo. Abrir contacto e historial y
   consultar solvencia/cuenta. Secretaría no ve F7 ni decisiones de Dirección.
3. Matricular: seleccionar ciclo, revisar sus seis materias/estados y calendario. **F7.1
   tiene materias cerradas en ambos ciclos y no permite una matrícula nueva válida.**
   Debe rechazar sin crear obligaciones y conservar lo ingresado. No reabrir cursos para
   superar esta prueba. La prueba positiva usa fixtures SQLite con seis cursos activos;
   para un ensayo manual positivo se necesita otro ciclo correctamente configurado por
   el mecanismo administrativo existente. No se agrega uno al escenario determinista.
4. Buscar SIM-017 → Cuenta → Registrar pago. Caja propia abierta. Elegir dos mensualidades
   que permitan abonos, ingresar USD 5,25 y USD 7,35; comprobar total USD 12,60, revisar,
   confirmar y abrir/imprimir recibo. Reenviar conserva el mismo recibo, sin otro cobro.
5. Probar excedente, matrícula parcial, obligación con convenio o padrinazgo: el servidor
   debe rechazar lo incompatible. Los valores se conservan y el foco llega al error.
6. Repetir un cobro permitido sin JS. Desde Becas/Convenios revisar secciones y enviar
   solicitudes; no puede aprobarlas Secretaría. Caja conserva comparación/confirmación.
7. Reiniciar el lanzador para recuperar exactamente los datos iniciales; nunca usar una
   base persistente para este recorrido.

## Alcance pendiente

[Resultados, medidas y evidencias](../evidencias/F83/README.md).

Se priorizaron los tres flujos principales y componentes compartidos. No se rediseñaron
integralmente todos los listados o resoluciones financieros ni F6. Mejoras condicionales
más avanzadas, búsqueda paginada remota y control de historiales grandes quedan pendientes.
La búsqueda de selectores es local y carga opciones originales. Validar comprensión con
personas y lector de pantalla real: las pruebas de Chromium no sustituyen esa evaluación.

Siguen pendientes PostgreSQL aislado (restricciones/transacciones/concurrencia), unificación
de solvencia Django/SQL y servicio formal de convenios INCUMPLIDO. No son cambios de UI.
F8.4–F8.6 no implementadas. Commit local únicamente; sin push, Neon o despliegue.
