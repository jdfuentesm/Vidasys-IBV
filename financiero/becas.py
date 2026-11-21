"""Único servicio institucional de becas; nunca modifica pagos, donaciones o recibos."""
from decimal import Decimal, InvalidOperation

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from academico.models import Estudiante, Matricula
from core.models import Usuario
from .consultas import importes, solvente
from .models import (SolicitudBeca, Beca, AplicacionBeca, Obligacion,
                     ConvenioObligacion, DetallePago, Donacion)

CONCEPTOS = ('MATRICULA','MENSUALIDAD')
ALCANCES = ('VENCIDAS','NO_VENCIDAS','AMBAS')


def normalizar_concepto(nombre):
    return nombre.strip().upper().replace('Í','I')


def condiciones(porcentaje, conceptos, alcance):
    try:
        porcentaje = Decimal(str(porcentaje))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Porcentaje inválido.')
    if not porcentaje.is_finite() or porcentaje not in (Decimal('50'),Decimal('100')):
        raise ValidationError('La beca solo puede ser del 50 % o del 100 %.')
    if not isinstance(conceptos, (list,tuple)) or not conceptos or any(type(c) is not str for c in conceptos) or len(set(conceptos)) != len(conceptos) or any(c not in CONCEPTOS for c in conceptos):
        raise ValidationError('Seleccione matrícula, mensualidades o ambos.')
    if alcance not in ALCANCES:
        raise ValidationError('Seleccione obligaciones vencidas, no vencidas o ambas.')
    return str(int(porcentaje)), sorted(conceptos), alcance


def contexto_matricula(matricula):
    return {'estudiante':matricula.estudiante_id,'ciclo':matricula.ciclo_id,
            'numero':matricula.numero_matricula,'fecha':str(matricula.fecha_matricula)}


def solicitar(*, usuario, matricula_id, porcentaje, conceptos, alcance, justificacion, clave):
    porcentaje, conceptos, alcance = condiciones(porcentaje,conceptos,alcance)
    justificacion = justificacion.strip()
    if not justificacion or len(justificacion) > 4000:
        raise ValidationError('Indique una justificación de hasta 4000 caracteres.')
    with transaction.atomic():
        actor = Usuario.objects.select_for_update().get(pk=usuario.pk)
        if not actor.is_active or actor.rol != 'SECRETARIA':
            raise PermissionDenied('Solo Secretaría activa puede solicitar becas.')
        referencia = Matricula.objects.get(pk=matricula_id)
        Estudiante.objects.select_for_update().get(pk=referencia.estudiante_id)
        matricula = Matricula.objects.select_for_update().get(pk=matricula_id)
        if matricula.estudiante_id != referencia.estudiante_id:
            raise ValidationError('La matrícula cambió. Recargue la pantalla.')
        previa = SolicitudBeca.objects.filter(clave=clave).first()
        if previa:
            if (previa.solicitante_id != actor.pk or previa.matricula_id != matricula.pk or
                    previa.porcentaje_solicitado != Decimal(porcentaje) or previa.conceptos_solicitados != conceptos or
                    previa.alcance_solicitado != alcance or previa.justificacion != justificacion):
                raise ValidationError('La clave ya se utilizó con otros datos.')
            return previa
        if matricula.estado != 'ACTIVA':
            raise ValidationError('La matrícula debe estar activa.')
        if SolicitudBeca.objects.filter(matricula=matricula,estado='PENDIENTE').exists():
            raise ValidationError('La matrícula ya tiene una solicitud pendiente.')
        return SolicitudBeca.objects.create(clave=clave,matricula=matricula,solicitante=actor,
            porcentaje_solicitado=porcentaje,conceptos_solicitados=conceptos,
            alcance_solicitado=alcance,justificacion=justificacion,contexto=contexto_matricula(matricula))


