"""F5: servicios institucionales. Orden: usuario -> caja -> origen/categoría -> solicitud.
Los documentos se insertan en la misma transacción; una anulación no devuelve fondos.
"""
import json
import re
import unicodedata
from decimal import Decimal
from django.core import signing
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction, connection
from django.db.models import Max
from django.utils import timezone
from . import caja, comprobantes
from .models import (Ingreso, Egreso, CategoriaIngreso, CategoriaEgreso, RegistroIngreso,
    SolicitudEgreso, DesembolsoEgreso, SolicitudAnulacionOperacion, MovimientoCaja, Caja)
from core.models import Usuario


def texto(valor, maximo=4000, obligatorio=False):
    valor=(valor or '').strip()
    if len(valor)>maximo or (obligatorio and not valor):raise ValidationError('Complete los campos obligatorios dentro de su longitud máxima.')
    return valor


def importe(valor):
    numero=caja.dinero(valor)
    if numero<=0 or numero>Decimal('99999999.99'):raise ValidationError('El importe debe ser positivo y no superar USD 99999999.99.')
    return numero


def administrativo(valor):
    normal=''.join(c for c in unicodedata.normalize('NFKD',valor.lower()) if not unicodedata.combining(c))
    if re.search(r'\b(matriculas?|mensualidad(?:es)?|convenios?|donacion(?:es)?|donativos?|padrinazgos?)\b',normal):
        raise ValidationError('Use el circuito correspondiente: no se cobran matrículas, mensualidades, convenios, donaciones ni padrinazgos desde ingresos administrativos.')


def _categoria(tipo,pk):
    modelo=CategoriaIngreso if tipo=='INGRESO' else CategoriaEgreso
    c=modelo.objects.select_for_update().get(pk=pk)
    if c.estado!='ACTIVO':raise ValidationError('La categoría está inactiva.')
    if tipo=='INGRESO':administrativo(c.nombre)
    return c


def _pago(metodo,referencia,fecha):
    referencia=texto(referencia,100)
    if metodo not in ('EFECTIVO','TRANSFERENCIA'):raise ValidationError('Método inválido.')
    if not hasattr(fecha,'tzinfo') or timezone.is_naive(fecha) or fecha>timezone.now():raise ValidationError('Indique una fecha efectiva válida, con zona horaria y no futura.')
    return referencia


def registrar_ingreso(*,usuario,clave,categoria_id,concepto,origen,monto,metodo,referencia,fecha,observaciones='',archivo=None):
    monto=importe(monto);concepto=texto(concepto,200,True);administrativo(concepto)
    origen=texto(origen,200);observaciones=texto(observaciones);referencia=_pago(metodo,referencia,fecha)
    documento=comprobantes.validar_archivo(archivo)
    datos={'categoria':categoria_id,'concepto':concepto,'origen':origen,'monto':str(monto),'metodo':metodo,
           'referencia':referencia,'fecha':fecha.isoformat(),'observaciones':observaciones,'documento':comprobantes.huella(documento)}
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,caja.OPERADORES)
        c=caja.abierta_bloqueada(actor,exigir=False)
        previo=RegistroIngreso.objects.filter(clave=clave).select_related('ingreso').first()
        if previo:
            if previo.ingreso.usuario_registra_id!=actor.pk or previo.datos!=datos:raise ValidationError('La clave ya se utilizó con otros datos.')
            return previo
        if c is None:raise ValidationError('Abra su propia caja antes de registrar ingresos.')
        if RegistroIngreso.objects.filter(ingreso__usuario_registra=actor,datos=datos).exists():
            raise ValidationError('Ya existe un ingreso con los mismos datos. Revise el historial; no se duplicó.')
        categoria=_categoria('INGRESO',categoria_id)
        ingreso=Ingreso(categoria_ingreso=categoria,usuario_registra=actor,fecha_ingreso=fecha,monto=monto,
            metodo_pago=metodo,referencia=referencia,estado='REGISTRADO',observaciones=observaciones,fecha_creacion=timezone.now())
        ingreso.full_clean();ingreso.save()
        registro=RegistroIngreso.objects.create(clave=clave,ingreso=ingreso,concepto=concepto,origen=origen,
            comprobante=comprobantes.guardar(documento,actor),datos=datos)
        MovimientoCaja.objects.create(caja=c,ingreso=ingreso,operador=actor,metodo=metodo,importe=monto,referencia=referencia)
        return registro


