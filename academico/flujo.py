"""Operaciones académicas integradas. Sin señales, DDL ni cambios de docentes."""
import hashlib
import json
from datetime import datetime, timedelta

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Usuario
from .models import CicloAcademico, Curso, Estudiante, InscripcionCurso, Materia, Matricula, SesionClase


def cursos_del_ciclo(ciclo, bloquear=False):
    materias = set(Materia.objects.filter(numero_ciclo_formativo=ciclo.numero_ciclo).values_list('pk', flat=True))
    qs = Curso.objects.filter(ciclo=ciclo).order_by('pk')
    if bloquear:
        qs = qs.select_for_update()
    cursos = list(qs.select_related('materia') if not bloquear else qs)
    if len(materias) != 6 or len(cursos) != 6 or {c.materia_id for c in cursos} != materias:
        raise ValidationError('El ciclo debe tener exactamente seis materias y sus seis cursos correspondientes. No se guardó la matrícula.')
    if any(c.estado in ('CANCELADO', 'FINALIZADO') for c in cursos):
        raise ValidationError('Hay cursos cancelados o finalizados. Revise la configuración antes de matricular.')
    for curso in cursos:
        try:
            curso.full_clean()
        except ValidationError as error:
            raise ValidationError(f'Configuración incompatible del curso {curso.pk}: ' + ' '.join(error.messages)) from error
    return cursos


def matricular(*, estudiante, ciclo, numero_matricula, fecha_matricula, observaciones=''):
    with transaction.atomic():
        ciclo = CicloAcademico.objects.select_for_update().get(pk=ciclo.pk)
        Estudiante.objects.select_for_update().get(pk=estudiante.pk)
        cursos = cursos_del_ciclo(ciclo, bloquear=True)
        existente = Matricula.objects.select_for_update().filter(estudiante=estudiante, ciclo=ciclo).first()
        if existente:
            if existente.estado != 'ACTIVA' or existente.numero_matricula != numero_matricula or existente.fecha_matricula != fecha_matricula:
                raise ValidationError('Ya existe una matrícula para este estudiante y ciclo con datos distintos. No se modificará.')
            matricula = existente
        else:
            matricula = Matricula(estudiante=estudiante, ciclo=ciclo, numero_matricula=numero_matricula,
                fecha_matricula=fecha_matricula, estado='ACTIVA', observaciones=observaciones)
            matricula.full_clean()
            matricula.save()
        registros = list(InscripcionCurso.objects.select_for_update().filter(matricula=matricula))
        if any(i.curso_id not in {c.pk for c in cursos} for i in registros):
            raise ValidationError('La matrícula tiene inscripciones de cursos incompatibles. No se modificó nada.')
        por_curso = {i.curso_id: i for i in registros}
        for curso in cursos:
            if curso.pk not in por_curso:
                inscripcion = InscripcionCurso(matricula=matricula, curso=curso,
                    fecha_inscripcion=fecha_matricula, estado='CURSANDO')
                inscripcion.full_clean()
                inscripcion.save()
                por_curso[curso.pk] = inscripcion
        return matricula, [por_curso[c.pk] for c in cursos], existente is None


def firma_calendario(curso, sesiones):
    datos = {'curso': curso.pk, 'maestro': curso.maestro_id, 'inicio': str(curso.fecha_inicio),
             'fin': str(curso.fecha_fin), 'estado': curso.estado,
             'sesiones': [{f.attname: str(getattr(s, f.attname)) for f in s._meta.local_fields}
                          for s in sesiones]}
    digest = hashlib.sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()
    return signing.Signer(salt='vidasys-calendario').sign(digest)