def datos_resolucion(decision, porcentaje=None, conceptos=None, alcance=None, obligaciones=None, observaciones=''):
    observaciones = observaciones.strip()
    if len(observaciones)>4000 or decision not in ('APROBADA','RECHAZADA'):
        raise ValidationError('Resolución inválida.')
    if decision=='RECHAZADA':
        if not observaciones:
            raise ValidationError('Indique la justificación del rechazo.')
        return {'decision':decision,'observaciones':observaciones}
    porcentaje,conceptos,alcance=condiciones(porcentaje,conceptos,alcance)
    if not isinstance(obligaciones,(list,tuple)) or not obligaciones:
        raise ValidationError('Seleccione expresamente las obligaciones beneficiadas.')
    if any(type(pk) is not int or pk<=0 for pk in obligaciones) or len(set(obligaciones))!=len(obligaciones):
        raise ValidationError('Lista de obligaciones inválida o repetida.')
    return {'decision':decision,'porcentaje':porcentaje,'conceptos':conceptos,'alcance':alcance,
            'obligaciones':sorted(obligaciones),'observaciones':observaciones}


def bloquear(usuario, solicitud_id):
    actor=Usuario.objects.select_for_update().get(pk=usuario.pk)
    if not actor.is_active or actor.rol!='DIRECTORA':
        raise PermissionDenied('Solo la Directora activa puede resolver solicitudes de beca.')
    referencia=SolicitudBeca.objects.get(pk=solicitud_id)
    matricula_previa=Matricula.objects.get(pk=referencia.matricula_id)
    estudiante=Estudiante.objects.select_for_update().get(pk=matricula_previa.estudiante_id)
    matricula=Matricula.objects.select_for_update().get(pk=referencia.matricula_id)
    if matricula.estudiante_id!=estudiante.pk:
        raise ValidationError('Las relaciones de matrícula cambiaron.')
    # Misma serialización por estudiante y obligaciones que registrar_pago.
    obligaciones=list(Obligacion.objects.select_for_update().filter(matricula=matricula).order_by('pk'))
    solicitud=SolicitudBeca.objects.select_for_update().get(pk=solicitud_id)
    return actor,estudiante,matricula,obligaciones,solicitud


def plan(matricula, obligaciones, resolucion):
    if matricula.estado!='ACTIVA':
        raise ValidationError('La matrícula ya no está activa.')
    seleccion={o.pk:o for o in obligaciones}
    hoy=timezone.localdate()
    filas=[]
    for pk in resolucion['obligaciones']:
        o=seleccion.get(pk)
        if o is None:
            raise ValidationError('Una obligación no pertenece a la matrícula solicitada.')
        concepto=normalizar_concepto(o.concepto.nombre)
        if concepto not in resolucion['conceptos'] or o.concepto.estado not in ('ACTIVO','ACTIVA'):
            raise ValidationError(f'Obligación #{pk}: concepto no autorizado o inactivo.')
        if o.estado=='ANULADA':
            raise ValidationError(f'Obligación #{pk}: está anulada.')
        vencida=o.fecha_vencimiento<hoy
        if (resolucion['alcance']=='VENCIDAS' and not vencida) or (resolucion['alcance']=='NO_VENCIDAS' and vencida):
            raise ValidationError(f'Obligación #{pk}: el vencimiento no corresponde al alcance autorizado.')
        if ConvenioObligacion.objects.filter(obligacion=o,convenio__estado__in=['ACTIVO','CUMPLIDO']).exists():
            raise ValidationError(f'Obligación #{pk}: cubierta por un convenio activo o cumplido.')
        if o.monto_descuento!=0 or AplicacionBeca.objects.filter(obligacion=o).exists():
            raise ValidationError(f'Obligación #{pk}: ya tiene descuentos o aplicaciones; no se acumulan ni sustituyen.')
        pagado,donado,saldo=importes(o)
        if saldo<=0 or o.estado=='PAGADA':
            raise ValidationError(f'Obligación #{pk}: está saldada.')
        descuento=o.monto_original*Decimal(resolucion['porcentaje'])/Decimal('100')
        if descuento<=0 or descuento!=descuento.quantize(Decimal('.01')):
            raise ValidationError(f'Obligación #{pk}: descuento sin representación exacta en centavos; requiere definición institucional antes de aplicarse.')
        if descuento>saldo:
            raise ValidationError(f'Obligación #{pk}: descuento USD {descuento:.2f} supera saldo USD {saldo:.2f}. No se generan devoluciones ni créditos.')
        # Datos financieros relevantes y versiones conservadoras de pagos/donaciones.
        filas.append({'id':pk,'descripcion':o.descripcion,'concepto':concepto,'vencimiento':str(o.fecha_vencimiento),
            'original':str(o.monto_original),'descuento_anterior':str(o.monto_descuento),
            'pagado':str(pagado),'donado':str(donado),'saldo_anterior':str(saldo),
            'descuento':str(descuento.quantize(Decimal('.01'))),'saldo_nuevo':str((saldo-descuento).quantize(Decimal('.01'))),
            'estado_anterior':o.estado,
            'pagos':list(DetallePago.objects.filter(obligacion=o).order_by('pk').values('pk','pago_id','monto_aplicado','pago__estado')),
            'donaciones':list(Donacion.objects.filter(obligacion=o).order_by('pk').values('pk','monto','estado'))})
    # JSON canónico: fechas/decimales como texto y sin datos personales innecesarios.
    import json
    return json.loads(json.dumps({'fecha':str(hoy),'matricula':matricula.pk,'estudiante':matricula.estudiante_id,
                                 'ciclo':matricula.ciclo_id,'filas':filas},default=str,sort_keys=True))


