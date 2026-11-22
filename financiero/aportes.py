"""F6: una recepción = un Ingreso = un movimiento de caja. Compromisos sin dinero.
Orden: usuario -> caja (si hay dinero) -> estudiante -> matrícula -> obligaciones
-> donantes por PK -> padrinazgo -> solicitud/coberturas -> ingreso/anulación.
"""
import json
import uuid
from datetime import date
from decimal import Decimal
from django.core import signing
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from academico.models import Estudiante,Matricula
from . import caja,comprobantes
from .operaciones import texto,importe,_pago
from .consultas import importes
from .models import (Donante,Donacion,Padrinazgo,Ingreso,CategoriaIngreso,Obligacion,ConvenioObligacion,
 MovimientoCaja,SolicitudBeca,HistorialDonante,SolicitudPadrinazgo,CoberturaPadrinazgo,
 RecepcionDonacion,LineaDonacion,RevisionPadrinazgo,AnulacionDonacion)


def fecha_dia(valor):
    try:return date.fromisoformat(str(valor))
    except (ValueError,TypeError):raise ValidationError('Indique una fecha válida antes de continuar.')


def pendiente(c):
    recibido=c.aportes.filter(donacion__estado='RECIBIDA').aggregate(n=Sum('donacion__monto'))['n'] or Decimal('0')
    return max(c.monto-recibido,Decimal('0'))


def cubierta(o,excluir=None):
    qs=o.coberturas_padrinazgo.filter(activa=True,solicitud__estado='APROBADA',solicitud__padrinazgo__fecha_inicio__lte=timezone.localdate())
    if excluir:qs=qs.exclude(solicitud_id=excluir)
    return min(importes(o)[2],sum((pendiente(c) for c in qs),Decimal('0')))


def reservada(o,excluir=None):
    qs=o.coberturas_padrinazgo.filter(activa=True,solicitud__estado='APROBADA')
    if excluir:qs=qs.exclude(solicitud_id=excluir)
    return sum((pendiente(c) for c in qs),Decimal('0'))


def detalle_solvencia(estudiante):
    # La función SQL original sigue siendo la primera autoridad. Se agrega solo la excepción F6.
    from .consultas import solvente_sql
    base=solvente_sql(estudiante)
    from .models import ConvenioPago
    from .convenios import resumen
    obs=list(Obligacion.objects.filter(matricula__estudiante=estudiante).select_related('matricula'))
    financiero=cobertura=exigible=Decimal('0');filas=[]
    for o in obs:
        if o.estado=='ANULADA':continue
        saldo=importes(o)[2];protegido=cubierta(o);cargo=max(saldo-protegido,Decimal('0'))
        financiero+=saldo;cobertura+=protegido
        if o.fecha_vencimiento<timezone.localdate() and cargo>0 and not ConvenioObligacion.objects.filter(obligacion=o,convenio__estado__in=('ACTIVO','CUMPLIDO')).exists():exigible+=cargo
        filas.append({'obligacion':o.pk,'saldo':str(saldo),'cobertura':str(protegido),'cargo':str(cargo)})
    convenios=ConvenioPago.objects.filter(estudiante=estudiante)
    conflicto=convenios.filter(estado='INCUMPLIDO').exists() or any(resumen(c)['vencidas'] for c in convenios.filter(estado='ACTIVO'))
    solvente=base or (cobertura>0 and exigible==0 and not conflicto)
    return {'solvente':solvente,'por_padrinazgo':bool(solvente and cobertura>0),
        'saldo_financiero':financiero,'cobertura_autorizada':cobertura,'saldo_estudiante':financiero-cobertura,'filas':filas}


