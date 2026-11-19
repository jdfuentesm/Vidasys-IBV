"""Cancelaciones autorizadas: bloqueos ordenados y decisión atómica, sin reapertura."""
from django.core.exceptions import ValidationError
from decimal import Decimal

from django.db import transaction, connection
from django.utils import timezone
from .models import Curso, SesionClase, Asistencia, SolicitudAcademica, Maestro, Calificacion, InscripcionCurso
from .bloqueos import bloquear_usuarios
from .flujo import docente_del_curso


def instantanea(curso, sesion):
    return {"curso_estado": curso.estado, "maestro": curso.maestro_id,
            "curso": {f.attname: str(getattr(curso, f.attname)) for f in curso._meta.local_fields},
            "docente_usuario": curso.maestro.usuario_id,
            "ciclo": {f.attname: str(getattr(curso.ciclo, f.attname)) for f in curso.ciclo._meta.local_fields},
            "materia": {f.attname: str(getattr(curso.materia, f.attname)) for f in curso.materia._meta.local_fields},
            "sesion": {f.attname: str(getattr(sesion, f.attname)) for f in sesion._meta.local_fields}}


def validar_cancelacion(curso, sesion):
    if sesion.curso_id != curso.pk or curso.estado != "ACTIVO":
        raise ValidationError("La sesión debe pertenecer a un curso activo.")
    if sesion.estado not in ("PROGRAMADA", "SUSPENDIDA"):
        raise ValidationError("Solo se cancelan sesiones programadas o suspendidas.")
    curso.full_clean()
    sesion.full_clean()
    if not curso.fecha_inicio <= sesion.fecha <= curso.fecha_fin:
        raise ValidationError("La sesión debe estar dentro del período del curso.")
    if Asistencia.objects.filter(sesion=sesion).exists():
        raise ValidationError("La sesión tiene asistencia registrada; no puede cancelarse.")


def solicitar(*, sesion_id, usuario, motivo, clave):
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Indique el motivo de la solicitud.")
    with transaction.atomic():
        referencia = SesionClase.objects.get(pk=sesion_id)
        actor = bloquear_usuarios(usuario.pk)[usuario.pk]
        curso = Curso.objects.select_for_update().get(pk=referencia.curso_id)
        curso.maestro = Maestro.objects.select_for_update().get(pk=curso.maestro_id)
        docente_del_curso(curso, actor)
        sesion = SesionClase.objects.select_for_update().get(pk=sesion_id)
        previa = SolicitudAcademica.objects.filter(clave=clave).first()
        if previa:
            if previa.solicitante_id != actor.pk or previa.sesion_id != sesion.pk or previa.motivo != motivo:
                raise ValidationError("La clave ya se utilizó con otros datos.")
            return previa
        validar_cancelacion(curso, sesion)
        if SolicitudAcademica.objects.filter(sesion=sesion, estado="PENDIENTE").exists():
            raise ValidationError("Esta sesión ya tiene una solicitud pendiente.")
        return SolicitudAcademica.objects.create(clave=clave, curso=curso, sesion=sesion,
            solicitante=actor, motivo=motivo, anteriores=instantanea(curso, sesion),
            propuestos={"estado": "CANCELADA"})


