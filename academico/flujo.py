"""Operaciones académicas integradas. Sin señales, DDL ni cambios de docentes."""
import hashlib
import json
from datetime import datetime, timedelta

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Usuario
from .bloqueos import bloquear_usuarios
from .models import Asistencia, Calificacion, Maestro, CicloAcademico, Curso, Estudiante, InscripcionCurso, Materia, Matricula, SesionClase


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
        if existente is None:
            from financiero.servicios import generar_obligaciones
            generar_obligaciones(matricula)
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


def pendientes_asistencia(curso):
    """Solo sesiones impartidas durante la vigencia de cada inscripción.

    Un cierre por inasistencia no habilita registros posteriores. Sus pendientes
    anteriores se informan para revisión de Dirección, sin reabrir la inscripción.
    """
    sesiones = list(SesionClase.objects.filter(curso=curso, estado='IMPARTIDA').order_by('fecha', 'numero_clase'))
    inscripciones = list(InscripcionCurso.objects.filter(curso=curso).select_related('matricula__estudiante'))
    registros = {(a.inscripcion_id, a.sesion_id): a.estado_asistencia
                 for a in Asistencia.objects.filter(inscripcion__curso=curso, sesion__curso=curso)}
    filas = []
    errores = []
    estados_validos = dict(Asistencia.ESTADOS_ASISTENCIA)
    for inscripcion in inscripciones:
        injustificadas = sum(estado == 'AUSENTE_INJUSTIFICADA'
                             for (pk, _), estado in registros.items() if pk == inscripcion.pk)
        cerrada = inscripcion.estado == 'REPROBADA_POR_INASISTENCIA'
        if cerrada and (inscripcion.fecha_cierre is None or injustificadas < 2):
            errores.append(f'{inscripcion.matricula.estudiante}: cierre por inasistencia inconsistente; requiere revisión de Dirección.')
        if inscripcion.estado == 'CURSANDO' and injustificadas >= 2:
            errores.append(f'{inscripcion.matricula.estudiante}: dos ausencias injustificadas sin cierre correspondiente; requiere revisión de Dirección.')
    for sesion in sesiones:
        faltantes = []
        for inscripcion in inscripciones:
            cerrada = inscripcion.estado == 'REPROBADA_POR_INASISTENCIA'
            if inscripcion.estado != 'CURSANDO' and not cerrada:
                continue  # Otros cierres se rechazan en requisitos_cierre, sin reabrirlos.
            if inscripcion.matricula.estado != 'ACTIVA' and not cerrada:
                continue
            inicio = max(inscripcion.fecha_inscripcion, inscripcion.matricula.fecha_matricula)
            if sesion.fecha < inicio:
                continue
            if cerrada and inscripcion.fecha_cierre and sesion.fecha > inscripcion.fecha_cierre:
                continue
            estado = registros.get((inscripcion.pk, sesion.pk))
            if estado not in estados_validos:
                faltantes.append({'inscripcion': inscripcion,
                                  'requiere_direccion': cerrada,
                                  'sin_registro': estado is None})
        if faltantes:
            filas.append({'sesion': sesion, 'faltantes': faltantes, 'cantidad': len(faltantes)})
    return {'sesiones': filas, 'cantidad': sum(f['cantidad'] for f in filas), 'errores': errores}