def guardar_donante(*,usuario,clave,donante_id=None,**datos):
    permitidos={'tipo','nombre_completo','documento_identidad','correo','telefono','pais','direccion','es_anonimo','notas','estado'}
    if set(datos)!=permitidos:raise ValidationError('Complete el formulario de donante.')
    datos={k:(v if k=='es_anonimo' else texto(v,4000 if k in ('direccion','notas') else 150)) for k,v in datos.items()}
    if datos['tipo'] not in ('PERSONA','INSTITUCION') or datos['estado'] not in ('ACTIVO','INACTIVO') or not datos['nombre_completo']:raise ValidationError('Tipo, nombre o estado inválido.')
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,caja.OPERADORES)
        previo=HistorialDonante.objects.filter(clave=clave).first()
        if previo:
            if previo.operador_id!=actor.pk or previo.datos!=datos or (donante_id and previo.donante_id!=donante_id):raise ValidationError('La clave ya se utilizó con otros datos.')
            return previo.donante
        d=Donante.objects.select_for_update().get(pk=donante_id) if donante_id else Donante(fecha_registro=timezone.now())
        anterior={f.attname:str(getattr(d,f.attname)) for f in d._meta.local_fields} if d.pk else {}
        if datos['documento_identidad'] and Donante.objects.filter(documento_identidad=datos['documento_identidad']).exclude(pk=d.pk).exists():raise ValidationError('Ya existe un donante con ese documento. Búsquelo antes de crear otro.')
        for k,v in datos.items():setattr(d,k,v)
        d.fecha_actualizacion=timezone.now();d.full_clean();d.save()
        HistorialDonante.objects.create(clave=clave,donante=d,operador=actor,datos=datos,anteriores=anterior)
        return d


def bloquear(matricula_id,donantes):
    m=Matricula.objects.get(pk=matricula_id)
    Estudiante.objects.select_for_update().get(pk=m.estudiante_id)
    m=Matricula.objects.select_for_update().get(pk=m.pk)
    obs=list(Obligacion.objects.select_for_update().filter(matricula=m).order_by('pk'))
    ds={d.pk:d for d in Donante.objects.select_for_update().filter(pk__in=sorted(set(donantes))).order_by('pk')}
    if len(ds)!=len(set(donantes)):raise ValidationError('El donante ya no está disponible.')
    return m,obs,ds


def elegible(o):
    if o.estado=='ANULADA' or o.concepto.nombre.upper().replace('Í','I') not in ('MATRICULA','MENSUALIDAD'):raise ValidationError('Seleccione cargos vigentes de matrícula o mensualidades.')
    if ConvenioObligacion.objects.filter(obligacion=o,convenio__estado__in=('ACTIVO','INCUMPLIDO','CUMPLIDO')).exists():raise ValidationError('La obligación tiene convenio. Su cruce con aportes requiere una política adicional.')


def foto(m,obs,donante):
    return {'matricula':m.pk,'estudiante':m.estudiante_id,'ciclo':m.ciclo_id,'estado':m.estado,'fecha_matricula':str(m.fecha_matricula),'ciclo_fechas':[str(m.ciclo.fecha_inicio),str(m.ciclo.fecha_fin)],
        'donante':donante.pk,'donante_version':str(donante.fecha_actualizacion),
        'obligaciones':[{'id':o.pk,'original':str(o.monto_original),'descuento':str(o.monto_descuento),
         'saldo':str(importes(o)[2]),'estado':o.estado,'emision':str(o.fecha_emision),'vencimiento':str(o.fecha_vencimiento),'concepto':o.concepto_id,'reserva':str(reservada(o))} for o in obs]}


