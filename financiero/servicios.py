"""Operaciones financieras atómicas; solo el servicio académico crea matrículas."""
import json
import threading
from decimal import Decimal

from django.core import signing
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from academico.models import Estudiante
from core.models import Usuario
from .calendario import leer, validar
from .consultas import importes
from .models import Obligacion, Pago, DetallePago, ConvenioObligacion, MovimientoCaja
from .caja import abierta_bloqueada


def puede_cobrar(usuario):
    return usuario.is_authenticated and usuario.is_active and usuario.rol in ('SECRETARIA', 'ADMINISTRADOR')


def generar_obligaciones(matricula):
    """Solo para una matrícula nueva; el llamador conserva el bloqueo y transacción."""
    if not connection.in_atomic_block:
        raise RuntimeError('La generación debe pertenecer a la transacción de matrícula.')
    emision, vencimiento, meses, conceptos = validar(matricula.ciclo, leer(matricula.ciclo))
    for concepto, fecha, descripcion in [(conceptos[0], vencimiento, 'Matrícula de ciclo')] + [
            (conceptos[1], fecha, f'Mensualidad {fecha:%Y-%m}') for fecha in meses]:
        if Obligacion.objects.filter(matricula=matricula, concepto=concepto, fecha_vencimiento=fecha).exists():
            raise ValidationError('Existen obligaciones para la matrícula nueva. No se sobrescribieron registros.')
        obligacion = Obligacion(matricula=matricula, concepto=concepto, descripcion=descripcion,
            fecha_emision=emision, fecha_vencimiento=fecha, monto_original=Decimal('20.00'),
            monto_descuento=Decimal('0.00'), estado='PENDIENTE')
        obligacion.full_clean()
        obligacion.save()


def reservar_recibo(usuario, estudiante):
    if not puede_cobrar(usuario):
        raise PermissionDenied
    # Reserva sin insertar pagos incompletos. La secuencia admite huecos por abandono/rollback.
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(pg_get_serial_sequence('pago', 'id_pago'))")
            identificador = cursor.fetchone()[0]
        if identificador is None:
            raise ValidationError('La tabla pago requiere una secuencia para id_pago; revise el esquema antes de cobrar.')
    elif connection.vendor == 'sqlite':
        # Solo usado por la configuración aislada de pruebas; serialización del proceso visual.
        with _reserva_sqlite:
            actual = Pago.objects.aggregate(maximo=Max('pk'))['maximo'] or 0
            global _ultimo_sqlite
            _ultimo_sqlite = max(_ultimo_sqlite, actual) + 1
            identificador = _ultimo_sqlite
    else:
        raise ValidationError('No se admite este motor para reservar recibos.')
    return signing.dumps({'id': identificador, 'usuario': usuario.pk, 'estudiante': estudiante.pk}, salt='pago-recibo')


_reserva_sqlite = threading.Lock()
_ultimo_sqlite = 0