def solicitar_egreso(*,usuario,clave,categoria_id,concepto,beneficiario,monto,justificacion,observaciones='',archivo=None):
    monto=importe(monto);concepto=texto(concepto,200,True);beneficiario=texto(beneficiario,200,True)
    justificacion=texto(justificacion,4000,True);observaciones=texto(observaciones)
    documento=comprobantes.validar_archivo(archivo)
    datos={'categoria':categoria_id,'concepto':concepto,'beneficiario':beneficiario,'monto':str(monto),
           'justificacion':justificacion,'observaciones':observaciones,'documento':comprobantes.huella(documento)}
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,caja.OPERADORES)
        previa=SolicitudEgreso.objects.filter(clave=clave).first()
        if previa:
            if previa.solicitante_id!=actor.pk or previa.datos!=datos:raise ValidationError('La clave ya se utilizó con otros datos.')
            return previa
        categoria=_categoria('EGRESO',categoria_id)
        return SolicitudEgreso.objects.create(clave=clave,categoria=categoria,concepto=concepto,beneficiario=beneficiario,
            monto=monto,justificacion=justificacion,observaciones=observaciones,solicitante=actor,
            comprobante=comprobantes.guardar(documento,actor),datos=datos)


def _validar_solicitud(s):
    actual={'categoria':s.categoria_id,'concepto':s.concepto,'beneficiario':s.beneficiario,
            'monto':str(s.monto),'justificacion':s.justificacion,'observaciones':s.observaciones,
            'documento':s.comprobante.sha256 if s.comprobante_id else None}
    if actual!=s.datos:
        raise ValidationError('La solicitud ya no coincide con sus valores originales; se requiere revisión.')


def decidir_egreso(*,usuario,solicitud_id,decision,resolucion=''):
    resolucion=texto(resolucion)
    if decision not in ('APROBADA','RECHAZADA') or (decision=='RECHAZADA' and not resolucion):raise ValidationError('El rechazo requiere justificación.')
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,('DIRECTORA',))
        referencia=SolicitudEgreso.objects.get(pk=solicitud_id)
        categoria=CategoriaEgreso.objects.select_for_update().get(pk=referencia.categoria_id)
        s=SolicitudEgreso.objects.select_for_update().get(pk=solicitud_id)
        if s.estado!='PENDIENTE':
            if s.estado==decision and s.resolucion==resolucion and s.directora_id==actor.pk:return s
            raise ValidationError('La solicitud ya tiene otra decisión definitiva.')
        if decision=='APROBADA':
            if categoria.estado!='ACTIVO':raise ValidationError('La categoría está inactiva.')
            _validar_solicitud(s)
            solicitante=Usuario.objects.get(pk=s.solicitante_id)
            if not solicitante.is_active or solicitante.rol not in caja.OPERADORES:raise ValidationError('El solicitante perdió sus permisos; rechace la solicitud obsoleta.')
        s.estado=decision;s.directora=actor;s.fecha_resolucion=timezone.now();s.resolucion=resolucion
        s.autorizados={'monto':str(s.monto),'directora':actor.pk,'fecha':s.fecha_resolucion.isoformat(),'resolucion':resolucion,'solicitud':s.datos} if decision=='APROBADA' else {}
        s.save(update_fields=['estado','directora','fecha_resolucion','resolucion','autorizados'])
        return s


def _numero_egreso():
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor:
            cursor.execute("SELECT nextval(pg_get_serial_sequence('egreso', 'id_egreso'))")
            numero=cursor.fetchone()[0]
        if numero is None:raise ValidationError('Egreso requiere una secuencia antes de desembolsar.')
        return numero
    if connection.vendor=='sqlite':return (Egreso.objects.aggregate(n=Max('pk'))['n'] or 0)+1
    raise ValidationError('Motor no admitido.')