def solicitar(*,usuario,clave,donante_id,matricula_id,inicio,limite,modalidad,porcentaje=None,asignaciones=None,observaciones=''):
    inicio=fecha_dia(inicio);limite=fecha_dia(limite);observaciones=texto(observaciones,4000,True)
    if limite<inicio or modalidad not in ('FIJO','PORCENTAJE'):raise ValidationError('Revise fechas y modalidad del compromiso.')
    if not asignaciones or len({pk for pk,_ in asignaciones})!=len(asignaciones):raise ValidationError('Seleccione obligaciones distintas e importes explícitos.')
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,caja.OPERADORES);m,obs,ds=bloquear(matricula_id,[donante_id]);d=ds[donante_id]
        previa=SolicitudPadrinazgo.objects.filter(clave=clave).first()
        if previa:
            prop=previa.propuesta
            pct_entrada=str(importe(porcentaje)) if modalidad=='PORCENTAJE' else None
            mismos_ids=sorted(pk for pk,_ in asignaciones)==[f['id'] for f in prop['lineas']]
            mismos_montos=modalidad=='PORCENTAJE' or sorted((pk,str(importe(v))) for pk,v in asignaciones)==[(f['id'],f['monto']) for f in prop['lineas']]
            if (previa.solicitante_id!=actor.pk or previa.donante_id!=d.pk or previa.matricula_id!=m.pk or
                prop['inicio']!=str(inicio) or prop['limite']!=str(limite) or prop['modalidad']!=modalidad or
                prop['porcentaje']!=pct_entrada or prop['observaciones']!=observaciones or not mismos_ids or not mismos_montos):
                raise ValidationError('La clave ya se utilizó con otros datos.')
            return previa
        if m.estado!='ACTIVA' or d.estado!='ACTIVO':raise ValidationError('La matrícula y el donante deben estar activos.')
        por_id={o.pk:o for o in obs};lineas=[]
        pct=importe(porcentaje) if modalidad=='PORCENTAJE' else None
        if pct and pct>100:raise ValidationError('El porcentaje no puede superar 100 %.')
        for pk,valor in asignaciones:
            o=por_id.get(pk)
            if o is None:raise ValidationError('La obligación pertenece a otra matrícula.')
            elegible(o);libre=importes(o)[2]-reservada(o)
            monto=libre*pct/100 if pct else importe(valor)
            if monto<=0 or monto!=monto.quantize(Decimal('.01')) or monto>libre:raise ValidationError('La cobertura supera el saldo libre o requiere fracciones de centavo. Revise los importes.')
            lineas.append({'id':pk,'monto':str(monto.quantize(Decimal('.01')))})
        propuesta={'inicio':str(inicio),'limite':str(limite),'modalidad':modalidad,'porcentaje':str(pct) if pct else None,
                   'lineas':sorted(lineas,key=lambda f:f['id']),'observaciones':observaciones}
        anterior=SolicitudPadrinazgo.objects.filter(clave=clave).first()
        if anterior:
            if anterior.solicitante_id!=actor.pk or anterior.donante_id!=d.pk or anterior.matricula_id!=m.pk or anterior.propuesta!=propuesta:raise ValidationError('La clave ya se utilizó con otros datos.')
            return anterior
        return SolicitudPadrinazgo.objects.create(clave=clave,donante=d,matricula=m,solicitante=actor,propuesta=propuesta,anteriores=foto(m,obs,d))


