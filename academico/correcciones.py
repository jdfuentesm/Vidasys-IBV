"""Corrección excepcional de una nota definitiva, sin reapertura ni asistencia."""
import json
from decimal import Decimal, InvalidOperation

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction

from .bloqueos import bloquear_usuarios
from .flujo import docente_del_curso
from .models import (Asistencia, Calificacion, Curso, InscripcionCurso, Maestro,
                     Matricula, SolicitudAcademica)

TIPO = 'CORRECCION_CALIFICACION'


def campos(registro):
    return {f.attname: str(getattr(registro, f.attname)) for f in registro._meta.local_fields}


def instantanea_nota(curso, inscripcion, nota):
    return {'curso': campos(curso), 'maestro': {'id': curso.maestro_id, 'usuario': curso.maestro.usuario_id},
            'ciclo': campos(curso.ciclo), 'materia': campos(curso.materia),
            'matricula': campos(inscripcion.matricula), 'inscripcion': campos(inscripcion),
            'calificacion': campos(nota),
            'asistencias': [campos(a) for a in Asistencia.objects.filter(inscripcion=inscripcion).order_by('pk')],
            'ultima_correccion': SolicitudAcademica.objects.filter(inscripcion=inscripcion,
                tipo=TIPO, estado='APROBADA').order_by('-pk').values_list('pk', flat=True).first()}


def firma_nota(curso, inscripcion, nota):
    return signing.Signer(salt='vidasys-correccion-nota').sign(
        json.dumps(instantanea_nota(curso, inscripcion, nota), sort_keys=True))


def validar_destino(curso, inscripcion, nota):
    if curso.estado != 'FINALIZADO' or inscripcion.curso_id != curso.pk:
        raise ValidationError('La corrección requiere una inscripción del curso finalizado.')
    if inscripcion.matricula.estado != 'ACTIVA' or inscripcion.matricula.ciclo_id != curso.ciclo_id:
        raise ValidationError('La matrícula debe estar activa y corresponder al ciclo del curso.')
    if inscripcion.estado == 'REPROBADA_POR_INASISTENCIA' or Asistencia.objects.filter(
            inscripcion=inscripcion, estado_asistencia='AUSENTE_INJUSTIFICADA').count() >= 2:
        raise ValidationError('No se corrigen notas de inscripciones con reprobación por inasistencia o dos ausencias injustificadas.')
    if nota is None:
        raise ValidationError('No existe una calificación definitiva. No se crearán notas faltantes.')
    if nota.inscripcion_id != inscripcion.pk or not nota.fecha_registro or not inscripcion.fecha_cierre:
        raise ValidationError('El registro académico es inconsistente; requiere revisión institucional.')
    nota.full_clean(exclude=['nota_final', 'estado', 'fecha_registro'])
    resultado = nota.calcular_nota()
    estado = Calificacion.estado_para_nota(resultado)
    if nota.nota_final != resultado or nota.estado != estado or inscripcion.estado != estado:
        raise ValidationError('La nota y el resultado de inscripción no son definitivos y coherentes. No se repararán automáticamente.')
    curso.full_clean()


def propuesta_nota(nota, componentes):
    if set(componentes) != set(Calificacion.COMPONENTES):
        raise ValidationError('Indique exclusivamente los nueve componentes de calificación.')
    candidata = Calificacion(pk=nota.pk, inscripcion=nota.inscripcion,
        fecha_registro=nota.fecha_registro, estado=nota.estado, nota_final=nota.nota_final,
        observaciones=nota.observaciones)
    candidata._state.adding = False
    candidata._state.db = nota._state.db
    for campo in Calificacion.COMPONENTES:
        try:
            valor = Decimal(str(componentes[campo]))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError('Ingrese componentes numéricos válidos.')
        setattr(candidata, campo, valor)
    candidata.full_clean(exclude=['nota_final', 'estado', 'fecha_registro'])
    if all(getattr(candidata, c) == getattr(nota, c) for c in Calificacion.COMPONENTES):
        raise ValidationError('La propuesta debe cambiar al menos un componente.')
    final = candidata.calcular_nota()
    return {'componentes': {c: str(getattr(candidata, c)) for c in Calificacion.COMPONENTES},
            'nota_final': str(final), 'estado': Calificacion.estado_para_nota(final)}


def cargar_destino(curso, inscripcion_id):
    previa = InscripcionCurso.objects.get(pk=inscripcion_id)
    matricula = Matricula.objects.select_for_update().get(pk=previa.matricula_id)
    inscripcion = InscripcionCurso.objects.select_for_update().get(pk=inscripcion_id)
    if inscripcion.matricula_id != matricula.pk or inscripcion.curso_id != curso.pk:
        raise ValidationError('Las relaciones académicas cambiaron. Recargue la solicitud.')
    inscripcion.matricula = matricula
    inscripcion.curso = curso
    list(Asistencia.objects.select_for_update().filter(inscripcion=inscripcion).order_by('pk'))
    nota = Calificacion.objects.select_for_update().filter(inscripcion=inscripcion).first()
    if nota is not None:
        nota.inscripcion = inscripcion
    return inscripcion, nota


def solicitar_correccion(*, inscripcion_id, usuario, motivo, clave, componentes, revision):
    motivo = motivo.strip()
    if not motivo or len(motivo) > 4000:
        raise ValidationError('Indique un motivo de hasta 4000 caracteres.')
    with transaction.atomic():
        referencia = InscripcionCurso.objects.get(pk=inscripcion_id)
        actor = bloquear_usuarios(usuario.pk)[usuario.pk]
        curso = Curso.objects.select_for_update().get(pk=referencia.curso_id)
        curso.maestro = Maestro.objects.select_for_update().get(pk=curso.maestro_id)
        docente_del_curso(curso, actor)
        inscripcion, nota = cargar_destino(curso, inscripcion_id)
        anterior = SolicitudAcademica.objects.filter(clave=clave).first()
        if anterior:
            # Reenvíos idénticos no recalculan contra una nota ya corregida.
            try:
                valores = {c: Decimal(str(v)) for c, v in componentes.items()}
                previos = {c: Decimal(v) for c, v in anterior.propuestos.get('componentes', {}).items()}
            except (InvalidOperation, ValueError, TypeError):
                raise ValidationError('Componentes inválidos para el reintento.')
            if (anterior.tipo != TIPO or anterior.inscripcion_id != inscripcion_id or
                    anterior.solicitante_id != actor.pk or anterior.motivo != motivo or valores != previos):
                raise ValidationError('La clave ya se utilizó con otros datos.')
            return anterior
        validar_destino(curso, inscripcion, nota)
        if revision != firma_nota(curso, inscripcion, nota):
            raise ValidationError('Los datos cambiaron. Recargue y compare nuevamente antes de solicitar.')
        propuesta = propuesta_nota(nota, componentes)
        if SolicitudAcademica.objects.filter(tipo=TIPO, inscripcion=inscripcion, estado='PENDIENTE').exists():
            raise ValidationError('Ya existe una corrección pendiente para esta inscripción.')
        return SolicitudAcademica.objects.create(tipo=TIPO, inscripcion=inscripcion,
            curso=curso, solicitante=actor, clave=clave, motivo=motivo,
            anteriores=instantanea_nota(curso, inscripcion, nota), propuestos=propuesta)
