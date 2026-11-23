"""Fuentes únicas de dinero F7. No sumar Pago + aplicaciones + MovimientoCaja."""
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone
from financiero.models import (Pago,DetallePago,Ingreso,Egreso,Donacion,AplicacionPagoCuota)

CERO=Decimal('0.00')
ORIGENES={
 'MATRICULA':'Matrículas recibidas','MENSUALIDAD':'Mensualidades recibidas',
 'CONVENIO':'Pagos mediante convenios','ACADEMICO_OTRO':'Otros cobros académicos',
 'ADMINISTRATIVO':'Ingresos administrativos','DON_GENERAL':'Donaciones generales',
 'DON_DIRIGIDA':'Donaciones dirigidas','DON_PADRINAZGO':'Aportes de padrinazgos recibidos',
 'EGRESO':'Egresos desembolsados','NO_CONCILIADO':'Registro pendiente de conciliación',
}


@dataclass
class Dinero:
    fuente:str
    pk:int
    numero:str
    fecha:object
    origen:str
    categoria:str
    importe:Decimal
    estado:str
    metodo:str
    operador:str
    operador_id:int
    estudiante:str=''
    url:str=''
    motivo:str=''
    autorizador:str=''
    anulacion:object=None
    autorizador_id:int|None=None

    @property
    def vigente(self):return self.estado=='REGISTRADO' and self.origen!='NO_CONCILIADO'
    @property
    def salida(self):return self.origen=='EGRESO'


def dia(fecha):
    return timezone.localdate(fecha) if isinstance(fecha,datetime) else fecha


def acotar(qs,fecha,f):
    if f.get('desde'):qs=qs.filter(**{fecha+'__date__gte':f['desde']})
    if f.get('hasta'):qs=qs.filter(**{fecha+'__date__lte':f['hasta']})
    if f.get('metodo'):qs=qs.filter(metodo_pago=f['metodo'])
    campo='usuario_id' if qs.model==Pago else 'usuario_registra_id'
    if f.get('operador'):qs=qs.filter(**{campo:f['operador'].pk})
    return qs


def coincide_obligacion(o,f):
    return (not f.get('ciclo') or o.matricula.ciclo_id==f['ciclo'].pk) and (not f.get('estudiante') or o.matricula.estudiante_id==f['estudiante'].pk)