def resolver(*,usuario,solicitud_id,decision,motivo='',revision='',confirmar=False):
    motivo=texto(motivo)
    if decision not in ('APROBADA','RECHAZADA') or (decision=='RECHAZADA' and not motivo):raise ValidationError('Explique el rechazo.')
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,('DIRECTORA',));ref=SolicitudPadrinazgo.objects.get(pk=solicitud_id)
        m,obs,ds=bloquear(ref.matricula_id,[ref.donante_id]);s=SolicitudPadrinazgo.objects.select_for_update().get(pk=ref.pk)
        if s.estado!='PENDIENTE':
            if s.estado==decision and s.motivo==motivo:return s
            raise ValidationError('La solicitud ya tiene otra resolución.')
        if decision=='APROBADA':
            d=ds[s.donante_id]
            if d.estado!='ACTIVO' or m.estado!='ACTIVA' or foto(m,obs,d)!=s.anteriores:raise ValidationError('Los datos cambiaron. Rechace esta solicitud y prepare una nueva.')
            if not s.solicitante.is_active or s.solicitante.rol not in caja.OPERADORES:raise ValidationError('El solicitante perdió sus permisos.')
            por_id={o.pk:o for o in obs}
            for f in s.propuesta['lineas']:
                elegible(por_id[f['id']])
                if Decimal(f['monto'])>importes(por_id[f['id']])[2]-reservada(por_id[f['id']]):raise ValidationError('Hay otra cobertura sobre el saldo solicitado.')
            contenido={'solicitud':s.pk,'directora':actor.pk,'datos':s.anteriores,'propuesta':s.propuesta,'motivo':motivo}
            if not confirmar:return signing.dumps(contenido,salt='padrinazgo')
            try:firmado=signing.loads(revision,salt='padrinazgo',max_age=7200)
            except signing.BadSignature:raise ValidationError('Compare nuevamente antes de aprobar.')
            if firmado!=contenido:raise ValidationError('La comparación cambió. Revise la solicitud.')
            total=sum(Decimal(f['monto']) for f in s.propuesta['lineas']);base=sum(importes(por_id[f['id']])[2] for f in s.propuesta['lineas'])
            p=Padrinazgo(donante=d,matricula=m,fecha_inicio=s.propuesta['inicio'],fecha_fin=s.propuesta['limite'],
                porcentaje_cobertura=(total/base*100).quantize(Decimal('.01')),estado='ACTIVO',observaciones=s.propuesta['observaciones'],fecha_registro=timezone.now(),fecha_actualizacion=timezone.now())
            p.full_clean();p.save();s.padrinazgo=p
        s.estado=decision;s.directora=actor;s.fecha_resolucion=timezone.now();s.motivo=motivo
        s.save(update_fields=['estado','directora','fecha_resolucion','motivo','padrinazgo'])
        if decision=='APROBADA':
            for f in s.propuesta['lineas']:CoberturaPadrinazgo.objects.create(solicitud=s,obligacion_id=f['id'],monto=f['monto'])
        return s


