"""Caja por operador. Orden: usuario -> caja -> estudiante -> obligaciones -> convenio/cuotas -> pago -> solicitud.

Una anulación administrativa no es una salida física de efectivo. No se registran
ni se simulan devoluciones; los cierres guardan una fotografía de las entradas reales.
"""
from decimal import Decimal, InvalidOperation
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from core.models import Usuario
from .models import Caja, MovimientoCaja


OPERADORES = ('SECRETARIA', 'ADMINISTRADOR')
LECTORES = (*OPERADORES, 'DIRECTORA')


def actor_bloqueado(usuario, roles):
    actor = Usuario.objects.select_for_update().get(pk=usuario.pk)
    if not actor.is_active or actor.rol not in roles:
        raise PermissionDenied('Su cuenta no puede realizar esta operación de caja o anulaciones.')
    return actor


def dinero(valor):
    try:
        numero = Decimal(str(valor))
        if not numero.is_finite() or numero < 0 or numero > Decimal('9999999999.99') or numero != numero.quantize(Decimal('.01')):
            raise ValueError
    except (ValueError, TypeError, InvalidOperation):
        raise ValidationError('Indique un importe no negativo con hasta dos decimales.')
    return numero.quantize(Decimal('.01'))


def abrir(*, usuario, clave, fondo, observaciones=''):
    fondo = dinero(fondo)
    observaciones = observaciones.strip()
    if len(observaciones) > 4000:
        raise ValidationError('Las observaciones admiten hasta 4000 caracteres.')
    with transaction.atomic():
        actor = actor_bloqueado(usuario, OPERADORES)
        previa = Caja.objects.filter(clave=clave).first()
        if previa:
            if previa.operador_id != actor.pk or previa.fondo_inicial != fondo or previa.observaciones != observaciones:
                raise ValidationError('La clave de apertura ya se utilizó con otros datos.')
            return previa
        if Caja.objects.filter(operador=actor, estado='ABIERTA').exists():
            raise ValidationError('Ya tiene una caja abierta. Consúltela antes de abrir otra.')
        return Caja.objects.create(operador=actor, clave=clave, fondo_inicial=fondo, observaciones=observaciones)


def abierta_bloqueada(usuario, *, exigir=True):
    """El servicio de cobro conserva el bloqueo hasta insertar pago Y movimiento."""
    caja = Caja.objects.select_for_update().filter(operador=usuario, estado='ABIERTA').first()
    if caja is None and exigir:
        raise ValidationError('Abra su caja en Finanzas → Caja antes de registrar un cobro nuevo.')
    return caja


def totales(caja):
    filas = list(caja.movimientos.select_related('pago','ingreso','egreso').order_by('pk'))
    efectivo = transferencias = anulados = retenido = entradas = salidas = Decimal('0.00')
    academicos = administrativos = egresos = transferidas = egresos_anulados = Decimal('0.00')
    movimientos=[]
    for m in filas:
        origen=m.pago if m.pago_id else m.ingreso if m.ingreso_id else m.egreso
        salida=m.egreso_id is not None
        vigente=origen.estado=='REGISTRADO'
        if m.metodo=='EFECTIVO':
            if salida:
                salidas+=m.importe
                if vigente:egresos+=m.importe
                else:egresos_anulados+=m.importe
            else:
                entradas+=m.importe
                if vigente:
                    efectivo+=m.importe
                    if m.pago_id:academicos+=m.importe
                    else:administrativos+=m.importe
                else:retenido+=m.importe
        elif salida:
            transferidas+=m.importe
        elif vigente:
            transferencias+=m.importe
        if not vigente:anulados+=m.importe
        numero=origen.numero_recibo if m.pago_id else f'ING-{origen.pk:010d}' if m.ingreso_id else origen.numero_egreso
        movimientos.append({'id':m.pk,'pago':m.pago_id,'ingreso':m.ingreso_id,'egreso':m.egreso_id,
            'tipo':'PAGO' if m.pago_id else 'INGRESO' if m.ingreso_id else 'EGRESO',
            'numero':numero,'fecha':m.fecha.isoformat(),'operador':m.operador_id,'metodo':m.metodo,
            'importe':str(m.importe),'referencia':m.referencia,'estado':origen.estado})
    esperado=caja.fondo_inicial+entradas-salidas
    return {'fondo':str(caja.fondo_inicial),'efectivo_vigente':str(efectivo),
        'transferencias_vigentes':str(transferencias),'anulados':str(anulados),
        'efectivo_anulado_retenido':str(retenido),'entradas_efectivo':str(entradas),
        'salidas_efectivo':str(salidas),'esperado':str(esperado),'disponible':str(esperado-retenido),
        'academicos_efectivo':str(academicos),'administrativos_efectivo':str(administrativos),
        'egresos_efectivo':str(egresos),'transferencias_realizadas':str(transferidas),
        'egresos_anulados_efectivo':str(egresos_anulados),
        'ingresos_vigentes':str(efectivo+transferencias),'recibos':len(filas),'movimientos':movimientos}


