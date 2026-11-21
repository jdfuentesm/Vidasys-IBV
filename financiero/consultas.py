"""Saldos conforme a scripts SQL 15 y 17; no modifica estados al consultar."""
from decimal import Decimal

from django.db import connection
from django.db.models import Sum
from django.utils import timezone

from .models import DetallePago, Donacion, Obligacion, ConvenioPago

CERO = Decimal('0.00')


def importes(obligacion):
    pagado = DetallePago.objects.filter(obligacion=obligacion, pago__estado='REGISTRADO').aggregate(total=Sum('monto_aplicado'))['total'] or CERO
    donado = Donacion.objects.filter(obligacion=obligacion, estado='RECIBIDA').aggregate(total=Sum('monto'))['total'] or CERO
    saldo = max(obligacion.monto_final - pagado - donado, CERO)
    return pagado, donado, saldo


def solvente(estudiante):
    # Reutiliza directamente las tres reglas y excepciones del SQL existente.
    with connection.cursor() as cursor:
        cursor.execute('SELECT estudiante_esta_solvente(%s, %s)', [estudiante.pk, timezone.localdate()])
        return bool(cursor.fetchone()[0])


def cuenta(estudiante):
    filas = []
    pendientes = CERO
    for obligacion in Obligacion.objects.filter(matricula__estudiante=estudiante).select_related('matricula__ciclo', 'concepto').order_by('fecha_vencimiento', 'pk'):
        pagado, donado, saldo = importes(obligacion)
        anulada = obligacion.estado == 'ANULADA'
        exigible = not anulada and saldo > CERO and obligacion.fecha_vencimiento < timezone.localdate()
        filas.append({'obligacion': obligacion, 'pagado': pagado, 'donado': donado, 'saldo': saldo,
                      'anulada': anulada, 'exigible': exigible,
                      'becas': list(obligacion.aplicaciones_beca.filter(estado='APLICADA').select_related('beca'))})
        if not anulada:
            pendientes += saldo
    return {'filas': filas, 'saldo_total': pendientes, 'solvente': solvente(estudiante),
            'convenios': ConvenioPago.objects.filter(estudiante=estudiante).order_by('-pk')}