def recibir(*,usuario,clave,donante_id,modalidad,monto,fecha,metodo,referencia='',matricula_id=None,solicitud_id=None,asignaciones=None,observaciones='',archivo=None):
    monto=importe(monto);referencia=_pago(metodo,referencia,fecha);observaciones=texto(observaciones)
    if modalidad not in ('GENERAL','DIRIGIDA','PADRINAZGO'):raise ValidationError('Seleccione el destino del aporte.')
    if modalidad=='GENERAL' and (matricula_id or solicitud_id or asignaciones):raise ValidationError('Una donación general no se aplica a deudas de estudiantes.')
    if modalidad!='GENERAL' and not matricula_id:raise ValidationError('Seleccione estudiante y matrícula.')
    if (modalidad=='PADRINAZGO')!=bool(solicitud_id):raise ValidationError('Seleccione el padrinazgo autorizado correspondiente.')
    asignaciones=asignaciones or []
    if len({pk for pk,_ in asignaciones})!=len(asignaciones):raise ValidationError('No repita obligaciones.')
    lineas=[{'id':pk,'monto':str(importe(v))} for pk,v in asignaciones]
    if modalidad!='GENERAL' and (not lineas or sum(Decimal(f['monto']) for f in lineas)!=monto):raise ValidationError('El desglose debe sumar exactamente el aporte recibido. No se redistribuyen excedentes.')
    doc=comprobantes.validar_archivo(archivo)
    datos={'donante':donante_id,'modalidad':modalidad,'monto':str(monto),'fecha':fecha.isoformat(),'metodo':metodo,'referencia':referencia,
        'matricula':matricula_id,'solicitud':solicitud_id,'lineas':sorted(lineas,key=lambda f:f['id']),'observaciones':observaciones,'documento':comprobantes.huella(doc)}
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,caja.OPERADORES);c=caja.abierta_bloqueada(actor,exigir=False)
        previa=RecepcionDonacion.objects.filter(clave=clave).select_related('ingreso').first()
        if previa:
            if previa.ingreso.usuario_registra_id!=actor.pk or previa.datos!=datos:raise ValidationError('La clave ya se utilizó con otros datos.')
            return previa
        if c is None:raise ValidationError('Abra su propia caja antes de recibir dinero.')
        if RecepcionDonacion.objects.filter(ingreso__usuario_registra=actor,datos=datos).exists():raise ValidationError('Ya existe un aporte con los mismos datos. Revise el historial.')
        m=None;obs=[]
        if matricula_id:m,obs,ds=bloquear(matricula_id,[donante_id]);d=ds[donante_id]
        else:d=Donante.objects.select_for_update().get(pk=donante_id)
        if d.estado!='ACTIVO':raise ValidationError('El donante está inactivo.')
        s=None;cs={}
        if solicitud_id:
            ref=SolicitudPadrinazgo.objects.get(pk=solicitud_id)
            if not ref.padrinazgo_id:raise ValidationError('El padrinazgo no está autorizado.')
            p=Padrinazgo.objects.select_for_update().get(pk=ref.padrinazgo_id)
            s=SolicitudPadrinazgo.objects.select_for_update().get(pk=solicitud_id)
            if s.estado!='APROBADA' or s.matricula_id!=m.pk or p.donante_id!=d.pk or p.estado!='ACTIVO':raise ValidationError('El padrinazgo, estudiante o padrino no corresponden o su cobertura fue cancelada.')
            cs={x.obligacion_id:x for x in s.coberturas.select_for_update().filter(activa=True).order_by('pk')}
        por_id={o.pk:o for o in obs}
        for f in lineas:
            o=por_id.get(f['id'])
            if o is None:raise ValidationError('La obligación pertenece a otra matrícula.')
            elegible(o);valor=Decimal(f['monto'])
            if valor>importes(o)[2]:raise ValidationError('El aporte supera el saldo real. No se generan créditos ni devoluciones.')
            if s:
                if o.pk not in cs or valor>pendiente(cs[o.pk]):raise ValidationError('El aporte supera o no corresponde al compromiso pendiente.')
            elif valor>importes(o)[2]-reservada(o):raise ValidationError('Ese saldo está reservado por otro padrinazgo. Dirección debe resolver primero la cobertura.')
        categoria,_=CategoriaIngreso.objects.get_or_create(nombre='DONACIONES',defaults={'estado':'ACTIVO','descripcion':'Aportes institucionales recibidos; compromisos excluidos.'})
        if categoria.estado!='ACTIVO':raise ValidationError('La categoría de donaciones está inactiva. Administración debe activarla antes de recibir aportes.')
        ingreso=Ingreso(categoria_ingreso=categoria,usuario_registra=actor,fecha_ingreso=fecha,monto=monto,metodo_pago=metodo,
            referencia=referencia,estado='REGISTRADO',observaciones=observaciones,fecha_creacion=timezone.now())
        ingreso.full_clean();ingreso.save()
        r=RecepcionDonacion.objects.create(clave=clave,ingreso=ingreso,donante=d,matricula=m,solicitud=s,datos=datos,comprobante=comprobantes.guardar(doc,actor),
            instantanea={'donante':'Donante anónimo' if d.es_anonimo else d.nombre_completo,'destino':f'{m.estudiante.codigo_estudiante} · {m.estudiante.nombres} {m.estudiante.apellidos} · {m.ciclo}' if m else 'Funcionamiento institucional',
                'operador':actor.numero_usuario,'lineas':[{'descripcion':por_id[f['id']].descripcion,'monto':f['monto']} for f in lineas] or [{'descripcion':'Aporte general','monto':str(monto)}]})
        for f in lineas or [{'id':None,'monto':str(monto)}]:
            donacion=Donacion(donante=d,padrinazgo=s.padrinazgo if s else None,obligacion=por_id.get(f['id']),
                ingreso=ingreso if len(lineas)<=1 else None,usuario_registra=actor,usuario_confirma=actor,monto=f['monto'],
                fecha_compromiso=s.fecha.date() if s else timezone.localdate(fecha),fecha_ingreso=timezone.localdate(fecha),
                estado='RECIBIDA',metodo_pago=metodo,referencia=referencia,observaciones=observaciones,fecha_registro=timezone.now(),fecha_actualizacion=timezone.now())
            donacion.full_clean();donacion.save()
            LineaDonacion.objects.create(recepcion=r,donacion=donacion,cobertura=cs.get(f['id']))
            if f['id']:por_id[f['id']].actualizar_estado()
        MovimientoCaja.objects.create(caja=c,ingreso=ingreso,operador=actor,metodo=metodo,importe=monto,referencia=referencia)
        return r