def desembolsar(*,usuario,clave,solicitud_id,metodo,referencia,fecha,archivo=None):
    referencia=_pago(metodo,referencia,fecha);documento=comprobantes.validar_archivo(archivo)
    datos={'solicitud':solicitud_id,'metodo':metodo,'referencia':referencia,'fecha':fecha.isoformat(),'documento':comprobantes.huella(documento)}
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,caja.OPERADORES)
        c=caja.abierta_bloqueada(actor,exigir=False)
        ref=SolicitudEgreso.objects.get(pk=solicitud_id)
        # Secretaría opera sus solicitudes; Administración puede ejecutar las autorizadas de cualquier operador.
        if actor.rol=='SECRETARIA' and ref.solicitante_id!=actor.pk:raise PermissionDenied('La solicitud pertenece a otro operador.')
        previo=DesembolsoEgreso.objects.filter(clave=clave).select_related('egreso').first()
        if previo:
            if previo.egreso.usuario_registra_id!=actor.pk or previo.datos!=datos:raise ValidationError('La clave ya se utilizó con otros datos.')
            return previo
        categoria=_categoria('EGRESO',ref.categoria_id)
        s=SolicitudEgreso.objects.select_for_update().get(pk=solicitud_id)
        if c is None:raise ValidationError('Abra su propia caja antes de desembolsar.')
        if s.estado!='APROBADA':raise ValidationError('El egreso no tiene autorización de Dirección.')
        _validar_solicitud(s)
        if s.autorizados!={'monto':str(s.monto),'directora':s.directora_id,'fecha':s.fecha_resolucion.isoformat(),'resolucion':s.resolucion,'solicitud':s.datos}:
            raise ValidationError('La autorización no coincide con sus valores definitivos.')
        if DesembolsoEgreso.objects.filter(solicitud=s).exists():raise ValidationError('El egreso ya fue desembolsado. Consulte el comprobante.')
        if metodo=='EFECTIVO' and Decimal(caja.totales(c)['disponible'])<s.monto:
            raise ValidationError('Efectivo disponible insuficiente. Los importes anulados retenidos no están disponibles.')
        numero=_numero_egreso()
        egreso=Egreso(id_egreso=numero,numero_egreso=f'EG-{numero:010d}',categoria_egreso=categoria,usuario_registra=actor,
            usuario_autoriza=s.directora,fecha_autorizacion=s.fecha_resolucion,fecha_egreso=fecha,concepto=s.concepto,
            monto=s.monto,metodo_pago=metodo,referencia=referencia,tipo_comprobante='INTERNO',estado='REGISTRADO',
            observaciones=s.observaciones,fecha_creacion=timezone.now())
        egreso.full_clean();egreso.save(force_insert=True)
        d=DesembolsoEgreso.objects.create(clave=clave,solicitud=s,egreso=egreso,datos=datos,
            comprobante=comprobantes.guardar(documento,actor))
        MovimientoCaja.objects.create(caja=c,egreso=egreso,operador=actor,metodo=metodo,importe=s.monto,referencia=referencia)
        return d


def _referencia(tipo,pk):
    if tipo=='INGRESO':
        registro=RegistroIngreso.objects.select_related('ingreso').get(pk=pk)
        return registro,registro.ingreso
    if tipo=='EGRESO':
        registro=DesembolsoEgreso.objects.select_related('egreso').get(pk=pk)
        return registro,registro.egreso
    raise ValidationError('Origen inválido.')


def _foto(movimiento):
    return json.loads(json.dumps({f.attname:getattr(movimiento,f.attname) for f in movimiento._meta.local_fields},default=str,sort_keys=True))


def _bloquear_anulacion(usuario,roles,tipo,pk):
    actor=caja.actor_bloqueado(usuario,roles)
    r,ref=_referencia(tipo,pk)
    m=MovimientoCaja.objects.get(**({'ingreso_id':ref.pk} if tipo=='INGRESO' else {'egreso_id':ref.pk}))
    c=Caja.objects.select_for_update().get(pk=m.caja_id)
    origen=type(ref).objects.select_for_update().get(pk=ref.pk)
    return actor,c,r,origen


def _validar_anulacion(c,origen,tipo):
    if c.estado!='ABIERTA':raise ValidationError('Caja cerrada: ajustes posteriores al cierre bloqueados.')
    if origen.estado!='REGISTRADO':raise ValidationError('Solo se anulan movimientos registrados.')
    movimiento=MovimientoCaja.objects.get(**({'ingreso':origen} if tipo=='INGRESO' else {'egreso':origen}))
    if (movimiento.importe!=origen.monto or movimiento.operador_id!=origen.usuario_registra_id or
            movimiento.metodo!=origen.metodo_pago or movimiento.referencia!=(origen.referencia or '')):
        raise ValidationError('El movimiento de caja no coincide con el origen financiero. Se requiere revisión.')
    if tipo=='INGRESO' and origen.metodo_pago=='EFECTIVO' and Decimal(caja.totales(c)['disponible'])<origen.monto:
        raise ValidationError('El ingreso ya respalda desembolsos; anulación bloqueada por efectivo disponible insuficiente.')


