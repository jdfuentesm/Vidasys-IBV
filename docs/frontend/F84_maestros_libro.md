# F8.4 — Maestros y libro de calificaciones

Base `5057a8283bdec999ba39c9b65e4abcb52ece25c1`, rama
`semana-9-rutas-calificaciones`. Solo presentación, lecturas auxiliares y JS progresivo.
Sin cambios en modelos, migraciones, formularios Python, servicios, permisos, rutas,
fórmula, límites, redondeos, asistencia, cierre, solvencia ni lanzador LAN.

## Diagnóstico y contratos

El libro ya tiene un único formulario por lote, tokens de revisión por fila, guardado
atómico y vista previa del servidor (`accion=calcular`). Asistencia usa curso/sesión,
lista completa de inscripciones y revisiones, con habilitación en `FilaAsistenciaForm`.
No se crean endpoints individuales ni se modifica ningún nombre de campo.

El problema visual era una tabla ancha con nota/estado separados de la identidad,
instrucciones de edición en cursos cerrados, selección truncada y enlaces de corrección
sin comprobar elegibilidad. Se reutilizan tokens y navegación F8.1 y los servicios reales.

## Operaciones, fuentes y permisos

| Pantalla / operación | Fuente | Permiso y comportamiento |
| --- | --- | --- |
| Inicio / Mis cursos | Cursos filtrados por `maestro__usuario`; `resumen_docente` existente | Solo cursos asignados; pendientes del servicio, sin indicadores inventados. Tres prioridades principales como máximo. |
| Libro / guardar lote | `FilaCalificacionForm` y vista original | Docente activo y curso propio ACTIVO; bloqueos, revisiones y transacción originales. |
| Vista previa | POST original `accion=calcular` | Cálculo exclusivo del servidor. JS no replica fórmula; solo actualiza filas editadas y no bloqueadas. |
| Estado académico | `InscripcionCurso.estado` almacenado | Distingue Aprobada/Reprobada/Inasistencia de solo lectura; no infiere resultado definitivo desde una nota provisional. |
| Asistencia | Formularios existentes y `motivo_bloqueo` | Edición solo cuando alguna fila está habilitada. Curso cerrado/sesión suspendida o cancelada: consulta, sin botón de guardar. |
| Sesiones | Estados, autorización y `editable` del flujo original | Ordinarias/extraordinarias identificadas; mensajes de edición solo cuando procede. No crea estados ni autoriza extraordinarias. |
| Cierre | `resumen_docente`, requisitos y servicio originales | Mantiene requisitos, fechas, revisión, atomicidad y prohibición de reapertura ordinaria. |
| Corrección excepcional | `correcciones.validar_destino` existente; solicitudes pendientes de origen | Solo finalizado/coherente/elegible. Si falla, no muestra nueva solicitud y explica motivo. No autoriza ni escribe. |
| Solicitud pendiente | Tipo/inscripción/curso y estado original | Enlace solo si la solicitud pertenece al docente actual; las ajenas no revelan expediente. Decisión sigue exclusiva de Dirección. |
| Reportes | Filtros y constructores originales | Maestro consulta solo sus cursos, CSV/impresión sin cambios; retorno al libro con curso seleccionado. |

Secretaría, Administración, Dirección, estudiantes y Pastor no obtienen por esta entrega
permiso de edición docente. Sus accesos institucionales previos siguen funcionando. Un
maestro ajeno continúa recibiendo 404; otros roles/POST no autorizados mantienen sus rechazos.
No se alteran autenticación, CSRF, revisiones ni permisos del servidor.

## Libro adaptable y componentes

Una sola tabla y DOM: cada fila contiene identidad, nota, estado y un detalle nativo de
componentes. Apreciación/extras, tareas y exámenes se agrupan sin cambiar sus nueve campos.
Observaciones y campos ocultos aparecen una vez. El formulario conserva `curso`,
`inscripciones`, todos los nombres `nota-<pk>-...` y revisiones originales.

- Escritorio desde 1.000 px: componentes abiertos automáticamente, encabezado fijo y
  desplazamiento vertical dentro del contenedor. Edición por lote intacta.
- Tableta/móvil: ficha con identidad/nota/estado y componentes ampliables. Sin scroll
  horizontal del documento o del libro. No se clonan campos entre resoluciones.
- Cambiar resolución abre/cierra detalles; nunca reinicia valores, cambia nombres,
  deshabilita campos ni envía formularios.
- Búsqueda local opcional por nombre/código: solo oculta filas visualmente. El POST
  conserva el lote completo, incluidas filas fuera de la búsqueda. Está fuera del formulario
  para no disparar cambios/vista previa al buscar. No tiene nombre POST.
- Índice nativo «Ir a un estudiante» disponible sin JS. Los detalles funcionan sin JS;
  en escritorio sin JS se abren manualmente, conservando el mismo guardado por lote.