def registrar_pago(*, usuario, estudiante, token, metodo, referencia, aplicaciones):
    if not puede_cobrar(usuario):
        raise PermissionDenied
    try:
        reserva = signing.loads(token, salt='pago-recibo', max_age=7200)
    except signing.BadSignature as error:
        raise ValidationError('El formulario venció o fue alterado. Abra uno nuevo y compruebe el historial antes de cobrar.') from error
    if reserva['usuario'] != usuario.pk or reserva['estudiante'] != estudiante.pk:
        raise ValidationError('El recibo no corresponde a esta cuenta o estudiante.')
    if metodo not in ('EFECTIVO', 'TRANSFERENCIA'):
        raise ValidationError('Seleccione EFECTIVO o TRANSFERENCIA.')
    referencia = (referencia or '').strip()
    if len(referencia) > 100:
        raise ValidationError('La referencia no puede superar 100 caracteres.')
    if not aplicaciones:
        raise ValidationError('Indique al menos una obligación e importe.')
    if len({pk for pk, _ in aplicaciones}) != len(aplicaciones):
        raise ValidationError('Una obligación no puede repetirse en el mismo pago.')
    for _, monto in aplicaciones:
        if not isinstance(monto, Decimal) or not monto.is_finite() or monto <= 0 or monto > Decimal('99999999.99') or monto != monto.quantize(Decimal('.01')):
            raise ValidationError('Los importes deben ser positivos, con hasta dos decimales.')
    total = sum((monto for _, monto in aplicaciones), Decimal('0.00'))
    if total > Decimal('99999999.99'):
        raise ValidationError('El importe total supera la capacidad del registro.')
    with transaction.atomic():
        # Serializa solicitudes del mismo estudiante, incluida una repetición del formulario.
        usuario = Usuario.objects.select_for_update().get(pk=usuario.pk)
        if not puede_cobrar(usuario):
            raise PermissionDenied
        caja = abierta_bloqueada(usuario, exigir=False)
        estudiante = Estudiante.objects.select_for_update().get(pk=estudiante.pk)
        numero = f'IBV-{reserva["id"]:010d}'
        existente = Pago.objects.filter(pk=reserva['id']).first()
        if existente:
            detalles = dict(existente.detalles.values_list('obligacion_id', 'monto_aplicado'))
            if (existente.numero_recibo == numero and existente.estudiante_id == estudiante.pk and
                    existente.usuario_id == usuario.pk and existente.estado == 'REGISTRADO' and
                    existente.metodo_pago == metodo and (existente.referencia or '') == referencia and
                    detalles == dict(aplicaciones)):
                return existente, False
            raise ValidationError('Esta reserva ya fue utilizada con otros datos. Revise el historial; no se modificó el pago.')
        if caja is None:
            raise ValidationError('Abra su caja en Finanzas → Caja antes de registrar un cobro nuevo.')
        obligaciones = list(Obligacion.objects.select_for_update().filter(pk__in=[pk for pk, _ in aplicaciones]).order_by('pk'))
        if len(obligaciones) != len(aplicaciones):
            raise ValidationError('Una obligación ya no está disponible.')
        por_id = {o.pk: o for o in obligaciones}
        for pk, monto in aplicaciones:
            obligacion = por_id[pk]
            if obligacion.matricula.estudiante_id != estudiante.pk or obligacion.estado == 'ANULADA':
                raise ValidationError('La obligación no pertenece al estudiante o está anulada.')
            if ConvenioObligacion.objects.filter(obligacion=obligacion, convenio__estado__in=('ACTIVO', 'CUMPLIDO', 'INCUMPLIDO')).exists():
                raise ValidationError('Esta obligación está cubierta por un convenio. Registre el cobro desde Convenios de pago con desglose por cuota y obligación.')
            _, _, saldo = importes(obligacion)
            if monto > saldo:
                raise ValidationError('El importe supera el saldo disponible. Recargue el estado de cuenta.')
            if not obligacion.concepto.permite_abonos and monto != saldo:
                raise ValidationError('Este concepto no permite abonos: debe pagar el saldo completo.')
        snapshot = {'estudiante': f'{estudiante.codigo_estudiante} · {estudiante.nombres} {estudiante.apellidos}',
            'registrado_por': usuario.numero_usuario,
            'detalles': [{'descripcion': por_id[pk].descripcion,
                         'matricula': por_id[pk].matricula.numero_matricula,
                         'vencimiento': por_id[pk].fecha_vencimiento.isoformat(),
                         'importe': str(monto)} for pk, monto in aplicaciones]}
        pago = Pago(id_pago=reserva['id'], estudiante=estudiante, usuario=usuario, numero_recibo=numero,
                    fecha_pago=timezone.now(), monto_total=total, metodo_pago=metodo, referencia=referencia,
                    estado='REGISTRADO', observaciones='VIDASYS_RECIBO_V1\n' + json.dumps(snapshot, ensure_ascii=False))
        pago.full_clean()
        pago.save(force_insert=True)
        for pk, monto in aplicaciones:
            detalle = DetallePago(pago=pago, obligacion=por_id[pk], monto_aplicado=monto)
            detalle.full_clean()
            detalle.save()
        MovimientoCaja.objects.create(caja=caja, pago=pago, operador=usuario, metodo=metodo, importe=total, referencia=referencia)
        return pago, True
