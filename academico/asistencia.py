"""Reglas de habilitación confirmadas, sin nuevos estados ni cambios de esquema."""

def motivo_bloqueo(inscripcion, sesion):
    if inscripcion.estado == "REPROBADA_POR_INASISTENCIA":
        return "Inscripción cerrada por inasistencia. Cualquier corrección requiere revisión de Dirección; no se reabre automáticamente."
    if inscripcion.estado != "CURSANDO":
        return "Inscripción cerrada o no habilitada. No se modificará su cierre académico."
    if inscripcion.matricula.estado != "ACTIVA":
        return "Matrícula no ACTIVA: asistencia disponible solo para consulta."
    if inscripcion.matricula.ciclo_id != inscripcion.curso.ciclo_id:
        return "La matrícula no pertenece al ciclo del curso."
    if inscripcion.curso_id != sesion.curso_id:
        return "La sesión no pertenece al curso de la inscripción."
    if sesion.estado not in ("PROGRAMADA", "IMPARTIDA"):
        return "Sesión suspendida o cancelada: asistencia disponible solo para consulta."
    return ""