- Errores individuales visibles y detalles abiertos, enlaces a la fila, foco inicial y
  rangos de widgets originales. Invalidación nativa abre el detalle para acceder al campo.
- Guardia de doble envío sin deshabilitar campos. Las revisiones y atomicidad reales
  permanecen en servidor. Vista previa respeta estados guardados de filas sin editar o
  bloqueadas, en lugar de sustituirlos por mensajes de otra fila.
- La navegación contextual de curso se reutiliza una sola vez, con estado, ciclo y reporte.
  Selector corto por código institucional/ciclo y catálogo con nombres completos; no
  requiere conocer un ID interno ni depender del texto truncado de un select nativo.

Componentes: contexto de curso compartido, selector/catálogo, tarjetas de cursos, campo
numérico con rango y estado académico reutilizado de Incidencia 01. CSS específico sobre
tokens F8.1; JS sin nuevas dependencias. La ayuda de fórmula sigue accesible y los controles
no cambian el redondeo ni agregan puntos por su cuenta.

## Correcciones y cursos cerrados

El adaptador consulta `validar_destino` sin replicar condiciones de elegibilidad en plantillas
o JS. Bloquea visualmente cuando hay inasistencia, dos injustificadas incluso con estado
histórico incoherente, matrícula inactiva, nota faltante o datos no definitivos/coherentes.
No repara registros. Una solicitud pendiente evita preparar otra y enlaza su historial si es
propia. Fallo de lectura: acciones deshabilitadas con aviso; no disponibilidad supuesta.
El endpoint original vuelve a comprobar permisos y datos al solicitar y decidir.

El validador realiza sus propias consultas por inscripción y `full_clean`; se conserva como
fuente de verdad. Optimizar elegibilidad por lotes requeriría diseñar una API de lectura
compartida sin duplicar reglas; queda pendiente medir cursos mucho mayores en PostgreSQL.
La disponibilidad es una lectura momentánea, no una autorización ni garantía frente a cambios
concurrentes. Las instantáneas y bloqueos siguen en los servicios originales.

## Recorrido Windows y móvil

Después de autorizar la publicación y actualizar la rama, con el entorno Python existente:

```powershell
$env:PYTHONUTF8 = '1'
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22
# Alternativa LAN ya existente, solo con esa IP de Windows y Wi-Fi privada:
python -B .\iniciar_simulacion.py --semilla 711 --fecha 2026-11-22 --lan
```

Una alternativa por vez. `http://127.0.0.1:8000/login/` o
`http://192.168.1.154:8000/login/`; contraseña temporal de consola, sin guardarla en Git.
Solo SQLite en memoria. Detener y reiniciar descarta las operaciones del recorrido.

1. `sim-maestro-04`: inicio → curso 4 activo → Calificaciones. Comprobar nombre, ciclo,
   pendientes y enlaces del curso; no se muestran cursos de otros maestros.
2. En móvil, abrir componentes de SIM-001. Registrar 40/20/20/20 en apreciación, extras
   vacíos, tareas/exámenes 75. Vista previa 80,00 desde servidor. Cambiar 390→768→1366:
   valores conservados. Buscar alumno: guardar sigue siendo de todo el lote.
3. Guardar: nota 80,00 provisional, inscripción CURSANDO. Probar un 101 enviándolo al
   servidor: rechazo, valores y foco preservados; ninguna fila se guarda parcialmente.
4. Asistencia → curso 4 → una sesión impartida. Modificar un registro permitido y guardar;
   observar confirmación, justificación/observaciones y estado. No hay acciones masivas nuevas.
5. `sim-maestro-01`: curso 1 finalizado. Consultar notas, asistencia y sesiones; sin botón
   ordinario para guardar ni instrucciones de edición. En filas por inasistencia, no existe
   enlace de corrección. Las elegibles abren el flujo original; las pendientes propias enlazan
   su expediente. Dirección sigue siendo quien decide.
6. Abrir reporte propio, exportar CSV/imprimir y volver al libro. Repetir edición permitida
   sin JS abriendo detalles manualmente. Recorrer con Tab, índice y foco de errores.

## Validación y pendientes

[Pruebas, evidencias y mediciones](../evidencias/F84/README.md). La desaparición del scroll
horizontal aumenta la altura del documento en móvil al mostrar las 20 fichas. Índice y búsqueda
ayudan a navegar; no se afirma reducción vertical ni se elimina información para conseguirla.
La tabla conserva semántica HTML; se requieren pruebas adicionales con lectores de pantalla
y personas reales, además de Chromium/teclado. No se certifica una nueva conexión física LAN.

F8.5/F8.6 sin implementar. Siguen críticos antes de despliegue: PostgreSQL aislado,
restricciones/transacciones/concurrencia, unificación de solvencia Django/SQL y tratamiento
formal de convenios INCUMPLIDO. No se accede a Neon ni se despliega. Commit local únicamente.
