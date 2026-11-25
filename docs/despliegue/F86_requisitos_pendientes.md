# F8.6 — Preparación pendiente para PostgreSQL y despliegue

**Estado: NO autorizado/listo para despliegue.** Documento de requisitos, no instrucciones
para ejecutar automáticamente en Neon. En F8.6 no se inició PostgreSQL ni se aplicó DDL.

El cierre visual no aprueba el esquema actual, funciones SQL, integración web productiva
o concurrencia. Las pruebas históricas de `preparacion_postgresql.md` describen una versión
y esquema sintético anteriores: no certifican la versión F2–F8 completa ni sus tablas nuevas.

## Puertas de aceptación, en orden

| Prioridad | Trabajo separado | Evidencia verificable necesaria |
| --- | --- | --- |
| Bloqueante para despliegue | Unificar solvencia Django/SQL | Contrastar `financiero.consultas.solvente`/`lectura.EstadoFinanciero` con `estudiante_esta_solvente` del script 15 y vistas 16/17. Definir una fuente compatible con F6; matrículas, vencimientos, becas, convenios, reserva, cobertura vigente/futura/expirada, pagos/donaciones anulados y dos implementaciones deben producir el mismo acceso. Revisar todos los consumidores, reportes y autorizaciones; no sustituir funciones históricas sin aprobación. |
| Bloqueante para despliegue | Inventario de esquema real y plan de incorporación | Export autorizado de solo esquema: tablas, defaults, secuencias, índices parciales, CHECK, FK, triggers, funciones/vistas y roles. Contrastar `managed=False` y cada migración nueva; DDL explícito exclusivamente sobre objetos autorizados. Identificar diferencias del esquema sintético; no asumir que `migrate` crea las tablas históricas. |
| Bloqueante para despliegue | PostgreSQL totalmente aislado de Neon/producción | Instancia/base/rol de ensayo explícitos, sin datos reales; registrar versión, esquema y semillas. No iniciar ni conectar desde esta fase. Posteriormente ensayar instalación nueva y actualización de una copia sintética del esquema existente, incluidos los datos históricos. |
| Bloqueante para despliegue | Restricciones físicas y transacciones | Verificar CHECK/NULL/UNIQUE/FK y origen único de `movimiento_caja`; solicitudes por tipo, pendientes únicas, motivos/resoluciones; importes, saldos y conservación de pagos/cierres. Provocar fallo después de cada escritura relevante y comprobar rollback completo en PostgreSQL real. |
| Bloqueante para despliegue | Concurrencia e idempotencia | Dos conexiones reales: misma solicitud, decisiones opuestas, mismo token de cobro, dos cobros contra saldo, pago/beca/padrinazgo/convenio/cierre simultáneos y reasignación docente. Verificar orden de bloqueos compartidos, ausencia de duplicados, pérdida de actualización o deadlock no manejado. SQLite no comprueba esto. |
| Pendiente funcional a resolver antes de aceptación operativa | Convenios INCUMPLIDO | Definir y autorizar el servicio formal de transición y sus efectos institucionales. No inferirlo desde UI ni forzar estado en la simulación. Hasta acordarlo, documentar ACTIVO con cuota vencida y sus limitaciones. |
| Bloqueante para publicación web | Configuración/seguridad productiva | Revisar SECRET_KEY real externa, DEBUG=False, hosts/orígenes concretos, TLS BD verify-full, rol mínimo, cookies, CSRF, sesiones, proxy de confianza, HTTPS/HSTS y logs sin secretos. Ejecutar check de despliegue solo con configuración aislada/autorizada. No publicar la contraseña temporal de simulación. |
| Bloqueante para publicación web | Web, estáticos y despliegue | Construir imagen/Gunicorn y `collectstatic` con manifiesto WhiteNoise; resolver imágenes/CSS/JS con DEBUG=False. Comprobar health/login/formularios/CSRF/exportación/impresión vía HTTPS y recuperación tras reinicio. Revisar persistencia del calendario y permisos de escritura. No usar runserver LAN como servidor público. |
| Bloqueante antes de tocar una base existente | Respaldo y recuperación ensayados | Respaldo autorizado y verificado; plan SQL/transaccional por versión, verificación posterior de conteos/importes/objetos y restauración probada en destino aislado. No retirar tablas/historial como recuperación improvisada. Autorización explícita para la intervención y para publicar. |

## Protecciones que permanecen intactas

- `config/settings_demo_pg.py` impide `migrate`, `flush` y `test` en la demo y valida
  destino/privilegios. No eliminar ni sortear esa protección para incorporar nuevas tablas.
- No usar el inicializador de base vacía sobre una base existente. La incorporación de
  solicitudes/objetos nuevos requiere un procedimiento separado, revisado contra el DDL.
- `render.yaml` mantiene `autoDeploy: false`. No se modificaron Docker, scripts, configuración,
  modelos, migraciones ni SQL. El push tampoco está autorizado en F8.6.
- La simulación y sus lanzadores solo aceptan SQLite `:memory:`. No dan evidencia de
  persistencia, rendimiento real de PostgreSQL, bloqueos ni compatibilidad con triggers.

## Rendimiento pendiente

El libro cerrado mostró 172 consultas con 20 inscripciones frente a 9 en el activo;
elegibilidad por inscripción y lectura de historias completas son candidatos medidos.
Diseñar optimización que conserve la validación institucional, firmas y orden transaccional,
con criterios de volumen/tiempo acordados y EXPLAIN/índices en PostgreSQL aislado. No
trasladar los milisegundos de SQLite a una promesa de producción.

La paridad Django/SQL deberá ensayarse especialmente en el borde de fecha/zona horaria
America/El_Salvador, cobertura futura y vencimiento del padrinazgo, y convenio con cuota
vencida. No dar por resuelta una discrepancia ocultándola en reportes o interfaz.