def previsualizar(*,usuario,solicitud_id,**datos):
    resolucion=datos_resolucion('APROBADA',**datos)
    with transaction.atomic():
        _,_,matricula,obligaciones,solicitud=bloquear(usuario,solicitud_id)
        if solicitud.estado!='PENDIENTE':
            raise ValidationError('La solicitud ya está resuelta.')
        if solicitud.contexto!=contexto_matricula(matricula):
            raise ValidationError('La matrícula cambió desde la solicitud. Rechace y solicite una nueva revisión.')
        propuesta=plan(matricula,obligaciones,resolucion)
        token=signing.dumps({'solicitud':solicitud.pk,'directora':usuario.pk,'resolucion':resolucion,'plan':propuesta},salt='vidasys-beca')
        return propuesta,token


def resolver(*,usuario,solicitud_id,decision,revision='',**datos):
    resolucion=datos_resolucion(decision,**datos)
    with transaction.atomic():
        actor,estudiante,matricula,obligaciones,solicitud=bloquear(usuario,solicitud_id)
        if solicitud.estado!='PENDIENTE':
            if solicitud.estado!=decision or solicitud.resolucion!=resolucion:
                raise ValidationError('La solicitud ya fue resuelta con otros datos.')
            return solicitud
        if decision=='APROBADA':
            if solicitud.contexto!=contexto_matricula(matricula):
                raise ValidationError('La matrícula cambió desde la solicitud. Rechace y solicite una nueva revisión.')
            propuesta=plan(matricula,obligaciones,resolucion)
            try:
                firmado=signing.loads(revision,salt='vidasys-beca',max_age=7200)
            except signing.BadSignature:
                raise ValidationError('Revise nuevamente los importes antes de aprobar.')
            if firmado!={'solicitud':solicitud.pk,'directora':actor.pk,'resolucion':resolucion,'plan':propuesta}:
                raise ValidationError('Los datos cambiaron. Compare nuevamente; no se aplicó la beca.')
            fechas=[o.fecha_vencimiento for o in obligaciones if o.pk in resolucion['obligaciones']]
            beca=Beca(matricula=matricula,usuario_autoriza=actor,porcentaje=resolucion['porcentaje'],
                fecha_aprobacion=timezone.localdate(),fecha_inicio=min(fechas),fecha_fin=max(fechas),
                estado='ACTIVA',observaciones=resolucion['observaciones'])
            beca.full_clean();beca.save()
            por_id={o.pk:o for o in obligaciones}
            for fila in propuesta['filas']:
                o=por_id[fila['id']]
                aplicacion=AplicacionBeca(beca=beca,obligacion=o,monto_aplicado=Decimal(fila['descuento']),
                    fecha_aplicacion=timezone.now(),estado='APLICADA')
                aplicacion.full_clean();aplicacion.save()
                o.monto_descuento=Decimal(fila['descuento'])
                o.full_clean();o.save(update_fields=['monto_descuento'])
                o.actualizar_estado()
                fila['estado_aplicado']=o.estado
            solicitud.beca=beca
            solicitud.aplicados={'plan':propuesta,'solvente':solvente(estudiante),'beca':beca.pk}
        solicitud.estado=decision
        solicitud.directora=actor
        solicitud.fecha_resolucion=timezone.now()
        solicitud.resolucion=resolucion
        solicitud.save(update_fields=['estado','directora','fecha_resolucion','resolucion','aplicados','beca'])
        return solicitud
