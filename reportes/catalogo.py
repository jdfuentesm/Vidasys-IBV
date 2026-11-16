"""Catálogo institucional y permisos por reporte, compartidos por pantalla y exportación."""
ADMIN=('ADMINISTRADOR','DIRECTORA')
OPERATIVOS=ADMIN+('SECRETARIA',)
DOCENCIA=ADMIN+('MAESTRO',)
CATALOGO={
 'matriculas':('Estudiantes matriculados por ciclo',OPERATIVOS,'Fecha de matrícula'),
 'inscripciones':('Materias y estudiantes inscritos',OPERATIVOS+('MAESTRO',),'Fecha de inscripción'),
 'calificaciones':('Calificaciones por materia y ciclo',DOCENCIA,'Fecha de matrícula de la inscripción'),
 'asistencia':('Asistencia por curso y estudiante',DOCENCIA,'Fecha de la sesión de clase'),
 'estados':('Estado académico de inscripciones',DOCENCIA,'Fecha de matrícula de la inscripción'),
 'pagos':('Pagos recibidos por período',OPERATIVOS,'Fecha local del pago'),
 'pendientes':('Obligaciones pendientes y saldos',OPERATIVOS,'Fecha de vencimiento; saldo actual'),
 'resumen':('Resumen financiero',OPERATIVOS,'Pagos/ingresos por fecha de registro; obligaciones por vencimiento, con saldo actual'),
}
