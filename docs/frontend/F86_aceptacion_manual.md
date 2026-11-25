# F8.6 — Aceptación en Windows y teléfono

El commit F8.6 queda local en Codex hasta autorización de push. `git pull` en Windows
solo obtiene lo publicado; no prometer que descargará este informe antes de publicarlo.
El código operativo y los dos lanzadores permanecen idénticos a F8.5.

## Inicio seguro de la simulación

Desde la carpeta del repositorio Windows, con el entorno virtual y dependencias ya instalados:

```powershell
git branch --show-current
git status --short
git rev-parse HEAD
.\venv\Scripts\python.exe iniciar_simulacion.py --semilla 711 --fecha 2026-11-22 --comprobar
.\venv\Scripts\python.exe iniciar_simulacion.py --semilla 711 --fecha 2026-11-22
```

Debe usarse `semana-9-rutas-calificaciones`. El último comando mantiene vivo un nuevo
ensayo en `http://127.0.0.1:8000/login/`; usar los usuarios ficticios mostrados y la
contraseña temporal de esa misma consola. No guardarla en Git ni capturas. `Ctrl+C`
descarta los datos; no ejecutar `migrate`, no usar settings PostgreSQL ni `.env` productivo.
`--comprobar` genera y descarta su propio ensayo, no prepara datos para el siguiente proceso.

Para el teléfono, detener primero el servidor y usar únicamente Wi-Fi privada de confianza:

```powershell
.\venv\Scripts\python.exe iniciar_simulacion.py --semilla 711 --fecha 2026-11-22 --lan
```

IP Windows debe seguir siendo `192.168.1.154`; abrir desde el móvil
`http://192.168.1.154:8000/login/`. Si Windows solicita firewall, limitar el permiso a
red privada/local; no abrir puertos del router ni usar red pública. La IP está validada
explícitamente en el lanzador: si cambia, este comando no la descubre automáticamente.
LAN mantiene hosts y CSRF; HTTP de ensayo no sustituye HTTPS productivo. F8.6 no cambió
ni certificó una conexión física a la Wi-Fi del usuario.

## Recorrido condensado

1. **Directora** (`sim-directora`): inicio → pendientes → filtros/historial → expediente
   original. Revisar comparación y consecuencias antes de resolver mediante POST. Abrir
   reportes; comparar período y saldo actual. Para 2.764/86/2.678, borrar ambas fechas;
   el mes actual no tiene necesariamente ese acumulado.
2. **Secretaría** (`sim-secretaria`): buscar un alumno; registrar/editar uno ficticio y
   volver al expediente. En F7.1 la matrícula nueva se bloquea por cursos finalizados:
   conservar mensaje/datos, no reabrir cursos. Revisar caja propia abierta, cobrar una
   mensualidad elegible, comparar total → confirmar → recibo. Reenviar mismo formulario
   debe devolver el mismo recibo. Repetir sin JS en un ensayo nuevo.
3. **Administración** (`sim-administrador`): inicio → usuarios/accesos → Finanzas/caja →
   reportes/auditoría. Distinguir período, stock y compromiso. No debe aparecer bandeja
   unificada ni aprobación exclusiva de Dirección.
4. **Maestro activo** (`sim-maestro-04`): cursos propios → curso 4 → asistencia; libro,
   componentes, cálculo y guardar lote. Cambiar ancho con datos escritos: mismos campos
   y valores. Un 101 debe rechazarse conservando el valor; corregir y guardar. No acceder
   a curso 2 (404). **Cerrado** (`sim-maestro-01`, curso 1): consulta sin guardado ordinario;
   probar una corrección elegible → comparar/enviar → resolver como Directora y consultar
   historial, sin reabrir. Las inasistencias bloquean cuando lo indica el validador.
5. **Estudiante solvente** (`sim-estudiante-01`): materias, estados provisionales/definitivos,
   componentes/asistencia, cuenta, recibo propio e impresión.
6. **Insolvente** (`sim-estudiante-17`): cuenta disponible; `/portal/academico/` debe responder
   403 también por URL directa. **Padrinazgo** (`sim-estudiante-29`): saldo 120, protección
   120, cargo 0; no es un pago ni exige que exista recibo. No debe aparecer identidad,
   contacto o datos privados del padrino. Recibo ajeno debe responder 404.
7. **Pastor** (`sim-pastor-principal`): solo Inicio/sesión activa y salida; no inventar módulos.
8. En 390/768/1366, recorrer menú con teclado, Enter/Escape, salto al contenido, errores,
   detalles y regreso. Repetir consultas sin JS. Imprimir recibo/reporte y descargar CSV
   desde rol autorizado. En móvil verificar controles y región propia de tablas, sin scroll exterior.

Las operaciones cambian el ensayo en memoria. Reiniciar antes de volver a comparar las
cifras iniciales. Nunca conciliar un estado modificado como si fuese la semilla original.

## Matrícula positiva y regresión completa, fuera de F7.1

Para el flujo válido con seis cursos activos y para todo el conjunto, usar SQLite de pruebas:

```powershell
.\venv\Scripts\python.exe manage.py test core.test_integracion_f86 --settings=academico.test_settings --noinput
.\venv\Scripts\python.exe manage.py test --settings=academico.test_settings --noinput
.\venv\Scripts\python.exe manage.py check --settings=academico.test_settings
git diff --check
```

El test F8.6 estará disponible tras publicar/actualizar ese commit. El runner exige SQLite
en memoria; no sustituir los settings ni dirigirlo a una base persistente. El fixture
positivo automatizado no se presenta como una matrícula posible en los ciclos F7.1 cerrados.
