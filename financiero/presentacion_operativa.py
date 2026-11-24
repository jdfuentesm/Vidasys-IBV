"""Datos de lectura para el cobro F8.3; el servicio original decide cada aplicación."""
from decimal import Decimal
from .models import Caja, ConvenioObligacion


def preparar_cobro(form, datos, usuario):
    por_id = {f['obligacion'].pk: f for f in datos['filas']}
    convenidas = set(ConvenioObligacion.objects.filter(obligacion_id__in=por_id,
        convenio__estado__in=('ACTIVO', 'CUMPLIDO', 'INCUMPLIDO')).values_list('obligacion_id', flat=True))
    filas = []
    for obligacion in form.obligaciones:
        fila = por_id[obligacion.pk]
        filas.append(dict(fila, campo=form[f'importe_{obligacion.pk}'],
            parte=max(fila['saldo']-fila['reserva_padrinazgo'], Decimal('0')),
            en_convenio=obligacion.pk in convenidas))
    return {'cobro_filas': filas, 'saldo_cobro': datos['saldo_total'],
        'caja_cobro': Caja.objects.filter(operador=usuario, estado='ABIERTA').first()}