def preparar_cierre(*, usuario, caja_id, contado, observaciones=''):
    contado = dinero(contado)
    with transaction.atomic():
        actor = actor_bloqueado(usuario, OPERADORES)
        caja = Caja.objects.select_for_update().get(pk=caja_id)
        if caja.operador_id != actor.pk:
            raise PermissionDenied('Solo puede cerrar su propia caja.')
        if caja.estado != 'ABIERTA':
            raise ValidationError('La caja ya está cerrada.')
        foto = totales(caja)
        contenido = {'caja': caja.pk, 'operador': actor.pk, 'contado': str(contado),
                     'observaciones': observaciones.strip(), 'totales': foto}
        return foto, signing.dumps(contenido, salt='caja-cierre')


def cerrar(*, usuario, caja_id, contado, observaciones='', revision):
    contado = dinero(contado)
    observaciones = observaciones.strip()
    if len(observaciones) > 4000:
        raise ValidationError('Las observaciones admiten hasta 4000 caracteres.')
    try:
        firmado = signing.loads(revision, salt='caja-cierre', max_age=7200)
    except signing.BadSignature:
        raise ValidationError('Compare de nuevo el arqueo antes de cerrar.')
    with transaction.atomic():
        actor = actor_bloqueado(usuario, OPERADORES)
        caja = Caja.objects.select_for_update().get(pk=caja_id)
        if caja.operador_id != actor.pk:
            raise PermissionDenied('Solo puede cerrar su propia caja.')
        if caja.estado == 'CERRADA':
            if (firmado.get('caja') == caja.pk and firmado.get('operador') == actor.pk and
                    firmado.get('totales') == caja.cierre and firmado.get('contado') == str(contado) and
                    firmado.get('observaciones') == observaciones and caja.efectivo_contado == contado and
                    caja.observaciones_cierre == observaciones):
                return caja
            raise ValidationError('Este cierre ya se confirmó con otros datos.')
        foto = totales(caja)
        if firmado != {'caja': caja.pk, 'operador': actor.pk, 'contado': str(contado),
                       'observaciones': observaciones, 'totales': foto}:
            raise ValidationError('Hubo movimientos desde la comparación. Revise el arqueo actualizado.')
        caja.estado = 'CERRADA'
        caja.fecha_cierre = timezone.now()
        caja.efectivo_contado = contado
        caja.efectivo_esperado = Decimal(foto['esperado'])
        caja.diferencia = contado - caja.efectivo_esperado
        caja.observaciones_cierre = observaciones
        caja.cierre = foto
        caja.save(update_fields=['estado', 'fecha_cierre', 'efectivo_contado', 'efectivo_esperado',
                                 'diferencia', 'observaciones_cierre', 'cierre'])
        return caja