def revisar(*,usuario,solicitud_id,clave,accion,motivo,limite=None,donante_id=None,porcentaje=None,notificacion='',revision='',confirmar=False):
    motivo=texto(motivo,4000,True);notificacion=texto(notificacion,1000)
    if accion not in ('PRORROGA','SUSTITUCION','CANCELACION','BECA'):raise ValidationError('Seleccione una resolución válida.')
    with transaction.atomic():
        actor=caja.actor_bloqueado(usuario,('DIRECTORA',));ref=SolicitudPadrinazgo.objects.select_related('padrinazgo').get(pk=solicitud_id)
        if not ref.padrinazgo_id:raise ValidationError('El padrinazgo no está autorizado.')
        ids=[ref.padrinazgo.donante_id]+([donante_id] if donante_id else [])
        m,obs,ds=bloquear(ref.matricula_id,ids)
        p=Padrinazgo.objects.select_for_update().get(pk=ref.padrinazgo_id)
        s=SolicitudPadrinazgo.objects.select_for_update().get(pk=solicitud_id)
        cs=list(s.coberturas.select_for_update().order_by('pk'))
        datos={'accion':accion,'motivo':motivo,'limite':str(limite) if limite else None,'donante':donante_id,'porcentaje':str(porcentaje) if porcentaje else None,'notificacion':notificacion}
        previa=RevisionPadrinazgo.objects.filter(clave=clave).first()
        if previa:
            if previa.directora_id!=actor.pk or previa.solicitud_id!=s.pk or previa.aplicados['datos']!=datos:raise ValidationError('La clave ya se utilizó con otros datos.')
            return previa
        if p.estado!='ACTIVO' or s.estado!='APROBADA':raise ValidationError('La cobertura ya fue cancelada o convertida.')
        version={'padrinazgo':{f.attname:str(getattr(p,f.attname)) for f in p._meta.local_fields},
            'coberturas':[{'id':c.pk,'monto':str(c.monto),'pendiente':str(pendiente(c)),'activa':c.activa} for c in cs]}
        if accion=='PRORROGA':
            limite=fecha_dia(limite)
            if limite<=p.fecha_fin or limite<timezone.localdate():raise ValidationError('La nueva fecha debe ampliar el compromiso y no estar vencida.')
        if accion=='SUSTITUCION' and (donante_id not in ds or ds[donante_id].estado!='ACTIVO' or donante_id==p.donante_id):raise ValidationError('Seleccione otro donante activo.')
        if accion in ('CANCELACION','BECA') and not notificacion:raise ValidationError('Escriba el mensaje que verá el estudiante, sin datos privados del padrino.')
        contenido={'solicitud':s.pk,'directora':actor.pk,'version':version,'datos':datos}
        if not confirmar:return signing.dumps(contenido,salt='revision-padrinazgo')
        try:firmado=signing.loads(revision,salt='revision-padrinazgo',max_age=7200)
        except signing.BadSignature:raise ValidationError('Compare nuevamente antes de confirmar.')
        if firmado!=contenido:raise ValidationError('El padrinazgo cambió. Compare nuevamente.')
        beca_id=None
        if accion=='PRORROGA':p.fecha_fin=limite
        elif accion=='SUSTITUCION':p.donante=ds[donante_id]
        else:
            for c in cs:c.activa=False;c.save(update_fields=['activa'])
            if accion=='BECA':
                from . import becas
                por_id={o.pk:o for o in obs};seleccion=[c for c in cs if pendiente(c)>0]
                pct,conceptos,alcance=becas.condiciones(porcentaje,list(sorted({por_id[c.obligacion_id].concepto.nombre.upper().replace('Í','I') for c in seleccion})),'AMBAS')
                if not seleccion:raise ValidationError('No hay cobertura pendiente que convertir.')
                for c in seleccion:
                    if por_id[c.obligacion_id].monto_original*Decimal(pct)/100!=pendiente(c):raise ValidationError('La beca F2 no coincide exactamente con la cobertura pendiente. No se retiró la protección.')
                if SolicitudBeca.objects.filter(matricula=m,estado='PENDIENTE').exists():raise ValidationError('Resuelva primero la solicitud de beca pendiente.')
                # Conversión iniciada por Dirección, sin atribuir falsamente una solicitud a Secretaría.
                sb=SolicitudBeca.objects.create(clave=uuid.uuid4(),matricula=m,solicitante=actor,porcentaje_solicitado=pct,
                    conceptos_solicitados=conceptos,alcance_solicitado=alcance,justificacion=motivo,contexto=becas.contexto_matricula(m))
                args={'porcentaje':pct,'conceptos':conceptos,'alcance':alcance,'obligaciones':[c.obligacion_id for c in seleccion],'observaciones':motivo}
                _,token=becas.previsualizar(usuario=actor,solicitud_id=sb.pk,**args)
                beca_id=becas.resolver(usuario=actor,solicitud_id=sb.pk,decision='APROBADA',revision=token,**args).beca_id
            p.estado='CANCELADO'
        p.fecha_actualizacion=timezone.now();p.full_clean();p.save()
        return RevisionPadrinazgo.objects.create(clave=clave,solicitud=s,directora=actor,accion=accion,motivo=motivo,
            notificacion=notificacion,anteriores=version,aplicados={'datos':datos,'beca':beca_id,'estado':p.estado})