def decidir(*, solicitud_id, usuario, decision, motivo=""):
    motivo = motivo.strip()
    if decision not in ("APROBADA", "RECHAZADA") or (decision == "RECHAZADA" and not motivo):
        raise ValidationError("Seleccione una decisión válida e indique el motivo del rechazo.")
    with transaction.atomic():
        referencia = SolicitudAcademica.objects.get(pk=solicitud_id)
        usuarios = bloquear_usuarios(usuario.pk, referencia.solicitante_id)
        actor = usuarios[usuario.pk]
        curso = Curso.objects.select_for_update().get(pk=referencia.curso_id)
        curso.maestro = Maestro.objects.select_for_update().get(pk=curso.maestro_id)
        if not actor.is_active or actor.rol != "DIRECTORA":
            raise ValidationError("Solo Dirección activa puede resolver solicitudes.")
        correccion = referencia.tipo == 'CORRECCION_CALIFICACION'
        if correccion:
            from .correcciones import cargar_destino, instantanea_nota, validar_destino, propuesta_nota
            inscripcion, nota = cargar_destino(curso, referencia.inscripcion_id)
            sesion = None
        else:
            sesion = SesionClase.objects.select_for_update().get(pk=referencia.sesion_id)
        solicitud = SolicitudAcademica.objects.select_for_update().get(pk=solicitud_id)
        if solicitud.estado != "PENDIENTE":
            if solicitud.estado != decision or solicitud.motivo_decision != motivo:
                raise ValidationError("La solicitud ya fue resuelta con otros datos.")
            return solicitud
        if decision == "APROBADA" and correccion:
            # Único punto de escritura excepcional: registros obtenidos y bloqueados
            # dentro de esta transacción, sin aceptar instancias aportadas por un llamador.
            if (not connection.in_atomic_block or solicitud.estado != 'PENDIENTE' or
                    not actor.is_active or actor.rol != 'DIRECTORA' or
                    solicitud.tipo != 'CORRECCION_CALIFICACION' or
                    solicitud.inscripcion_id != inscripcion.pk or solicitud.curso_id != curso.pk):
                raise ValidationError('No se cumplen las precondiciones de la decisión autorizada.')
            docente_del_curso(curso, usuarios[solicitud.solicitante_id])
            if nota is None or solicitud.anteriores != instantanea_nota(curso, inscripcion, nota):
                raise ValidationError('Solicitud obsoleta: los datos cambiaron. Rechace y presente una nueva solicitud.')
            validar_destino(curso, inscripcion, nota)
            propuesta = propuesta_nota(nota, solicitud.propuestos.get('componentes', {}))
            if propuesta != solicitud.propuestos:
                raise ValidationError('La propuesta no coincide con el cálculo del servidor.')
            cambios = {c: Decimal(v) for c, v in propuesta['componentes'].items()}
            cambios.update(nota_final=Decimal(propuesta['nota_final']), estado=propuesta['estado'])
            if Calificacion.objects.filter(pk=nota.pk, inscripcion=inscripcion).update(**cambios) != 1:
                raise ValidationError('No se pudo actualizar la calificación esperada.')
            if InscripcionCurso.objects.filter(pk=inscripcion.pk, curso=curso).update(estado=propuesta['estado']) != 1:
                raise ValidationError('No se pudo actualizar la inscripción esperada.')
            nota.refresh_from_db()
            inscripcion.refresh_from_db()
            solicitud.aplicados = instantanea_nota(curso, inscripcion, nota)
            solicitud.aplicados['ultima_correccion'] = solicitud.pk
        elif decision == "APROBADA":
            solicitante = usuarios[solicitud.solicitante_id]
            docente_del_curso(curso, solicitante)
            if solicitud.anteriores != instantanea(curso, sesion):
                raise ValidationError("Solicitud obsoleta: los datos cambiaron. Rechace y solicite una nueva revisión.")
            validar_cancelacion(curso, sesion)
            if solicitud.propuestos != {"estado": "CANCELADA"}:
                raise ValidationError("Propuesta de cancelación inválida.")
            sesion.estado = "CANCELADA"
            sesion.save(update_fields=["estado"])
            solicitud.aplicados = instantanea(curso, sesion)
        solicitud.estado = decision
        solicitud.directora = actor
        solicitud.fecha_decision = timezone.now()
        solicitud.motivo_decision = motivo
        solicitud.save(update_fields=["estado", "directora", "fecha_decision", "motivo_decision", "aplicados"])
        return solicitud


def bloqueo_cancelacion(curso, sesion):
    """Mensaje de consulta; el servicio revalida siempre bajo bloqueo."""
    try:
        validar_cancelacion(curso, sesion)
    except ValidationError as error:
        return " ".join(error.messages)
    if SolicitudAcademica.objects.filter(sesion=sesion, estado="PENDIENTE").exists():
        return "Esta sesión ya tiene una solicitud pendiente. Consulte su estado en Mis solicitudes académicas."
    return ""
