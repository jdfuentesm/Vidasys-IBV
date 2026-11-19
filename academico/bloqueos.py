"""Orden común: usuarios (PK), curso, maestro, sesiones, solicitud.

Los servicios de cuentas no esperan cursos. Bloquear usuarios antes del curso
impide formar un ciclo con cuentas que también bloquean expedientes de estudiante
mientras una matrícula espera el curso. No usar select_related en estos locks.
"""
from core.models import Usuario


def bloquear_usuarios(*identificadores):
    return {u.pk: u for u in Usuario.objects.select_for_update().filter(
        pk__in=set(identificadores)).order_by('pk')}
