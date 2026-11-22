"""Convenios institucionales con distribución explícita de cobros, sin intereses."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from academico.models import Estudiante
from core.models import Usuario
from .consultas import importes, solvente
from .models import (SolicitudConvenio, RevisionConvenio, ConvenioPago, ConvenioObligacion,
                     CuotaConvenio, AplicacionPagoCuota, Obligacion, DetallePago, Donacion, Pago, MovimientoCaja)


def actor_bloqueado(usuario,roles):
    actor=Usuario.objects.select_for_update().get(pk=usuario.pk)
    if not actor.is_active or actor.rol not in roles:raise PermissionDenied('Su cuenta no puede realizar esta operación de convenios.')
    return actor


def condiciones(obligaciones,cuotas):
    if not isinstance(obligaciones,(list,tuple)) or not obligaciones or any(type(pk) is not int or pk<=0 for pk in obligaciones) or len(set(obligaciones))!=len(obligaciones):
        raise ValidationError('Seleccione obligaciones distintas válidas.')
    if not isinstance(cuotas,(list,tuple)) or not 1<=len(cuotas)<=100:
        raise ValidationError('Indique entre una y cien cuotas por formulario.')
    filas=[]
    for fila in cuotas:
        if not isinstance(fila,dict) or set(fila)!={'fecha','monto'}:raise ValidationError('Cuota inválida.')
        try:
            fecha=date.fromisoformat(str(fila['fecha']))
            monto=Decimal(str(fila['monto']))
        except (ValueError,TypeError,InvalidOperation):raise ValidationError('Fecha o importe inválido.')
        if not monto.is_finite() or monto<=0 or monto>Decimal('99999999.99') or monto!=monto.quantize(Decimal('.01')):
            raise ValidationError('Cada cuota requiere un importe positivo con hasta dos decimales.')
        filas.append({'fecha':str(fecha),'monto':str(monto.quantize(Decimal('.01')))})
    return {'obligaciones':sorted(obligaciones),'cuotas':filas}


def filas_bloqueadas(estudiante):
    return list(Obligacion.objects.select_for_update().filter(matricula__estudiante=estudiante).order_by('pk'))


def evaluar(estudiante,obligaciones,condicion,excluir_convenio=None):
    if any(date.fromisoformat(c['fecha'])<timezone.localdate() for c in condicion['cuotas']):
        raise ValidationError('Una nueva cuota no puede vencer antes de la fecha de autorización.')
    por_id={o.pk:o for o in obligaciones};filas=[];total=Decimal('0')
    for pk in condicion['obligaciones']:
        o=por_id.get(pk)
        if o is None or o.matricula.estudiante_id!=estudiante.pk:raise ValidationError('La obligación no pertenece al estudiante.')
        if o.concepto.nombre.strip().upper().replace('Í','I') not in ('MATRICULA','MENSUALIDAD') or o.estado=='ANULADA':
            raise ValidationError(f'Obligación #{pk}: concepto no permitido o cargo anulado.')
        cobertura=ConvenioObligacion.objects.filter(obligacion=o).exclude(convenio__estado='CANCELADO')
        if excluir_convenio is not None:cobertura=cobertura.exclude(convenio_id=excluir_convenio)
        if cobertura.exists():raise ValidationError(f'Obligación #{pk}: ya pertenece a un convenio incompatible.')
        from .aportes import reservada
        if reservada(o)>0:raise ValidationError('La obligación tiene padrinazgo. Dirección debe resolver primero su cobertura.')
        pagado,donado,saldo=importes(o)
        if saldo<=0 or o.estado=='PAGADA':raise ValidationError(f'Obligación #{pk}: no tiene saldo disponible.')
        total+=saldo
        filas.append({'id':pk,'descripcion':o.descripcion,'vencimiento':str(o.fecha_vencimiento),
            'original':str(o.monto_original),'descuento':str(o.monto_descuento),'pagado':str(pagado),
            'donado':str(donado),'saldo':str(saldo),'estado':o.estado,
            'matricula':o.matricula_id,'concepto':o.concepto_id,
            'pagos':list(DetallePago.objects.filter(obligacion=o).order_by('pk').values('pk','pago_id','monto_aplicado','pago__estado')),
            'donaciones':list(Donacion.objects.filter(obligacion=o).order_by('pk').values('pk','monto','estado'))})
    suma=sum((Decimal(c['monto']) for c in condicion['cuotas']),Decimal('0'))
    if suma!=total:raise ValidationError(f'Las cuotas suman USD {suma:.2f}; deben sumar exactamente el saldo USD {total:.2f}. Sin intereses ni recargos.')
    if total>Decimal('99999999.99'):raise ValidationError('El total supera la capacidad del registro.')
    return json.loads(json.dumps({'fecha':str(timezone.localdate()),'estudiante':estudiante.pk,
        'filas':filas,'total':str(total.quantize(Decimal('.01')))},default=str,sort_keys=True))


def solicitar(*,usuario,estudiante_id,obligaciones,cuotas,justificacion,clave):
    condicion=condiciones(obligaciones,cuotas);justificacion=justificacion.strip()
    if not justificacion or len(justificacion)>4000:raise ValidationError('Indique una justificación de hasta 4000 caracteres.')
    with transaction.atomic():
        actor=actor_bloqueado(usuario,('SECRETARIA',))
        estudiante=Estudiante.objects.select_for_update().get(pk=estudiante_id)
        filas=filas_bloqueadas(estudiante)
        previa=SolicitudConvenio.objects.filter(clave=clave).first()
        if previa:
            if previa.solicitante_id!=actor.pk or previa.estudiante_id!=estudiante.pk or previa.propuesta!=condicion or previa.justificacion!=justificacion:
                raise ValidationError('La clave ya se utilizó con otros datos.')
            return previa
        if SolicitudConvenio.objects.filter(estudiante=estudiante,estado='PENDIENTE').exists():raise ValidationError('El estudiante ya tiene una solicitud pendiente.')
        plan=evaluar(estudiante,filas,condicion)
        return SolicitudConvenio.objects.create(clave=clave,estudiante=estudiante,solicitante=actor,
            propuesta=condicion,anteriores=plan,justificacion=justificacion)


def _bloquear_solicitud(usuario,solicitud_id):
    actor=actor_bloqueado(usuario,('DIRECTORA',))
    referencia=SolicitudConvenio.objects.get(pk=solicitud_id)
    estudiante=Estudiante.objects.select_for_update().get(pk=referencia.estudiante_id)
    filas=filas_bloqueadas(estudiante)
    solicitud=SolicitudConvenio.objects.select_for_update().get(pk=solicitud_id)
    return actor,estudiante,filas,solicitud


def previsualizar(*,usuario,solicitud_id,obligaciones,cuotas,motivo=''):
    condicion=condiciones(obligaciones,cuotas)
    with transaction.atomic():
        actor,estudiante,filas,s=_bloquear_solicitud(usuario,solicitud_id)
        if s.estado!='PENDIENTE':raise ValidationError('La solicitud ya está resuelta.')
        plan=evaluar(estudiante,filas,condicion)
        revision=signing.dumps({'solicitud':s.pk,'directora':actor.pk,'condicion':condicion,'plan':plan,'motivo':motivo.strip()},salt='convenio-alta')
        return plan,revision


def resolver(*,usuario,solicitud_id,decision,obligaciones=None,cuotas=None,motivo='',revision=''):
    motivo=motivo.strip()
    if decision not in ('APROBADA','RECHAZADA') or len(motivo)>4000 or (decision=='RECHAZADA' and not motivo):raise ValidationError('Resolución inválida; el rechazo requiere motivo.')
    condicion=condiciones(obligaciones,cuotas) if decision=='APROBADA' else {}
    resolucion={'decision':decision,'condicion':condicion,'motivo':motivo}
    with transaction.atomic():
        actor,estudiante,filas,s=_bloquear_solicitud(usuario,solicitud_id)
        if s.estado!='PENDIENTE':
            if s.estado!=decision or s.resolucion!=resolucion:raise ValidationError('La solicitud ya fue resuelta con otros datos.')
            return s
        if decision=='APROBADA':
            plan=evaluar(estudiante,filas,condicion)
            try:firmado=signing.loads(revision,salt='convenio-alta',max_age=7200)
            except signing.BadSignature:raise ValidationError('Compare nuevamente antes de aprobar.')
            if firmado!={'solicitud':s.pk,'directora':actor.pk,'condicion':condicion,'plan':plan,'motivo':motivo}:raise ValidationError('Los saldos o condiciones cambiaron. No se creó el convenio.')
            convenio=ConvenioPago(estudiante=estudiante,usuario_autoriza=actor,fecha_convenio=timezone.localdate(),
                monto_convenido=Decimal(plan['total']),numero_cuotas=len(condicion['cuotas']),estado='ACTIVO',
                fecha_actualizacion=timezone.now(),observaciones=motivo)
            convenio.full_clean();convenio.save()
            for fila in plan['filas']:
                enlace=ConvenioObligacion(convenio=convenio,obligacion_id=fila['id'],saldo_incluido=Decimal(fila['saldo']))
                enlace.full_clean();enlace.save()
            for n,fila in enumerate(condicion['cuotas'],1):
                cuota=CuotaConvenio(convenio=convenio,numero_cuota=n,fecha_vencimiento=date.fromisoformat(fila['fecha']),monto_cuota=Decimal(fila['monto']),estado='PENDIENTE')
                cuota.full_clean();cuota.save()
            s.convenio=convenio
            s.aplicados={'plan':plan,'solvente':solvente(estudiante)}
        s.estado=decision;s.directora=actor;s.fecha_resolucion=timezone.now();s.resolucion=resolucion
        s.save(update_fields=['estado','directora','fecha_resolucion','resolucion','aplicados','convenio'])
        return s


def resumen(convenio):
    filas=[];abonado=Decimal('0');saldo=Decimal('0');vencidas=0
    for cuota in convenio.cuotas.order_by('numero_cuota'):
        pagado=cuota.aplicaciones_pago.filter(pago__estado='REGISTRADO').aggregate(total=Sum('monto_aplicado'))['total'] or Decimal('0')
        restante=max(cuota.monto_cuota-pagado,Decimal('0')) if cuota.estado!='ANULADA' else Decimal('0')
        abonado+=pagado;saldo+=restante
        vencida=cuota.estado!='ANULADA' and restante>0 and cuota.fecha_vencimiento<timezone.localdate()
        vencidas+=int(vencida)
        filas.append({'cuota':cuota,'abonado':pagado,'saldo':restante,'vencida':vencida})
    return {'convenio':convenio,'filas':filas,'abonado':abonado,'saldo':saldo,'vencidas':vencidas,
            'pagadas':sum(f['saldo']==0 and f['cuota'].estado!='ANULADA' for f in filas),
            'pendientes':sum(f['saldo']>0 for f in filas)}


def _version(convenio):
    return {'convenio':{f.attname:str(getattr(convenio,f.attname)) for f in convenio._meta.local_fields},
            'cuotas':list(convenio.cuotas.order_by('pk').values()),
            'obligaciones':list(convenio.obligaciones_incluidas.order_by('pk').values())}


def revisar(*,usuario,convenio_id,accion,motivo,clave,obligaciones=None,cuotas=None,revision='',confirmar=False):
    motivo=motivo.strip()
    if accion not in ('MODIFICACION','CANCELACION') or not motivo or len(motivo)>4000:raise ValidationError('Seleccione operación y justificación obligatoria.')
    condicion=condiciones(obligaciones,cuotas) if accion=='MODIFICACION' else {}
    with transaction.atomic():
        actor=actor_bloqueado(usuario,('DIRECTORA',))
        ref=ConvenioPago.objects.get(pk=convenio_id)
        estudiante=Estudiante.objects.select_for_update().get(pk=ref.estudiante_id)
        filas=filas_bloqueadas(estudiante)
        convenio=ConvenioPago.objects.select_for_update().get(pk=convenio_id)
        list(convenio.cuotas.select_for_update().order_by('pk'))
        previo=RevisionConvenio.objects.filter(clave=clave).first()
        if previo:
            if previo.convenio_id!=convenio.pk or previo.accion!=accion or previo.motivo!=motivo or previo.directora_id!=actor.pk or previo.aplicados.get('condicion',{})!=condicion:raise ValidationError('La clave ya se utilizó con otros datos.')
            return previo
        if convenio.estado not in ('ACTIVO','INCUMPLIDO'):raise ValidationError('Solo se revisan convenios activos o incumplidos sin movimientos.')
        # No redistribuir pagos existentes ni reinterpretar movimientos anulados.
        if AplicacionPagoCuota.objects.filter(cuota__convenio=convenio).exists():
            raise ValidationError('Este convenio tiene movimientos de pago. Modificación/cancelación bloqueada hasta definir su tratamiento institucional.')
        version=json.loads(json.dumps(_version(convenio),default=str,sort_keys=True))
        if accion=='MODIFICACION':
            plan=evaluar(estudiante,filas,condicion,excluir_convenio=convenio.pk)
        else:
            ids=set(convenio.obligaciones_incluidas.values_list('obligacion_id',flat=True))
            originales=[o for o in filas if o.pk in ids]
            if len(originales)!=len(ids):raise ValidationError('Las obligaciones originales cambiaron de estudiante.')
            detalle=[]
            for o in originales:
                pagado,donado,saldo=importes(o)
                detalle.append({'id':o.pk,'descripcion':o.descripcion,'vencimiento':str(o.fecha_vencimiento),
                    'original':str(o.monto_original),'descuento':str(o.monto_descuento),
                    'pagado':str(pagado),'donado':str(donado),'saldo':str(saldo)})
            plan={'cancelacion':True,'filas':detalle,'total':str(sum((Decimal(f['saldo']) for f in detalle),Decimal('0')))}
        contenido={'convenio':convenio.pk,'directora':actor.pk,'accion':accion,'motivo':motivo,'condicion':condicion,'version':version,'plan':plan,'fecha':str(timezone.localdate())}
        if not confirmar:return {'plan':plan,'revision':signing.dumps(contenido,salt='convenio-revision')}
        try:firmado=signing.loads(revision,salt='convenio-revision',max_age=7200)
        except signing.BadSignature:raise ValidationError('Compare nuevamente la revisión.')
        if firmado!=contenido:raise ValidationError('El convenio cambió. No se modificó nada.')
        convenio.estado='CANCELADO';convenio.usuario_cancela=actor;convenio.fecha_cancelacion=timezone.now();convenio.motivo_cancelacion=motivo;convenio.fecha_actualizacion=timezone.now()
        convenio.full_clean();convenio.save(update_fields=['estado','usuario_cancela','fecha_cancelacion','motivo_cancelacion','fecha_actualizacion'])
        nuevo=None
        if accion=='MODIFICACION':
            nuevo=ConvenioPago(estudiante=estudiante,usuario_autoriza=actor,fecha_convenio=timezone.localdate(),
                monto_convenido=Decimal(plan['total']),numero_cuotas=len(condicion['cuotas']),estado='ACTIVO',
                fecha_actualizacion=timezone.now(),observaciones=motivo)
            nuevo.full_clean();nuevo.save()
            for fila in plan['filas']:
                enlace=ConvenioObligacion(convenio=nuevo,obligacion_id=fila['id'],saldo_incluido=Decimal(fila['saldo']))
                enlace.full_clean();enlace.save()
            for n,fila in enumerate(condicion['cuotas'],1):
                cuota=CuotaConvenio(convenio=nuevo,numero_cuota=n,fecha_vencimiento=date.fromisoformat(fila['fecha']),monto_cuota=Decimal(fila['monto']),estado='PENDIENTE')
                cuota.full_clean();cuota.save()
        # Nueva versión sin borrar cuotas ni enlaces históricos; sin pagos que redistribuir.
        return RevisionConvenio.objects.create(clave=clave,convenio=convenio,nuevo=nuevo,directora=actor,
            accion=accion,motivo=motivo,anteriores=version,
            aplicados={'condicion':condicion,'nuevo':nuevo.pk if nuevo else None,'solvente':solvente(estudiante)})


def _aplicaciones(filas):
    if not isinstance(filas,(list,tuple)) or not filas:raise ValidationError('Indique aplicaciones explícitas a cuotas y obligaciones.')
    resultado={}
    for fila in filas:
        if not isinstance(fila,(list,tuple)) or len(fila)!=2:raise ValidationError('Aplicación inválida.')
        pk,monto=fila
        if type(pk) is not int or pk<=0 or pk in resultado:raise ValidationError('Identificador inválido o repetido.')
        if not isinstance(monto,Decimal) or not monto.is_finite() or monto<=0 or monto>Decimal('99999999.99') or monto!=monto.quantize(Decimal('.01')):
            raise ValidationError('Importes positivos con hasta dos decimales.')
        resultado[pk]=monto
    return resultado


def registrar_abono(*,usuario,convenio_id,token,metodo,referencia,cuotas,obligaciones):
    from .servicios import puede_cobrar
    from .caja import abierta_bloqueada
    if not puede_cobrar(usuario):raise PermissionDenied('Solo Secretaría y Administración pueden cobrar.')
    por_cuota=_aplicaciones(cuotas);por_obligacion=_aplicaciones(obligaciones)
    total=sum(por_cuota.values(),Decimal('0'))
    if total!=sum(por_obligacion.values(),Decimal('0')) or total>Decimal('99999999.99'):
        raise ValidationError('El desglose por obligaciones debe sumar exactamente el abono a cuotas.')
    referencia=(referencia or '').strip()
    if metodo not in ('EFECTIVO','TRANSFERENCIA') or len(referencia)>100:raise ValidationError('Método o referencia inválidos.')
    try:reserva=signing.loads(token,salt='pago-recibo',max_age=7200)
    except signing.BadSignature:raise ValidationError('La reserva de recibo venció o fue alterada. Revise el historial antes de reintentar.')
    with transaction.atomic():
        actor=actor_bloqueado(usuario,('SECRETARIA','ADMINISTRADOR'))
        caja=abierta_bloqueada(actor,exigir=False)
        ref=ConvenioPago.objects.get(pk=convenio_id)
        estudiante=Estudiante.objects.select_for_update().get(pk=ref.estudiante_id)
        if reserva.get('usuario')!=actor.pk or reserva.get('estudiante')!=estudiante.pk:
            raise ValidationError('La reserva no corresponde al usuario y estudiante.')
        filas=filas_bloqueadas(estudiante)
        convenio=ConvenioPago.objects.select_for_update().get(pk=convenio_id)
        registros=list(convenio.cuotas.select_for_update().order_by('pk'))
        numero=f'IBV-{reserva["id"]:010d}'
        previo=Pago.objects.filter(pk=reserva['id']).first()
        if previo:
            try:snapshot=json.loads((previo.observaciones or '').split('\n',1)[1])
            except (ValueError,IndexError):snapshot={}
            if (snapshot.get('convenio')==convenio.pk and previo.estudiante_id==estudiante.pk and previo.usuario_id==actor.pk and
                    previo.estado=='REGISTRADO' and previo.numero_recibo==numero and previo.metodo_pago==metodo and
                    (previo.referencia or '')==referencia and previo.monto_total==total and
                    dict(previo.detalles.values_list('obligacion_id','monto_aplicado'))==por_obligacion and
                    dict(previo.aplicaciones_cuotas.values_list('cuota_id','monto_aplicado'))==por_cuota):
                return previo,False
            raise ValidationError('La reserva ya se utilizó con otros datos. No se modificó el pago.')
        if caja is None:raise ValidationError('Abra su caja en Finanzas → Caja antes de registrar un cobro nuevo.')
        if convenio.estado not in ('ACTIVO','INCUMPLIDO'):raise ValidationError('El convenio no está habilitado para cobros nuevos.')
        enlaces={e.obligacion_id:e for e in convenio.obligaciones_incluidas.all()}
        originales={o.pk:o for o in filas if o.pk in enlaces}
        if len(originales)!=len(enlaces):raise ValidationError('Las obligaciones del convenio ya no corresponden al estudiante.')
        resumen_actual=resumen(convenio)
        saldos_cuotas={f['cuota'].pk:f for f in resumen_actual['filas']}
        saldos_originales={pk:importes(o)[2] for pk,o in originales.items()}
        if any(o.estado=='ANULADA' for o in originales.values()) or resumen_actual['saldo']!=sum(saldos_originales.values(),Decimal('0')):
            raise ValidationError('Los saldos de cuotas y obligaciones no coinciden. Se requiere revisión de Dirección; no se redistribuyen pagos ni donaciones automáticamente.')
        for pk,monto in por_cuota.items():
            if pk not in saldos_cuotas or saldos_cuotas[pk]['cuota'].estado=='ANULADA' or monto>saldos_cuotas[pk]['saldo']:
                raise ValidationError('Una cuota es ajena, está anulada o el abono supera su saldo.')
        for pk,monto in por_obligacion.items():
            if pk not in originales or monto>saldos_originales[pk]:raise ValidationError('Obligación ajena o importe superior al saldo original.')
        snapshot={'convenio':convenio.pk,'estudiante':f'{estudiante.codigo_estudiante} · {estudiante.nombres} {estudiante.apellidos}',
            'registrado_por':actor.numero_usuario,
            'detalles':[{'descripcion':originales[pk].descripcion,'matricula':originales[pk].matricula.numero_matricula,
                         'vencimiento':str(originales[pk].fecha_vencimiento),'importe':str(monto)} for pk,monto in sorted(por_obligacion.items())],
            'cuotas':[{'cuota':pk,'numero':saldos_cuotas[pk]['cuota'].numero_cuota,'importe':str(monto)} for pk,monto in sorted(por_cuota.items())]}
        pago=Pago(id_pago=reserva['id'],numero_recibo=numero,estudiante=estudiante,usuario=actor,fecha_pago=timezone.now(),
            monto_total=total,metodo_pago=metodo,referencia=referencia,estado='REGISTRADO',
            observaciones='VIDASYS_RECIBO_V1\n'+json.dumps(snapshot,ensure_ascii=False))
        pago.full_clean();pago.save(force_insert=True)
        for pk,monto in sorted(por_obligacion.items()):
            detalle=DetallePago(pago=pago,obligacion=originales[pk],monto_aplicado=monto)
            detalle.full_clean();detalle.save()
        for pk,monto in sorted(por_cuota.items()):
            aplicacion=AplicacionPagoCuota(pago=pago,cuota=saldos_cuotas[pk]['cuota'],monto_aplicado=monto)
            aplicacion.full_clean();aplicacion.save()
        for cuota in registros:
            if cuota.estado=='ANULADA':continue
            pagado=cuota.aplicaciones_pago.filter(pago__estado='REGISTRADO').aggregate(total=Sum('monto_aplicado'))['total'] or Decimal('0')
            cuota.estado='PAGADA' if pagado==cuota.monto_cuota else 'PENDIENTE'
            cuota.save(update_fields=['estado'])
        if resumen(convenio)['saldo']==0:
            convenio.estado='CUMPLIDO'
        convenio.fecha_actualizacion=timezone.now()
        convenio.save(update_fields=['estado','fecha_actualizacion'])
        MovimientoCaja.objects.create(caja=caja,pago=pago,operador=actor,metodo=metodo,importe=total,referencia=referencia)
        return pago,True
