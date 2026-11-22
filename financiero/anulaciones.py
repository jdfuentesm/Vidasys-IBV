"""Único punto institucional de anulación. No borra aplicaciones ni devuelve fondos."""
import json
from decimal import Decimal
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from academico.models import Estudiante
from core.models import Usuario
from .caja import actor_bloqueado
from .consultas import importes, solvente
from .convenios import filas_bloqueadas, resumen
from .models import (Caja, MovimientoCaja, SolicitudAnulacion, Pago, ConvenioPago,
                     ConvenioObligacion, CuotaConvenio, AplicacionPagoCuota, DetallePago)


def _bloquear(usuario, roles, pago_id):
    actor = actor_bloqueado(usuario, roles)
    referencia = Pago.objects.get(pk=pago_id)
    movimiento = MovimientoCaja.objects.filter(pago_id=pago_id).first()
    caja = Caja.objects.select_for_update().get(pk=movimiento.caja_id) if movimiento else None
    estudiante = Estudiante.objects.select_for_update().get(pk=referencia.estudiante_id)
    obligaciones = filas_bloqueadas(estudiante)
    ids = set(AplicacionPagoCuota.objects.filter(pago_id=pago_id).values_list('cuota__convenio_id', flat=True))
    convenios = list(ConvenioPago.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    cuotas = list(CuotaConvenio.objects.select_for_update().filter(convenio_id__in=ids).order_by('pk'))
    pago = Pago.objects.select_for_update().get(pk=pago_id)
    return actor, caja, estudiante, obligaciones, convenios, cuotas, pago, movimiento


def _foto(pago, caja, obligaciones, convenios, cuotas):
    datos = {'pago': {f.attname: getattr(pago, f.attname) for f in pago._meta.local_fields},
        'caja': {'id': caja.pk, 'estado': caja.estado} if caja else None,
        'obligaciones': [dict({f.attname: getattr(o, f.attname) for f in o._meta.local_fields},
            pagado=str(importes(o)[0]), donado=str(importes(o)[1]), saldo=str(importes(o)[2])) for o in obligaciones],
        'detalles': list(DetallePago.objects.filter(pago=pago).order_by('pk').values()),
        'aplicaciones': list(AplicacionPagoCuota.objects.filter(pago=pago).order_by('pk').values()),
        'convenios': [{f.attname: getattr(c, f.attname) for f in c._meta.local_fields} for c in convenios],
        'cuotas': [{f.attname: getattr(c, f.attname) for f in c._meta.local_fields} for c in cuotas]}
    return json.loads(json.dumps(datos, default=str, sort_keys=True))


def _validar(pago, caja, obligaciones, convenios, cuotas, movimiento):
    if pago.estado != 'REGISTRADO':
        raise ValidationError('Solo se anulan pagos registrados.')
    if caja is None or movimiento is None:
        raise ValidationError('Recibo histórico sin caja: anulación bloqueada hasta definir su tratamiento institucional.')
    if caja.estado != 'ABIERTA':
        raise ValidationError('La caja está cerrada. Su anulación requiere una política de ajustes posterior al cierre aún no autorizada.')
    if pago.metodo_pago == 'EFECTIVO':
        from .caja import totales
        if Decimal(totales(caja)['disponible']) < pago.monto_total:
            raise ValidationError('El pago respalda desembolsos posteriores. No hay efectivo disponible para reservar su anulación.')
    if (movimiento.operador_id != pago.usuario_id or movimiento.importe != pago.monto_total or
            movimiento.metodo != pago.metodo_pago or movimiento.referencia != (pago.referencia or '')):
        raise ValidationError('El movimiento y el recibo no coinciden. Se requiere revisión.')
    detalles = list(pago.detalles.all())
    por_id = {o.pk: o for o in obligaciones}
    if (not detalles or sum((d.monto_aplicado for d in detalles), Decimal('0')) != pago.monto_total or
            any(d.obligacion_id not in por_id or por_id[d.obligacion_id].estado == 'ANULADA' for d in detalles)):
        raise ValidationError('Las aplicaciones originales son inconsistentes; no se reparan automáticamente.')
    for d in detalles:
        o = por_id[d.obligacion_id]
        pagado, donado, _ = importes(o)
        if pagado + donado > o.monto_final:
            raise ValidationError('Existen importes incompatibles o pagos excedentes. Se requiere revisión; no se crean créditos.')
    ids = {c.pk for c in convenios}
    if len(ids) > 1 or any(c.estado not in ('ACTIVO', 'CUMPLIDO', 'INCUMPLIDO') for c in convenios):
        raise ValidationError('El convenio tiene un estado incompatible con la anulación.')
    enlaces = ConvenioObligacion.objects.filter(obligacion_id__in=[d.obligacion_id for d in detalles]).exclude(convenio__estado='CANCELADO')
    if any(e.convenio_id not in ids for e in enlaces):
        raise ValidationError('Hay un convenio posterior incompatible con este pago. No se redistribuyen saldos.')
    aplicaciones = list(pago.aplicaciones_cuotas.all())
    if ids:
        c = convenios[0]
        if c.estudiante_id != pago.estudiante_id or any(q.estado == 'ANULADA' for q in cuotas):
            raise ValidationError('El convenio o sus cuotas ya no son compatibles.')
        originales = list(c.obligaciones_incluidas.values_list('obligacion_id', flat=True))
        if any(pk not in por_id or por_id[pk].estado == 'ANULADA' for pk in originales):
            raise ValidationError('Las obligaciones del convenio cambiaron.')
        if (any(d.obligacion_id not in originales for d in detalles) or
                sum((a.monto_aplicado for a in aplicaciones), Decimal('0')) != pago.monto_total or
                resumen(c)['saldo'] != sum((importes(por_id[pk])[2] for pk in originales), Decimal('0'))):
            raise ValidationError('Los saldos de cuotas y obligaciones no coinciden; se requiere revisión de Dirección.')


def consecuencias(pago):
    return [{'obligacion': d.obligacion, 'importe': d.monto_aplicado,
             'saldo_actual': importes(d.obligacion)[2],
             'saldo_propuesto': importes(d.obligacion)[2] + d.monto_aplicado} for d in pago.detalles.select_related('obligacion')]


def solicitar(*, usuario, pago_id, motivo, clave):
    motivo = motivo.strip()
    if not motivo or len(motivo) > 4000:
        raise ValidationError('Indique el motivo obligatorio de hasta 4000 caracteres.')
    with transaction.atomic():
        actor, caja, estudiante, obligaciones, convenios, cuotas, pago, movimiento = _bloquear(usuario, ('SECRETARIA',), pago_id)
        previa = SolicitudAnulacion.objects.filter(clave=clave).first()
        if previa:
            if previa.solicitante_id != actor.pk or previa.pago_id != pago.pk or previa.motivo != motivo:
                raise ValidationError('La clave ya se utilizó con otros datos.')
            return previa
        if SolicitudAnulacion.objects.filter(pago=pago, estado='PENDIENTE').exists():
            raise ValidationError('Este pago ya tiene una solicitud pendiente. Consulte su historial.')
        _validar(pago, caja, obligaciones, convenios, cuotas, movimiento)
        return SolicitudAnulacion.objects.create(clave=clave, pago=pago, solicitante=actor, motivo=motivo,
            anteriores=_foto(pago, caja, obligaciones, convenios, cuotas))


def previsualizar(*, usuario, solicitud_id, observaciones=''):
    with transaction.atomic():
        ref = SolicitudAnulacion.objects.get(pk=solicitud_id)
        actor, caja, estudiante, obligaciones, convenios, cuotas, pago, movimiento = _bloquear(usuario, ('DIRECTORA',), ref.pago_id)
        s = SolicitudAnulacion.objects.select_for_update().get(pk=solicitud_id)
        if s.estado != 'PENDIENTE':
            raise ValidationError('La solicitud ya está resuelta.')
        _validar(pago, caja, obligaciones, convenios, cuotas, movimiento)
        actual = _foto(pago, caja, obligaciones, convenios, cuotas)
        if actual != s.anteriores:
            raise ValidationError('Los datos cambiaron desde la solicitud. Rechácela con explicación y registre una nueva si procede.')
        return signing.dumps({'solicitud': s.pk, 'directora': actor.pk, 'foto': actual,
                              'observaciones': observaciones.strip()}, salt='anulacion')


def resolver(*, usuario, solicitud_id, decision, observaciones='', revision=''):
    observaciones = observaciones.strip()
    if decision not in ('APROBADA', 'RECHAZADA') or len(observaciones) > 4000 or (decision == 'RECHAZADA' and not observaciones):
        raise ValidationError('El rechazo exige justificación; revise la resolución.')
    with transaction.atomic():
        ref = SolicitudAnulacion.objects.get(pk=solicitud_id)
        actor, caja, estudiante, obligaciones, convenios, cuotas, pago, movimiento = _bloquear(usuario, ('DIRECTORA',), ref.pago_id)
        s = SolicitudAnulacion.objects.select_for_update().get(pk=solicitud_id)
        if s.estado != 'PENDIENTE':
            if s.estado == decision and s.observaciones == observaciones and s.directora_id == actor.pk:
                return s
            raise ValidationError('La solicitud ya tiene otra resolución definitiva.')
        if decision == 'APROBADA':
            solicitante = Usuario.objects.get(pk=s.solicitante_id)
            if not solicitante.is_active or solicitante.rol != 'SECRETARIA':
                raise ValidationError('El solicitante perdió sus permisos. Rechace esta solicitud obsoleta.')
            _validar(pago, caja, obligaciones, convenios, cuotas, movimiento)
            actual = _foto(pago, caja, obligaciones, convenios, cuotas)
            try:
                firmado = signing.loads(revision, salt='anulacion', max_age=7200)
            except signing.BadSignature:
                raise ValidationError('Compare las consecuencias antes de aprobar.')
            if actual != s.anteriores or firmado != {'solicitud': s.pk, 'directora': actor.pk, 'foto': actual, 'observaciones': observaciones}:
                raise ValidationError('La solicitud o los saldos cambiaron. No se anuló el pago.')
            # Único punto de escritura: permisos, bloqueos y comparación dentro de la misma transacción.
            pago.estado = 'ANULADO'
            pago.save(update_fields=['estado'])
            afectados = set(pago.detalles.values_list('obligacion_id', flat=True))
            for o in obligaciones:
                if o.pk in afectados:
                    o.actualizar_estado()
            for cuota in cuotas:
                pagado = cuota.aplicaciones_pago.filter(pago__estado='REGISTRADO').aggregate(total=Sum('monto_aplicado'))['total'] or Decimal('0')
                cuota.estado = 'PAGADA' if pagado == cuota.monto_cuota else 'PENDIENTE'
                cuota.save(update_fields=['estado'])
            for c in convenios:
                por_id = {o.pk: o for o in obligaciones}
                saldo_originales = sum((importes(por_id[pk])[2] for pk in c.obligaciones_incluidas.values_list('obligacion_id', flat=True)), Decimal('0'))
                if resumen(c)['saldo'] != saldo_originales:
                    raise ValidationError('La anulación produciría saldos incompatibles; se revirtió íntegramente.')
                if c.estado == 'CUMPLIDO' and resumen(c)['saldo'] > 0:
                    c.estado = 'ACTIVO'
                c.fecha_actualizacion = timezone.now()
                c.save(update_fields=['estado', 'fecha_actualizacion'])
            s.aplicados = {'datos': _foto(pago, caja, obligaciones, convenios, cuotas),
                           'solvente': solvente(estudiante), 'devolucion': False,
                           'efectivo_retenido': str(pago.monto_total) if pago.metodo_pago == 'EFECTIVO' else '0.00'}
        s.estado = decision
        s.directora = actor
        s.fecha_resolucion = timezone.now()
        s.observaciones = observaciones
        s.save(update_fields=['estado', 'directora', 'fecha_resolucion', 'observaciones', 'aplicados'])
        return s