def cargar_dinero(f):
    filas=[];avisos=[]
    pagos=acotar(Pago.objects.select_related('estudiante','usuario'),'fecha_pago',f)
    if f.get('estudiante'):pagos=pagos.filter(estudiante=f['estudiante'])
    detalles=DetallePago.objects.select_related('obligacion__concepto','obligacion__matricula')
    pagos=pagos.prefetch_related(Prefetch('detalles',queryset=detalles,to_attr='detalles_f7'))
    es_convenio=set(AplicacionPagoCuota.objects.filter(pago__in=pagos).values_list('pago_id',flat=True))
    from financiero.models import SolicitudAnulacion
    anulaciones={a.pago_id:a for a in SolicitudAnulacion.objects.filter(pago__in=pagos,estado='APROBADA').select_related('directora')}
    categoria=f.get('categoria') or ''
    for p in pagos:
        grupos={};seleccion=[]
        for d in p.detalles_f7:
            o=d.obligacion
            if not coincide_obligacion(o,f):continue
            if categoria.startswith('C:') and o.concepto_id!=int(categoria[2:]):continue
            if categoria.startswith(('I:','E:')):continue
            nombre=o.concepto.nombre.upper().replace('Í','I')
            origen='CONVENIO' if p.pk in es_convenio else 'MATRICULA' if nombre=='MATRICULA' else 'MENSUALIDAD' if nombre=='MENSUALIDAD' else 'ACADEMICO_OTRO'
            key=(origen,o.concepto.nombre);grupos[key]=grupos.get(key,CERO)+d.monto_aplicado;seleccion.append(d)
        if categoria.startswith(('I:','E:')) or (f.get('ciclo') and not seleccion):continue
        suma=sum((d.monto_aplicado for d in p.detalles_f7),CERO)
        if suma!=p.monto_total:
            # No inventar atribución del remanente: se registra como incidencia fuera de totales.
            avisos.append(f'{p.numero_recibo}: total y aplicaciones no concilian; revise el recibo original.')
            grupos={('NO_CONCILIADO','Pago con aplicaciones inconsistentes'):sum((d.monto_aplicado for d in seleccion),CERO) if f.get('ciclo') or categoria else p.monto_total}
        elif f.get('ciclo') and not seleccion:continue
        a=anulaciones.get(p.pk)
        for (origen,concepto),monto in grupos.items():
            filas.append(Dinero('Pago',p.pk,p.numero_recibo,p.fecha_pago,origen,concepto,monto,p.estado,p.metodo_pago,
                p.usuario.numero_usuario,p.usuario_id,f'{p.estudiante.codigo_estudiante} · {p.estudiante.nombres} {p.estudiante.apellidos}',
                reverse('finanzas_recibo',args=[p.pk]),a.motivo if a else '',a.directora.numero_usuario if a else '',a.fecha_resolucion if a else None,a.directora_id if a else None))
    ingresos=acotar(Ingreso.objects.select_related('categoria_ingreso','usuario_registra','usuario_anula',
        'registro_institucional','recepcion_donacion__matricula__estudiante','donacion__obligacion__matricula'),'fecha_ingreso',f)
    for i in ingresos:
        if categoria and (not categoria.startswith('I:') or i.categoria_ingreso_id!=int(categoria[2:])):continue
        recepcion=getattr(i,'recepcion_donacion',None);registro=getattr(i,'registro_institucional',None);legado=getattr(i,'donacion',None)
        # Un vínculo histórico Donacion es compatible con la misma recepción F6, no otro ingreso.
        conflicto=bool(registro and (recepcion or legado))
        origen='NO_CONCILIADO';url='';nombre='';cantidad=i.monto
        if recepcion:
            origen={'GENERAL':'DON_GENERAL','DIRIGIDA':'DON_DIRIGIDA','PADRINAZGO':'DON_PADRINAZGO'}.get(recepcion.datos.get('modalidad'),'NO_CONCILIADO')
            if f.get('ciclo') or f.get('estudiante'):
                if not recepcion.matricula_id or (f.get('ciclo') and recepcion.matricula.ciclo_id!=f['ciclo'].pk) or (f.get('estudiante') and recepcion.matricula.estudiante_id!=f['estudiante'].pk):continue
            nombre=str(recepcion.matricula.estudiante) if recepcion.matricula_id else ''
            url=reverse('aportes_recibo',args=[recepcion.pk]);numero=recepcion.numero
        elif legado:
            origen='DON_PADRINAZGO' if legado.padrinazgo_id else 'DON_DIRIGIDA' if legado.obligacion_id else 'DON_GENERAL'
            if f.get('ciclo') or f.get('estudiante'):
                if not legado.obligacion_id or not coincide_obligacion(legado.obligacion,f):continue
            numero=f'Donación histórica vinculada a ingreso {i.pk}'
        elif registro:
            if f.get('ciclo') or f.get('estudiante'):continue
            origen='ADMINISTRATIVO';numero=registro.numero;url=reverse('operaciones_ingreso',args=[registro.pk])
        else:
            if f.get('ciclo') or f.get('estudiante'):continue
            numero=f'Ingreso histórico {i.pk}'
        if conflicto:origen='NO_CONCILIADO'
        if origen=='NO_CONCILIADO':avisos.append(f'Ingreso {i.pk}: origen no conciliado; excluido del resultado verificado.')
        filas.append(Dinero('Ingreso',i.pk,numero,i.fecha_ingreso,origen,i.categoria_ingreso.nombre,cantidad,i.estado,i.metodo_pago,
            i.usuario_registra.numero_usuario,i.usuario_registra_id,nombre,url,i.motivo_anulacion or '',
            i.usuario_anula.numero_usuario if i.usuario_anula_id else '',i.fecha_anulacion,i.usuario_anula_id))
    # Donaciones históricas recibidas sin ingreso ni aplicación F6: fuente independiente explícita.
    donaciones=Donacion.objects.filter(ingreso__isnull=True,aplicacion_institucional__isnull=True,estado__in=('RECIBIDA','ANULADA')).select_related('obligacion__matricula','usuario_registra')
    for d in donaciones:
        if categoria:continue
        if f.get('ciclo') or f.get('estudiante'):
            if not d.obligacion_id or not coincide_obligacion(d.obligacion,f):continue
        if not d.fecha_ingreso:
            if not d.fecha_ingreso:avisos.append(f'Donación histórica {d.pk}: fecha efectiva no verificable; no se incluye en el período.')
            continue
        if f.get('desde') and d.fecha_ingreso<f['desde'] or f.get('hasta') and d.fecha_ingreso>f['hasta']:continue
        if f.get('metodo') and d.metodo_pago!=f['metodo'] or f.get('operador') and d.usuario_registra_id!=f['operador'].pk:continue
        if f.get('ciclo') or f.get('estudiante'):
            if not d.obligacion_id or not coincide_obligacion(d.obligacion,f):continue
        origen='DON_PADRINAZGO' if d.padrinazgo_id else 'DON_DIRIGIDA' if d.obligacion_id else 'DON_GENERAL'
        fecha=d.fecha_ingreso
        filas.append(Dinero('Donacion',d.pk,f'Donación histórica {d.pk}',fecha,origen,'Aporte histórico',d.monto,
            'REGISTRADO' if d.estado=='RECIBIDA' else 'ANULADO',d.metodo_pago or 'No consta',d.usuario_registra.numero_usuario,d.usuario_registra_id))
    egresos=acotar(Egreso.objects.select_related('categoria_egreso','usuario_registra','usuario_anula','desembolso_institucional'),'fecha_egreso',f)
    if not f.get('ciclo') and not f.get('estudiante'):
        for e in egresos:
            if categoria and (not categoria.startswith('E:') or e.categoria_egreso_id!=int(categoria[2:])):continue
            d=getattr(e,'desembolso_institucional',None)
            origen='EGRESO' if d else 'NO_CONCILIADO'
            if not d:avisos.append(f'Egreso histórico {e.pk}: desembolso no verificable; excluido del resultado verificado.')
            filas.append(Dinero('Egreso',e.pk,e.numero_egreso,e.fecha_egreso,origen,e.categoria_egreso.nombre,e.monto,e.estado,e.metodo_pago,
                e.usuario_registra.numero_usuario,e.usuario_registra_id,'',reverse('operaciones_egreso',args=[d.solicitud_id]) if d else '',
                e.motivo_anulacion or '',e.usuario_anula.numero_usuario if e.usuario_anula_id else '',e.fecha_anulacion,e.usuario_anula_id))
    if f.get('origen'):
        clave=f['origen'];grupos={'ACADEMICOS':{'MATRICULA','MENSUALIDAD','CONVENIO','ACADEMICO_OTRO'},'DONACIONES':{'DON_GENERAL','DON_DIRIGIDA','DON_PADRINAZGO'}}
        filas=[m for m in filas if m.origen in grupos.get(clave,{clave})]
    if f.get('estado'):filas=[m for m in filas if m.estado==f['estado']]
    return sorted(filas,key=lambda m:(dia(m.fecha),m.fuente,m.pk),reverse=True),list(dict.fromkeys(avisos))