def _bloquear_recepcion(usuario,roles,recepcion_id):
    actor=caja.actor_bloqueado(usuario,roles);ref=RecepcionDonacion.objects.select_related('ingreso').get(pk=recepcion_id)
    mov=MovimientoCaja.objects.get(ingreso_id=ref.ingreso_id);c=caja.Caja.objects.select_for_update().get(pk=mov.caja_id)
    if ref.matricula_id:m,obs,ds=bloquear(ref.matricula_id,[ref.donante_id])
    else:
        m=None;obs=[];Donante.objects.select_for_update().get(pk=ref.donante_id)
    if ref.solicitud_id:
        sr=SolicitudPadrinazgo.objects.get(pk=ref.solicitud_id)
        Padrinazgo.objects.select_for_update().get(pk=sr.padrinazgo_id)
        SolicitudPadrinazgo.objects.select_for_update().get(pk=sr.pk)
        list(sr.coberturas.select_for_update().order_by('pk'))
    i=Ingreso.objects.select_for_update().get(pk=ref.ingreso_id)
    return actor,ref,c,i,obs


def _foto_recepcion(r,i):
    return json.loads(json.dumps({'ingreso':{f.attname:getattr(i,f.attname) for f in i._meta.local_fields},
        'lineas':list(r.lineas.order_by('pk').values('donacion_id','cobertura_id','donacion__estado','donacion__monto','donacion__obligacion_id'))},default=str,sort_keys=True))


def _validar_anulacion(r,c,i):
    mov=MovimientoCaja.objects.get(ingreso=i)
    if (mov.importe!=i.monto or mov.metodo!=i.metodo_pago or mov.operador_id!=i.usuario_registra_id or mov.referencia!=(i.referencia or '') or
        Decimal(r.datos['monto'])!=i.monto or r.datos['metodo']!=i.metodo_pago or r.datos['referencia']!=(i.referencia or '')):
        raise ValidationError('El ingreso, la recepción y la caja no coinciden; se requiere revisión.')
    if r.solicitud_id and r.solicitud.padrinazgo.donante_id!=r.donante_id:
        raise ValidationError('El padrino fue sustituido después del aporte. La anulación requiere revisar su tratamiento.')
    if c.estado!='ABIERTA' or i.estado!='REGISTRADO':raise ValidationError('La caja está cerrada o el aporte ya fue anulado. No se habilitan ajustes posteriores al cierre.')
    if i.metodo_pago=='EFECTIVO' and Decimal(caja.totales(c)['disponible'])<i.monto:raise ValidationError('El aporte respalda desembolsos. No hay disponible para reservar su anulación.')
    if r.lineas.filter(cobertura__activa=False).exists():raise ValidationError('La cobertura fue cancelada o convertida después del aporte. Dirección debe revisar su tratamiento.')
    if sum((l.donacion.monto for l in r.lineas.select_related('donacion')),Decimal('0'))!=i.monto:raise ValidationError('El desglose no coincide con el ingreso original.')