def propuesta(fecha, frecuencia, hora, duracion, intervalo=None):
    dias = {'semanal': 7, 'quincenal': 14}.get(frecuencia)
    if frecuencia == 'personalizada':
        dias = intervalo
    if not dias or dias < 1 or duracion < 1:
        raise ValidationError('Indique expresamente la frecuencia, la duración y el intervalo personalizado si corresponde.')
    inicio = datetime.combine(fecha, hora)
    fin = inicio + timedelta(minutes=duracion)
    if fin.date() != inicio.date():
        raise ValidationError('La sesión debe terminar el mismo día y después de la hora de inicio.')
    return [{'numero_clase': n, 'fecha': fecha + timedelta(days=(n-1)*dias),
             'hora_inicio': hora, 'hora_fin': fin.time()} for n in range(1, 7)]


def docente_del_curso(curso, usuario):
    if not usuario.is_active or usuario.rol != 'MAESTRO' or curso.maestro.usuario_id != usuario.pk:
        raise ValidationError('No puede administrar el calendario de este curso.')


def guardar_calendario(curso_id, usuario, filas, revision):
    with transaction.atomic():
        curso = Curso.objects.select_for_update().get(pk=curso_id)
        docente_del_curso(curso, usuario)
        sesiones = list(SesionClase.objects.select_for_update().filter(curso=curso).order_by('numero_clase'))
        if firma_calendario(curso, sesiones) != revision:
            raise ValidationError('El calendario cambió. Genere una propuesta nueva; no se sobrescribió ninguna sesión.')
        if curso.estado in ('FINALIZADO','CANCELADO'):
            raise ValidationError('El curso está cerrado o cancelado.')
        if len(filas) != 6 or [f['numero_clase'] for f in filas] != list(range(1,7)):
            raise ValidationError('La propuesta debe contener exactamente las seis clases ordinarias.')
        existentes = {s.numero_clase: s for s in sesiones}
        nuevas = []
        for fila in filas:
            n = fila['numero_clase']
            if n in existentes:
                if any(getattr(existentes[n], campo) != fila[campo] for campo in ('fecha','hora_inicio','hora_fin')):
                    raise ValidationError('No se pueden modificar sesiones existentes desde la propuesta.')
                continue
            if not curso.fecha_inicio <= fila['fecha'] <= curso.fecha_fin:
                raise ValidationError(f'La clase {n} queda fuera del período del curso. Ajuste la propuesta.')
            sesion = SesionClase(curso=curso, estado='PROGRAMADA', **fila)
            sesion.full_clean()
            nuevas.append(sesion)
        for sesion in nuevas:
            sesion.save()
        return len(nuevas)


def requisitos_cierre(curso):
    anterior = curso.estado
    try:
        curso.estado = 'FINALIZADO'
        curso.full_clean()
        return []
    except ValidationError as error:
        return error.messages
    finally:
        curso.estado = anterior


def cerrar_curso(curso_id, usuario, revision):
    with transaction.atomic():
        curso = Curso.objects.select_for_update().get(pk=curso_id)
        docente_del_curso(curso, usuario)
        sesiones = list(SesionClase.objects.select_for_update().filter(curso=curso).order_by('numero_clase'))
        if firma_calendario(curso, sesiones) != revision:
            raise ValidationError('El curso o las sesiones cambiaron. Revise nuevamente el cierre.')
        if curso.estado == 'CANCELADO':
            raise ValidationError('No se puede finalizar un curso cancelado.')
        if curso.estado != 'FINALIZADO':
            curso.estado = 'FINALIZADO'
            curso.save()
        return curso


def autorizar_extra(sesion, usuario):
    with transaction.atomic():
        actor = Usuario.objects.select_for_update().get(pk=usuario.pk)
        if not actor.is_active or actor.rol != 'DIRECTORA':
            raise ValidationError('Solo Dirección autenticada y activa puede autorizar clases extraordinarias.')
        curso = Curso.objects.select_for_update().get(pk=sesion.curso_id)
        if curso.estado in ('FINALIZADO','CANCELADO') or sesion.pk or sesion.numero_clase not in (7,8):
            raise ValidationError('No se puede crear esta clase extraordinaria ni sobrescribir sesiones existentes.')
        sesion.usuario_autoriza = actor
        sesion.fecha_autorizacion = timezone.now()
        sesion.save()
        return sesion
