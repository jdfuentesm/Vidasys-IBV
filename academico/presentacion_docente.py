"""Lectura F8.4. Delega elegibilidad a las reglas institucionales existentes."""
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.shortcuts import render
from .correcciones import validar_destino
from .flujo import resumen_docente
from .models import Curso, SolicitudAcademica


def resumenes_propios(usuario):
    cursos = Curso.objects.filter(maestro__usuario=usuario).select_related('materia', 'ciclo', 'maestro')
    return [resumen_docente(c) for c in cursos]


def presentar_libro(request, contexto, status=200):
    curso = contexto.get('curso')
    if curso and curso.estado == 'FINALIZADO':
        try:
            pendientes = {s.inscripcion_id: s for s in SolicitudAcademica.objects.filter(
                curso=curso, tipo='CORRECCION_CALIFICACION', estado='PENDIENTE')}
            for fila in contexto['filas']:
                fila['correccion_disponible'] = False
                try:
                    validar_destino(curso, fila['inscripcion'], fila['nota'])
                except ValidationError as error:
                    fila['motivo_correccion'] = ' '.join(error.messages)
                else:
                    pendiente = pendientes.get(fila['inscripcion'].pk)
                    if pendiente:
                        fila['motivo_correccion'] = 'Ya existe una solicitud pendiente; espere su resolución.'
                        if pendiente.solicitante_id == request.user.pk:
                            fila['solicitud_pendiente'] = pendiente
                    else:
                        fila['correccion_disponible'] = True
        except DatabaseError:
            for fila in contexto['filas']:
                fila['correccion_disponible'] = False
                fila.pop('solicitud_pendiente', None)
                fila['motivo_correccion'] = 'No se pudo comprobar la disponibilidad. Consulte sus solicitudes o intente nuevamente.'
    return render(request, 'academico/registrar_calificacion.html', contexto, status=status)


def presentar_asistencia(request, contexto, status=200):
    contexto['edicion_asistencia'] = any(not f['form'].motivo_bloqueo for f in contexto['filas'])
    return render(request, 'academico/registrar_asistencia.html', contexto, status=status)