def solicitar_anulacion(*,usuario,tipo,registro_id,clave,motivo):
    motivo=texto(motivo,4000,True)
    with transaction.atomic():
        actor,c,r,origen=_bloquear_anulacion(usuario,caja.OPERADORES,tipo,registro_id)
        if origen.usuario_registra_id!=actor.pk:raise PermissionDenied('Solo puede solicitar anulación de sus propios movimientos.')
        previa=SolicitudAnulacionOperacion.objects.filter(clave=clave).first()
        if previa:
            if previa.solicitante_id!=actor.pk or previa.motivo!=motivo or (previa.ingreso_id if tipo=='INGRESO' else previa.desembolso_id)!=r.pk:raise ValidationError('La clave ya se utilizó con otros datos.')
            return previa
        campo='ingreso' if tipo=='INGRESO' else 'desembolso'
        if SolicitudAnulacionOperacion.objects.filter(**{campo:r,'estado':'PENDIENTE'}).exists():raise ValidationError('Ya existe una solicitud de anulación pendiente.')
        _validar_anulacion(c,origen,tipo)
        return SolicitudAnulacionOperacion.objects.create(clave=clave,solicitante=actor,motivo=motivo,anteriores=_foto(origen),**{campo:r})


def decidir_anulacion(*,usuario,solicitud_id,decision,resolucion='',revision='',confirmar=False):
    resolucion=texto(resolucion)
    if decision not in ('APROBADA','RECHAZADA') or (decision=='RECHAZADA' and not resolucion):raise ValidationError('El rechazo requiere justificación.')
    with transaction.atomic():
        ref=SolicitudAnulacionOperacion.objects.get(pk=solicitud_id)
        tipo='INGRESO' if ref.ingreso_id else 'EGRESO';pk=ref.ingreso_id or ref.desembolso_id
        actor,c,r,origen=_bloquear_anulacion(usuario,('DIRECTORA',),tipo,pk)
        s=SolicitudAnulacionOperacion.objects.select_for_update().get(pk=solicitud_id)
        if s.estado!='PENDIENTE':
            if s.estado==decision and s.directora_id==actor.pk and s.resolucion==resolucion:return s
            raise ValidationError('Ya existe otra resolución definitiva.')
        if decision=='APROBADA':
            solicitante=Usuario.objects.get(pk=s.solicitante_id)
            if not solicitante.is_active or solicitante.rol not in caja.OPERADORES:raise ValidationError('El solicitante perdió sus permisos.')
            _validar_anulacion(c,origen,tipo)
            if _foto(origen)!=s.anteriores:raise ValidationError('El movimiento cambió. Rechace la solicitud obsoleta.')
            contenido={'solicitud':s.pk,'directora':actor.pk,'foto':_foto(origen),'disponible':caja.totales(c)['disponible'],'resolucion':resolucion}
            if not confirmar:return signing.dumps(contenido,salt='anulacion-operacion')
            try:firmado=signing.loads(revision,salt='anulacion-operacion',max_age=7200)
            except signing.BadSignature:raise ValidationError('Compare nuevamente antes de confirmar.')
            if firmado!=contenido:raise ValidationError('Los datos o el disponible cambiaron. Compare nuevamente.')
            origen.estado='ANULADO';origen.usuario_anula=actor;origen.fecha_anulacion=timezone.now();origen.motivo_anulacion=s.motivo
            origen.save(update_fields=['estado','usuario_anula','fecha_anulacion','motivo_anulacion'])
            s.aplicados={'movimiento':_foto(origen),'devolucion':False,'recuperacion':False}
        s.estado=decision;s.directora=actor;s.fecha_resolucion=timezone.now();s.resolucion=resolucion
        s.save(update_fields=['estado','directora','fecha_resolucion','resolucion','aplicados'])
        return s


def configurar_categoria(*,usuario,tipo,nombre='',descripcion='',categoria_id=None,estado='ACTIVO'):
    if tipo not in ('INGRESO','EGRESO') or estado not in ('ACTIVO','INACTIVO'):raise ValidationError('Tipo o estado inválido.')
    with transaction.atomic():
        caja.actor_bloqueado(usuario,('ADMINISTRADOR',))
        modelo=CategoriaIngreso if tipo=='INGRESO' else CategoriaEgreso
        if categoria_id:
            categoria=modelo.objects.select_for_update().get(pk=categoria_id)
            categoria.estado=estado
            categoria.save(update_fields=['estado'])
            return categoria
        nombre=texto(nombre,100,True).upper();descripcion=texto(descripcion)
        if tipo=='INGRESO':administrativo(nombre)
        if modelo.objects.filter(nombre__iexact=nombre).exists():raise ValidationError('La categoría ya existe. Active o desactive la existente.')
        datos={'nombre':nombre,'descripcion':descripcion,'estado':estado}
        if tipo=='EGRESO':datos['requiere_autorizacion']=True
        return modelo.objects.create(**datos)