def requisitos_cierre(curso):
    if curso.estado == 'FINALIZADO':
        return []
    asistencia = pendientes_asistencia(curso)
    errores = list(asistencia['errores'])
    for fila in asistencia['sesiones']:
        errores.append(f"Clase {fila['sesion'].numero_clase} ({fila['sesion'].fecha}): faltan {fila['cantidad']} registros válidos de asistencia. Revise los pendientes por estudiante.")
    if curso.estado != 'ACTIVO':
        errores.append('El curso debe estar ACTIVO para finalizar.')
    anterior = curso.estado
    try:
        curso.estado = 'FINALIZADO'
        curso.full_clean()
    except ValidationError as error:
        errores.extend(error.messages)
    finally:
        curso.estado = anterior
    for inscripcion in InscripcionCurso.objects.filter(curso=curso).select_related('matricula__estudiante'):
        if inscripcion.matricula.ciclo_id != curso.ciclo_id:
            errores.append(f'{inscripcion.matricula.estudiante}: matrícula de otro ciclo; requiere revisión de Dirección.')
            continue
        if inscripcion.estado == 'REPROBADA_POR_INASISTENCIA':
            continue
        if inscripcion.estado != 'CURSANDO' or inscripcion.matricula.estado != 'ACTIVA':
            errores.append(f'{inscripcion.matricula.estudiante}: cierre previo o matrícula no activa; requiere revisión de Dirección.')
            continue
        nota = Calificacion.objects.filter(inscripcion=inscripcion).first()
        if nota is None:
            errores.append(f'{inscripcion.matricula.estudiante}: faltan calificaciones obligatorias. Complete el libro.')
        else:
            try:
                nota.full_clean(exclude=['nota_final', 'estado', 'fecha_registro'])
            except ValidationError:
                errores.append(f'{inscripcion.matricula.estudiante}: revise los componentes de calificación obligatorios.')
    return errores


def firma_cierre(curso, sesiones):
    datos = {'calendario': firma_calendario(curso, sesiones),
             'inscripciones': list(InscripcionCurso.objects.filter(curso=curso).order_by('pk').values()),
             'notas': list(Calificacion.objects.filter(inscripcion__curso=curso).order_by('pk').values()),
             'asistencias': list(Asistencia.objects.filter(inscripcion__curso=curso).order_by('pk').values())}
    return signing.Signer(salt='vidasys-cierre').sign(hashlib.sha256(json.dumps(datos, default=str, sort_keys=True).encode()).hexdigest())


def cerrar_curso(curso_id, usuario, revision):
    with transaction.atomic():
        curso = Curso.objects.select_for_update().get(pk=curso_id)
        docente_del_curso(curso, usuario)
        Maestro.objects.select_for_update().get(pk=curso.maestro_id, usuario=usuario)
        if curso.estado == 'FINALIZADO':
            return curso
        sesiones = list(SesionClase.objects.select_for_update().filter(curso=curso).order_by('numero_clase'))
        matriculas = InscripcionCurso.objects.filter(curso=curso).values_list('matricula_id', flat=True)
        list(Matricula.objects.filter(pk__in=matriculas).order_by('pk').select_for_update())
        inscripciones = list(InscripcionCurso.objects.filter(curso=curso).order_by('pk').select_for_update())
        list(Asistencia.objects.filter(inscripcion__curso=curso).order_by('pk').select_for_update())
        notas = {n.inscripcion_id: n for n in Calificacion.objects.filter(inscripcion__curso=curso).order_by('pk').select_for_update()}
        if firma_cierre(curso, sesiones) != revision:
            raise ValidationError('El curso, las sesiones, la asistencia o las notas cambiaron. Revise nuevamente el cierre.')
        errores = requisitos_cierre(curso)
        if errores:
            raise ValidationError(errores)
        for inscripcion in inscripciones:
            if inscripcion.estado == 'REPROBADA_POR_INASISTENCIA':
                continue
            nota = notas[inscripcion.pk]
            resultado = nota.calcular_nota()
            estado = Calificacion.estado_para_nota(resultado)
            # Solo el cierre fija resultados definitivos; save() conserva notas provisionales.
            Calificacion.objects.filter(pk=nota.pk).update(nota_final=resultado, estado=estado)
            inscripcion.estado = estado
            inscripcion.fecha_cierre = timezone.localdate()
            inscripcion.motivo_cierre = 'Resultado académico definitivo al cerrar el curso.'
            inscripcion.save(update_fields=['estado', 'fecha_cierre', 'motivo_cierre'])
        curso.estado = 'FINALIZADO'
        curso.save()
        return curso