def pedir_anulacion(*,usuario,recepcion_id,clave,motivo):
    motivo=texto(motivo,4000,True)
    with transaction.atomic():
        actor,r,c,i,obs=_bloquear_recepcion(usuario,caja.OPERADORES,recepcion_id)
        if i.usuario_registra_id!=actor.pk:raise PermissionDenied('Solo puede solicitar anulaciones de sus propios aportes.')
        anterior=AnulacionDonacion.objects.filter(clave=clave).first()
        if anterior:
            if anterior.recepcion_id!=r.pk or anterior.solicitante_id!=actor.pk or anterior.motivo!=motivo:raise ValidationError('La clave ya se utilizó con otros datos.')
            return anterior
        if r.anulaciones.filter(estado='PENDIENTE').exists():raise ValidationError('Ya existe una solicitud pendiente.')
        _validar_anulacion(r,c,i)
        return AnulacionDonacion.objects.create(clave=clave,recepcion=r,solicitante=actor,motivo=motivo,anteriores=_foto_recepcion(r,i))


def anular(*,usuario,anulacion_id,decision,resolucion='',revision='',confirmar=False):
    resolucion=texto(resolucion)
    if decision not in ('APROBADA','RECHAZADA') or (decision=='RECHAZADA' and not resolucion):raise ValidationError('Explique el rechazo.')
    with transaction.atomic():
        ref=AnulacionDonacion.objects.get(pk=anulacion_id)
        actor,r,c,i,obs=_bloquear_recepcion(usuario,('DIRECTORA',),ref.recepcion_id)
        s=AnulacionDonacion.objects.select_for_update().get(pk=ref.pk)
        if s.estado!='PENDIENTE':
            if s.estado==decision and s.resolucion==resolucion:return s
            raise ValidationError('La solicitud ya tiene otra resolución.')
        if decision=='APROBADA':
            if not s.solicitante.is_active or s.solicitante.rol not in caja.OPERADORES:raise ValidationError('El solicitante perdió sus permisos.')
            _validar_anulacion(r,c,i)
            actual=_foto_recepcion(r,i)
            if actual!=s.anteriores:raise ValidationError('Los datos cambiaron; rechace la solicitud y prepare otra.')
            contenido={'solicitud':s.pk,'directora':actor.pk,'foto':actual,'disponible':caja.totales(c)['disponible'],'resolucion':resolucion}
            if not confirmar:return signing.dumps(contenido,salt='anular-aporte')
            try:firmado=signing.loads(revision,salt='anular-aporte',max_age=7200)
            except signing.BadSignature:raise ValidationError('Compare nuevamente antes de confirmar.')
            if firmado!=contenido:raise ValidationError('Cambió el aporte o el disponible; compare nuevamente.')
            i.estado='ANULADO';i.usuario_anula=actor;i.fecha_anulacion=timezone.now();i.motivo_anulacion=s.motivo;i.save(update_fields=['estado','usuario_anula','fecha_anulacion','motivo_anulacion'])
            for l in r.lineas.select_related('donacion'):
                d=l.donacion;d.estado='ANULADA';d.fecha_actualizacion=timezone.now();d.save(update_fields=['estado','fecha_actualizacion'])
            afectados=set(r.lineas.values_list('donacion__obligacion_id',flat=True))
            for o in obs:
                if o.pk in afectados:o.actualizar_estado()
            s.aplicados={'ingreso':i.pk,'devolucion':False,'cobertura_restablecida':bool(r.solicitud_id)}
        s.estado=decision;s.directora=actor;s.fecha_resolucion=timezone.now();s.resolucion=resolucion
        s.save(update_fields=['estado','directora','fecha_resolucion','resolucion','aplicados'])
        return s