def resumen_docente(curso):
    sesiones = list(SesionClase.objects.filter(curso=curso).order_by('numero_clase'))
    inscripciones = list(InscripcionCurso.objects.filter(curso=curso, estado='CURSANDO', matricula__estado='ACTIVA'))
    asistencia = pendientes_asistencia(curso)
    notas = Calificacion.objects.filter(inscripcion_id__in=[i.pk for i in inscripciones]).count()
    return {'curso': curso, 'sesiones_pendientes': sum(s.estado in ('PROGRAMADA','SUSPENDIDA') for s in sesiones),
            'sin_programar': max(0, 6-sum(s.numero_clase <= 6 for s in sesiones)),
            'asistencias_pendientes': asistencia['cantidad'] if curso.estado != 'FINALIZADO' else 0,
            'detalle_asistencia': asistencia['sesiones'] if curso.estado != 'FINALIZADO' else [],
            'notas_pendientes': len(inscripciones)-notas, 'errores': requisitos_cierre(curso)}


def actualizar_sesion(curso_id, sesion_id, usuario, datos, revision):
    with transaction.atomic():
        curso = Curso.objects.select_for_update().get(pk=curso_id)
        docente_del_curso(curso, usuario)
        Maestro.objects.select_for_update().get(pk=curso.maestro_id, usuario=usuario)
        if curso.estado != 'ACTIVO':
            raise ValidationError('Solo puede gestionar sesiones de un curso activo.')
        sesiones = list(SesionClase.objects.select_for_update().filter(curso=curso).order_by('numero_clase'))
        if firma_calendario(curso, sesiones) != revision:
            raise ValidationError('El calendario cambió. Recargue antes de guardar.')
        sesion = next((s for s in sesiones if s.pk == sesion_id), None)
        if sesion is None or sesion.estado not in ('PROGRAMADA','SUSPENDIDA'):
            raise ValidationError('La sesión no está disponible para cambios ordinarios. Solicite revisión de Dirección.')
        estado = datos['estado']
        if estado not in ('PROGRAMADA','SUSPENDIDA','IMPARTIDA'):
            raise ValidationError('Estado no autorizado.')
        cambio_fecha = any(getattr(sesion, f) != datos[f] for f in ('fecha','hora_inicio','hora_fin'))
        if (cambio_fecha or estado == 'SUSPENDIDA') and Asistencia.objects.filter(sesion=sesion).exists():
            raise ValidationError('La sesión ya tiene asistencia: no se puede suspender ni reprogramar sin revisión de Dirección.')
        if not curso.fecha_inicio <= datos['fecha'] <= curso.fecha_fin:
            raise ValidationError('La sesión debe quedar dentro del período del curso.')
        if estado == 'IMPARTIDA' and datos['fecha'] > timezone.localdate():
            raise ValidationError('No se puede marcar impartida una sesión futura.')
        if estado == 'IMPARTIDA' and (sesion.estado == 'SUSPENDIDA' or cambio_fecha):
            raise ValidationError('Primero confirme la reprogramación en estado PROGRAMADA; después registre que fue impartida.')
        for campo in ('estado','fecha','hora_inicio','hora_fin'):
            setattr(sesion, campo, datos[campo])
        sesion.save()
        return sesion


def autorizar_extra(sesion, usuario):
    with transaction.atomic():
        actor = bloquear_usuarios(usuario.pk)[usuario.pk]
        if not actor.is_active or actor.rol != 'DIRECTORA':
            raise ValidationError('Solo Dirección autenticada y activa puede autorizar clases extraordinarias.')
        curso = Curso.objects.select_for_update().get(pk=sesion.curso_id)
        if sesion.estado == 'CANCELADA':
            raise ValidationError('La cancelación requiere una solicitud y decisión trazable de Dirección; su implementación está pendiente de aprobación técnica.')
        if curso.estado in ('FINALIZADO','CANCELADO') or sesion.pk or sesion.numero_clase not in (7,8):
            raise ValidationError('No se puede crear esta clase extraordinaria ni sobrescribir sesiones existentes.')
        sesion.usuario_autoriza = actor
        sesion.fecha_autorizacion = timezone.now()
        sesion.save()
        return sesion
