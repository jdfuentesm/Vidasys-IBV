"""F7: proyecciones de consulta, sin ajustes contables, registros ni tablas nuevas."""
from collections import defaultdict
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from django.db.models import Prefetch,Sum
from django.urls import reverse
from django.utils import timezone
from academico.models import Estudiante,Matricula
from financiero.lectura import EstadoFinanciero
from financiero.models import (Beca,AplicacionBeca,SolicitudPadrinazgo,RevisionPadrinazgo,
    SolicitudBeca,SolicitudConvenio,RevisionConvenio,SolicitudEgreso,SolicitudAnulacion,
    SolicitudAnulacionOperacion,AnulacionDonacion,Caja,MovimientoCaja,CoberturaPadrinazgo,LineaDonacion)
from .financiero_fuentes import cargar_dinero,ORIGENES,dia

CERO=Decimal('0.00')
NOTA_PERIODO=('Operaciones con fecha efectiva dentro del período y estado vigente al generar. '
    'Una anulación posterior se refleja hoy; no se reconstruye un cierre histórico. '
    'Estado de resultados simplificado sobre base de efectivo; no es un estado contable completo.')
NOTA_SALDOS='Saldos actuales al generar, sin fecha de corte histórica. Las cuotas de convenios no se suman nuevamente a las obligaciones originales.'


def dinero(v):return f'USD {v:.2f}'


def valor(v):
    if v is None:return 'No consta'
    if isinstance(v,Decimal):return dinero(v)
    if isinstance(v,datetime):return timezone.localtime(v).strftime('%d/%m/%Y %H:%M')
    if isinstance(v,date):return v.strftime('%d/%m/%Y')
    if isinstance(v,bool):return 'Sí' if v else 'No'
    return str(v)


def resultado(columnas,filas,totales,nota,avisos=()):
    return {'columnas':columnas,'filas':filas,'totales':totales,'nota':nota,'avisos':list(dict.fromkeys(avisos))}


def fila(*celdas,url=''):return {'celdas':list(celdas),'url':url}


def seleccion_estudiantes(f):
    qs=Estudiante.objects.order_by('apellidos','nombres','pk')
    if f.get('estudiante'):qs=qs.filter(pk=f['estudiante'].pk)
    if f.get('ciclo'):qs=qs.filter(pk__in=Matricula.objects.filter(ciclo=f['ciclo']).values('estudiante_id'))
    return list(qs)


def seleccion_obligaciones(ctx,f):
    return [r for r in ctx.filas if not r['anulada'] and (not f.get('ciclo') or r['obligacion'].matricula.ciclo_id==f['ciclo'].pk)]


def periodo(qs,campo,f,es_fecha=False):
    campo=campo if es_fecha else campo+'__date'
    if f.get('desde'):qs=qs.filter(**{campo+'__gte':f['desde']})
    if f.get('hasta'):qs=qs.filter(**{campo+'__lte':f['hasta']})
    return qs


def movimientos(f):
    datos,avisos=cargar_dinero(f)
    ingresos=sum((m.importe for m in datos if m.vigente and not m.salida),CERO)
    egresos=sum((m.importe for m in datos if m.vigente and m.salida),CERO)
    filas=[fila(m.numero,m.fecha,ORIGENES[m.origen],m.categoria,m.estudiante or 'Institucional',m.operador,m.metodo,m.estado,m.importe,url=m.url) for m in datos]
    por_origen=defaultdict(lambda:CERO);por_categoria=defaultdict(lambda:CERO)
    for m in datos:
        if m.vigente:
            por_origen[m.origen]+=m.importe
            if m.salida:por_categoria[m.categoria]+=m.importe
    nota=NOTA_PERIODO
    if f.get('ciclo') or f.get('estudiante'):nota+=' Con ciclo/estudiante solo se incluyen aplicaciones verificables; ingresos generales y gastos institucionales no se atribuyen por coincidencias. Los pagos de convenio conservan su origen exclusivo.'
    res=resultado(['Comprobante o referencia','Fecha efectiva','Origen exclusivo','Categoría','Estudiante o destino','Operador','Método','Estado actual','Importe'],filas,
        [('Ingresos vigentes verificados',ingresos),('Egresos desembolsados vigentes',egresos),('Resultado de la selección',ingresos-egresos),
         ('Operaciones anuladas (informativo, no sumar)',sum((m.importe for m in datos if m.estado=='ANULADO'),CERO)),
         ('Importes sin conciliación excluidos',sum((m.importe for m in datos if m.origen=='NO_CONCILIADO'),CERO))],nota,avisos)
    res['resumen_origen']=[(ORIGENES[o],n) for o,n in sorted(por_origen.items()) if o!='EGRESO']
    res['resumen_egresos']=sorted(por_categoria.items())
    return res


def cuentas(f,ctx=None):
    ctx=ctx or EstadoFinanciero(seleccion_estudiantes(f));datos=seleccion_obligaciones(ctx,f);filas=[];avisos=[]
    if f.get('estado')=='VENCIDA':datos=[r for r in datos if r['vencida'] and r['saldo']>0]
    elif f.get('estado')=='NO_VENCIDA':datos=[r for r in datos if not r['vencida'] and r['saldo']>0]
    elif f.get('estado')=='SALDADA':datos=[r for r in datos if r['saldo']==0]
    for r in datos:
        o=r['obligacion'];e=o.matricula.estudiante
        filas.append(fila(str(e),str(o.matricula.ciclo),o.descripcion,o.fecha_vencimiento,
            'Vencida' if r['vencida'] and r['saldo']>0 else 'No vencida' if r['saldo']>0 else 'Saldada',
            o.monto_original,o.monto_descuento,r['pagado'],r['donado'],r['saldo'],r['cobertura'],r['convenio'],r['directo'],r['cargo_estudiante'],r['cargo_estudiante'] if r['vencida'] and not any(c.estado in ('ACTIVO','CUMPLIDO') for c in ctx.convenios_obligacion[o.pk]) else CERO,r['reserva'],url=reverse('finanzas_cuenta',args=[e.pk])))
        if r['sobreaplicado']>0:avisos.append(f'{o.matricula.numero_matricula} · {o.descripcion}: aplicaciones superiores al importe neto; no se genera crédito.')
        if r['cobertura']>0 and r['convenio']>0:avisos.append(f'{o.matricula.numero_matricula}: existen coberturas de padrinazgo y convenio; revisar integridad del vínculo.')
    suma=lambda clave:sum((r[clave] for r in datos),CERO)
    saldo=suma('saldo');pad=suma('cobertura');conv=suma('convenio');directo=suma('directo')
    return resultado(['Estudiante','Ciclo','Obligación','Vencimiento','Situación','Original','Descuento existente','Pagos aplicados','Donaciones aplicadas','Saldo financiero',
        'Protegido por padrinazgo','En convenio (sin sumar de nuevo)','Directo sin convenio','Total a cargo del estudiante','Vencido exigible fuera de convenio vigente','Compromiso de padrino pendiente de recepción (informativo)'],filas,
        [('Saldo financiero pendiente',saldo),('Protección pendiente efectiva',pad),('Compromisos activos de padrinos pendientes (informativo)',suma('reserva')),('Saldo en convenio',conv),('Saldo directo del estudiante',directo),
         ('A cargo del estudiante, incluido convenio y no vencido',conv+directo),('Control: padrinazgo + convenio + directo',pad+conv+directo)],
        NOTA_SALDOS+' Distribución excluyente: padrinazgo + convenio + directo = saldo financiero. El total a cargo del estudiante incluye su convenio y saldos no vencidos; no es una cuarta categoría para sumar. El vencido exigible por obligación excluye convenios vigentes; sus cuotas vencidas se consultan en Convenios sin duplicar originales.',avisos)


def solvencia(f,ctx=None):
    ctx=ctx or EstadoFinanciero(seleccion_estudiantes(f));filas=[];contadores=defaultdict(int)
    etiquetas={'SOLVENTE':'Solvente','INSOLVENTE':'Insolvente','PADRINAZGO':'Solvente por padrinazgo','CONVENIO':'Solvente mediante convenio','COMBINADA':'Solvente con beneficios combinados'}
    for e in ctx.estudiantes:
        s=ctx.solvencias[e.pk]
        if f.get('estado') and s['clase']!=f['estado']:continue
        contadores[s['clase']]+=1
        filas.append(fila(str(e),etiquetas[s['clase']],s['saldo_financiero'],s['cobertura_autorizada'],s['saldo_estudiante'],url=reverse('finanzas_cuenta',args=[e.pk])))
    return resultado(['Estudiante','Clasificación única','Saldo financiero actual','Protección pendiente','Saldo a su cargo'],filas,
        [('Estudiantes distintos de la selección',len(filas))]+[(etiquetas[k],contadores[k]) for k in etiquetas],
        'Mismo servicio de lectura de solvencia que el portal, incluida F6. Cada estudiante pertenece a una sola categoría. El ciclo selecciona estudiantes, pero la solvencia considera todo su expediente, incluidas otras deudas. No sustituye permisos de cuenta ni reglas académicas. Unificación definitiva Django/SQL obligatoria antes del despliegue.')


def beneficios(f,ctx=None):
    ctx=ctx or EstadoFinanciero(seleccion_estudiantes(f));oids=[r['obligacion'].pk for r in seleccion_obligaciones(ctx,f)]
    aplicaciones=AplicacionBeca.objects.filter(obligacion_id__in=oids,estado='APLICADA').select_related('obligacion__matricula__estudiante','obligacion__matricula__ciclo')
    becas=periodo(Beca.objects.filter(aplicaciones__in=aplicaciones).distinct().select_related('matricula__estudiante','matricula__ciclo'),'fecha_aprobacion',f,True)
    mapa=defaultdict(list)
    for a in aplicaciones:mapa[a.beca_id].append(a)
    filas=[];exonerado=CERO;beneficiados=set();comprometido=recibido=pendiente=protegido=CERO
    if f.get('beneficio')!='PADRINAZGOS':
        for b in becas:
            estado='VIGENTE' if b.estado=='ACTIVA' else 'CANCELADO'
            if f.get('estado') and f['estado']!=estado:continue
            n=sum((a.monto_aplicado for a in mapa[b.pk]),CERO);exonerado+=n;beneficiados.add(b.matricula.estudiante_id)
            filas.append(fila('Beca',str(b.matricula.estudiante),str(b.matricula.ciclo),f'{b.porcentaje} %',estado,b.fecha_aprobacion,n,None,None,None,
                'Descuento, sin salida de caja'))
    solicitudes=periodo(SolicitudPadrinazgo.objects.filter(estado='APROBADA',matricula__estudiante_id__in=[e.pk for e in ctx.estudiantes]).select_related('padrinazgo','matricula__estudiante','matricula__ciclo'),'fecha_resolucion',f)
    if f.get('beneficio')=='BECAS':solicitudes=solicitudes.none()
    if f.get('ciclo'):solicitudes=solicitudes.filter(matricula__ciclo=f['ciclo'])
    coberturas=list(CoberturaPadrinazgo.objects.filter(solicitud__in=solicitudes).select_related('obligacion'))
    importes_aporte=dict(LineaDonacion.objects.filter(cobertura__in=coberturas,donacion__estado='RECIBIDA').values('cobertura_id').annotate(n=Sum('donacion__monto')).values_list('cobertura_id','n'))
    cs=defaultdict(list)
    for c in coberturas:cs[c.solicitud_id].append(c)
    revisiones=RevisionPadrinazgo.objects.filter(solicitud__in=solicitudes).order_by('fecha','pk').values('solicitud_id','accion','motivo','fecha')
    historias=defaultdict(list)
    for r in revisiones:historias[r['solicitud_id']].append(r['accion']+' · '+r['motivo'])
    if f.get('beneficio')!='BECAS':
        for s in solicitudes:
            total=sum((c.monto for c in cs[s.pk]),CERO);real=sum((importes_aporte.get(c.pk,CERO) for c in cs[s.pk]),CERO)
            falta=sum((max(c.monto-importes_aporte.get(c.pk,CERO),CERO) for c in cs[s.pk] if c.activa),CERO)
            proteccion=sum((min(max(c.monto-importes_aporte.get(c.pk,CERO),CERO),ctx.por_obligacion[c.obligacion_id]['saldo']) for c in cs[s.pk] if c.activa and s.padrinazgo.fecha_inicio<=ctx.hoy and c.obligacion_id in ctx.por_obligacion),CERO)
            estado='CANCELADO' if s.padrinazgo.estado!='ACTIVO' else 'CUMPLIDO' if falta==0 else 'VENCIDO' if s.padrinazgo.fecha_fin<ctx.hoy else 'VIGENTE'
            if f.get('estado') and f['estado']!=estado:continue
            comprometido+=total;recibido+=real;pendiente+=falta;protegido+=proteccion;beneficiados.add(s.matricula.estudiante_id)
            filas.append(fila('Padrinazgo',str(s.matricula.estudiante),str(s.matricula.ciclo),s.propuesta['modalidad'],estado,s.padrinazgo.fecha_fin,total,real,falta,proteccion,
                '; '.join(historias[s.pk]) or 'Autorización original',url=reverse('aportes_solicitud',args=[s.pk])))
    return resultado(['Beneficio','Estudiante','Ciclo','Modalidad o porcentaje','Estado actual','Aprobación beca / límite padrinazgo','Exonerado o comprometido','Recibido aplicado','Pendiente de recepción activo','Protección efectiva','Resoluciones'],filas,
        [('Estudiantes beneficiados distintos',len(beneficiados)),('Becas exoneradas',exonerado),('Padrinazgos comprometidos históricos',comprometido),('Aportes recibidos aplicados',recibido),('Compromisos activos pendientes',pendiente),('Protección actual de la selección',protegido)],
        'Fechas seleccionan aprobación de beca o autorización de padrinazgo. Recibido, pendiente y protección son actuales, no al corte. Becas no son egresos y compromisos no son ingresos. No sumar columnas de naturaleza distinta. Los estudiantes combinados se cuentan una vez.')


def convenios(f,ctx=None):
    ctx=ctx or EstadoFinanciero(seleccion_estudiantes(f));filas=[];totales=defaultdict(lambda:CERO);avisos=[]
    enlaces=defaultdict(list)
    for e in ctx.enlaces:enlaces[e.convenio_id].append(e)
    for c in ctx.convenios:
        if f.get('estado') and c.estado!=f['estado']:continue
        if f.get('desde') and c.fecha_convenio<f['desde'] or f.get('hasta') and c.fecha_convenio>f['hasta']:continue
        obs=[ctx.por_obligacion[e.obligacion_id] for e in enlaces[c.pk] if e.obligacion_id in ctx.por_obligacion]
        if f.get('ciclo') and not any(r['obligacion'].matricula.ciclo_id==f['ciclo'].pk for r in obs):continue
        cuotas=ctx.cuotas_por_convenio[c.pk]
        real=sum((r['abonado'] for r in cuotas),CERO);saldo=sum((r['saldo'] for r in cuotas),CERO)
        original=sum((r['saldo'] for r in obs if not r['anulada']),CERO)
        diferencia=saldo-original
        if diferencia and c.estado!='CANCELADO':avisos.append(f'Convenio {c.pk}: cuota y obligaciones originales difieren; no se ajusta ni redistribuye dinero.')
        totales['monto']+=c.monto_convenido;totales['real']+=real;totales['saldo']+=saldo;totales['original']+=original
        filas.append(fila(str(c.estudiante),c.estado,c.fecha_convenio,c.monto_convenido,real,saldo,original,diferencia,sum(r['vencida'] for r in cuotas),url=reverse('convenios_detalle',args=[c.pk])))
    return resultado(['Estudiante','Estado','Fecha del convenio','Comprometido original','Recibido vigente','Saldo cuotas','Saldo obligaciones originales','Diferencia de conciliación','Cuotas vencidas'],filas,
        [('Convenios distintos',len(filas)),('Comprometido',totales['monto']),('Recibido',totales['real']),('Saldo de cuotas (informativo)',totales['saldo']),('Saldo de obligaciones (no sumar con cuotas)',totales['original'])],
        'Estado y saldos actuales; fechas filtran fecha del convenio. Con ciclo se incluyen convenios que contienen ese ciclo, mostrando el convenio íntegro, sin reparto implícito de cuotas. Un cancelado conserva historia; su deuda sigue en las obligaciones originales.',avisos)


def decimal_foto(foto,clave):
    try:
        n=Decimal(str(foto[clave]));return n if n.is_finite() else None
    except (KeyError,ValueError,TypeError,InvalidOperation):return None


def cajas(f):
    qs=Caja.objects.select_related('operador').order_by('-fecha_apertura','pk')
    qs=periodo(qs,'fecha_apertura',f)
    if f.get('operador'):qs=qs.filter(operador=f['operador'])
    if f.get('estado'):qs=qs.filter(estado=f['estado'])
    cajas=list(qs);abiertas=[c.pk for c in cajas if c.estado=='ABIERTA']
    movimientos=defaultdict(list)
    for m in MovimientoCaja.objects.filter(caja_id__in=abiertas).select_related('pago','ingreso','egreso').order_by('pk'):movimientos[m.caja_id].append(m)
    filas=[];avisos=[];retenido=CERO
    for c in cajas:
        if c.estado=='CERRADA':
            foto=c.cierre;fondo=decimal_foto(foto,'fondo');entradas=decimal_foto(foto,'entradas_efectivo');salidas=decimal_foto(foto,'salidas_efectivo')
            esperado=decimal_foto(foto,'esperado');ret=decimal_foto(foto,'efectivo_anulado_retenido')
            trans_in=trans_out=CERO
            if isinstance(foto.get('movimientos'),list):
                for m in foto['movimientos']:
                    if m.get('metodo')=='TRANSFERENCIA':
                        importe=decimal_foto(m,'importe')
                        if importe is None:
                            trans_in=trans_out=None;break
                        if m.get('egreso') or m.get('tipo')=='EGRESO':trans_out+=importe
                        else:trans_in+=importe
            else:trans_in=trans_out=None
            if any(v is None for v in (fondo,entradas,salidas,esperado,ret,trans_in,trans_out)):avisos.append(f'Caja {c.pk}: su foto histórica no contiene todos los campos; se muestra No consta, sin reconstruir con datos actuales.')
            contado=c.efectivo_contado;diferencia=c.diferencia
        else:
            fondo=c.fondo_inicial;entradas=salidas=trans_in=trans_out=ret=CERO
            for m in movimientos[c.pk]:
                salida=m.egreso_id is not None;origen=m.pago if m.pago_id else m.ingreso if m.ingreso_id else m.egreso
                if m.metodo=='EFECTIVO':
                    if salida:salidas+=m.importe
                    else:
                        entradas+=m.importe
                        if origen.estado!='REGISTRADO':ret+=m.importe
                elif salida:trans_out+=m.importe
                else:trans_in+=m.importe
            esperado=fondo+entradas-salidas;contado=diferencia=None
        if ret is not None:retenido+=ret
        filas.append(fila(f'Caja {c.pk}',c.operador.numero_usuario,c.estado,c.fecha_apertura,c.fecha_cierre,fondo,entradas,salidas,esperado,contado,diferencia,ret,trans_in,trans_out,url=reverse('caja_detalle',args=[c.pk])))
    return resultado(['Caja','Operador','Estado','Apertura','Cierre','Fondo inicial','Entradas físicas efectivo','Salidas físicas efectivo','Esperado','Contado','Diferencia','Efectivo retenido','Transferencias recibidas','Transferencias realizadas'],filas,
        [('Cajas',len(filas)),('Retenido conocido, no libremente disponible',retenido)],
        'Fechas filtran apertura. Cajas abiertas: lectura actual; cerradas: fotografía original, sin modificarla. Transferencias físicas registradas se informan aparte. Fondos iniciales no son ingresos. Estas transferencias no constituyen saldo ni conciliación bancaria.',avisos)


SOLICITUDES=[
 (SolicitudBeca,'Beca','fecha_solicitud','becas_detalle','solicitud_id'),
 (SolicitudConvenio,'Convenio','fecha_solicitud','convenios_solicitud','solicitud_id'),
 (SolicitudEgreso,'Egreso','fecha','operaciones_egreso','solicitud_id'),
 (SolicitudPadrinazgo,'Padrinazgo','fecha','aportes_solicitud','solicitud_id'),
 (SolicitudAnulacion,'Anulación de pago','fecha_solicitud','anulaciones_detalle','solicitud_id'),
 (SolicitudAnulacionOperacion,'Anulación de ingreso/egreso','fecha','operaciones_anulacion','solicitud_id'),
 (AnulacionDonacion,'Anulación de donación','fecha','aportes_anulacion','anulacion_id'),
]


def motivo_resolucion(s):
    r=getattr(s,'resolucion',None)
    if isinstance(r,dict):return str(r.get('observaciones') or r.get('motivo') or '')
    if r:return str(r)
    return str(getattr(s,'observaciones','') or getattr(s,'motivo',''))


def auditoria(f):
    eventos=[];avisos=[]
    def agregar(fecha,tipo,estado,responsable,motivo,referencia,importe=None,url='',responsable_id=None):
        if f.get('estado') and f['estado']!=estado:return
        if f.get('operador') and responsable_id!=f['operador'].pk:return
        if fecha is not None:
            if f.get('desde') and dia(fecha)<f['desde'] or f.get('hasta') and dia(fecha)>f['hasta']:return
        eventos.append((fecha,fila(fecha,tipo,estado,responsable,motivo,referencia,importe,url=url)))
    for modelo,tipo,campo,ruta,param in SOLICITUDES:
        qs=modelo.objects.select_related('solicitante','directora').order_by('pk')
        if modelo==SolicitudEgreso:qs=qs.select_related('desembolso')
        if f.get('estado')=='PENDIENTE':qs=qs.filter(estado='PENDIENTE')
        for s in qs:
            url=reverse(ruta,kwargs={param:s.pk});creacion=getattr(s,campo)
            motivo=str(getattr(s,'justificacion','') or getattr(s,'motivo','') or getattr(s,'observaciones',''))
            if modelo==SolicitudEgreso and s.estado=='APROBADA' and not hasattr(s,'desembolso'):
                agregar(s.fecha_resolucion,'Egreso autorizado sin desembolso','DESEMBOLSO_PENDIENTE',s.directora.numero_usuario if s.directora_id else 'No consta',motivo_resolucion(s),f'Solicitud {s.pk}',s.monto,url=url,responsable_id=s.directora_id)
            if s.estado=='PENDIENTE':agregar(creacion,'Solicitud de '+tipo,'PENDIENTE',s.solicitante.numero_usuario,motivo,f'Solicitud {s.pk}',url=url,responsable_id=s.solicitante_id)
            else:
                agregar(creacion,'Solicitud de '+tipo,'RESOLUCION',s.solicitante.numero_usuario,motivo,f'Solicitud {s.pk}',url=url,responsable_id=s.solicitante_id)
                agregar(s.fecha_resolucion,'Decisión de '+tipo,s.estado,s.directora.numero_usuario if s.directora_id else 'No consta',motivo_resolucion(s),f'Solicitud {s.pk}',url=url,responsable_id=s.directora_id)
    for r in RevisionPadrinazgo.objects.select_related('directora').order_by('pk'):
        agregar(r.fecha,'Resolución de padrinazgo: '+r.accion,'RESOLUCION',r.directora.numero_usuario,r.motivo,f'Padrinazgo solicitado {r.solicitud_id}',url=reverse('aportes_solicitud',args=[r.solicitud_id]),responsable_id=r.directora_id)
    for r in RevisionConvenio.objects.select_related('directora').order_by('pk'):
        agregar(r.fecha,'Resolución de convenio: '+r.accion,'RESOLUCION',r.directora.numero_usuario,r.motivo,f'Convenio {r.convenio_id}',url=reverse('convenios_detalle',args=[r.convenio_id]),responsable_id=r.directora_id)
    datos,problemas=cargar_dinero({})
    vistos=set();importes=defaultdict(lambda:CERO)
    for m in datos:importes[(m.fuente,m.pk)]+=m.importe
    for m in datos:
        if (m.fuente,m.pk) in vistos:continue
        vistos.add((m.fuente,m.pk))
        if m.estado=='ANULADO':
            agregar(m.anulacion,'Movimiento anulado','ANULADO',m.autorizador or 'Sin resolución verificable',m.motivo,m.numero,importes[(m.fuente,m.pk)],url=m.url,responsable_id=m.autorizador_id)
            if not m.anulacion:avisos.append(m.numero+': fecha de anulación no disponible; no se le atribuye una fecha inventada.')
        if m.origen=='NO_CONCILIADO':agregar(m.fecha,'Registro sin conciliación','REGULARIZACION',m.operador,'Origen o desembolso sin trazabilidad suficiente; excluido de resultado verificado.',m.numero,m.importe,url=m.url,responsable_id=m.operador_id)
    for c in cajas({k:v for k,v in f.items() if k in ('operador',)})['filas']:
        valores=c['celdas'];ret=valores[11]
        if ret is not None and ret>0:
            # Foto/estado físico, no un ingreso ni una devolución del período.
            if not f.get('estado') or f['estado']=='REGULARIZACION':
                eventos.append((None,fila(None,'Efectivo retenido registrado en caja','REGULARIZACION',valores[1],
                    'Situación física de caja o foto al cierre; requiere política de regularización. No es resultado financiero ni evento fechado en el período.',valores[0],ret,url=c['url'])))
    eventos.sort(key=lambda x:(x[0] is not None,str(x[0]) if x[0] else ''),reverse=True)
    return resultado(['Fecha del evento','Tipo','Estado','Responsable','Motivo o resolución','Referencia','Importe informativo, no sumar'],[r for _,r in eventos],
        [('Eventos y situaciones de la selección',len(eventos))],
        'Eventos del período y situaciones sin fecha verificable identificadas como tales. Incluye solicitudes, decisiones y resoluciones; no sumar importes repetidos de una misma operación. Las retenciones muestran situación actual o foto histórica, no una devolución. Sin acciones de escritura.',avisos+problemas)


def graficos(datos,f):
    meses=defaultdict(lambda:{'ingresos':CERO,'egresos':CERO});origenes=defaultdict(lambda:CERO)
    for m in datos:
        if m.vigente:
            mes=dia(m.fecha).strftime('%Y-%m');meses[mes]['egresos' if m.salida else 'ingresos']+=m.importe
            if not m.salida:origenes[m.origen]+=m.importe
    if not meses:return {'meses':[],'origenes':[],'nota':'Sin movimientos vigentes para graficar.'}
    fin=f.get('hasta') or max(dia(m.fecha) for m in datos if m.vigente)
    inicio=f.get('desde') or min(dia(m.fecha) for m in datos if m.vigente)
    fin_ind=fin.year*12+fin.month-1;inicio_ind=max(inicio.year*12+inicio.month-1,fin_ind-23)
    claves=[f'{n//12:04}-{n%12+1:02}' for n in range(inicio_ind,fin_ind+1)]
    escala=max([meses[k][c] for k in claves for c in ('ingresos','egresos')]+[Decimal('1')])
    series=[{'mes':k,**meses[k],'ancho_ingreso':str((meses[k]['ingresos']/escala*100).quantize(Decimal('.01'))),
        'ancho_egreso':str((meses[k]['egresos']/escala*100).quantize(Decimal('.01')))} for k in claves]
    total=sum(origenes.values(),CERO)
    return {'meses':series,'origenes':[{'nombre':ORIGENES[k],'importe':n,'ancho':str((n/total*100).quantize(Decimal('.01')))} for k,n in sorted(origenes.items())],
        'nota':'Evolución de hasta los últimos 24 meses de la selección. Los totales cubren todo el período; solo operaciones vigentes verificadas. Barras con etiquetas e importes, no solo color.'}


def panel(f):
    datos,avisos=cargar_dinero(f);ctx=EstadoFinanciero();corrientes=[r for r in ctx.filas if not r['anulada']]
    montos=defaultdict(lambda:CERO)
    for m in datos:
        if m.vigente:montos[m.origen]+=m.importe
    ingresos=sum((v for k,v in montos.items() if k!='EGRESO'),CERO);egresos=montos['EGRESO']
    desde=f.get('desde');hasta=f.get('hasta')
    def enlace(tipo,**extra):
        from urllib.parse import urlencode
        params={**extra}
        if tipo in ('resultados','beneficios'):params.update(desde=str(desde) if desde else '',hasta=str(hasta) if hasta else '')
        if tipo=='auditoria':params.update(desde='',hasta='')
        return reverse('finanzas_reporte',args=[tipo])+('?' + urlencode(params) if params else '')
    def tarjeta(titulo,n,tipo,**params):return {'titulo':titulo,'valor':valor(n),'url':enlace(tipo,**params)}
    becas=beneficios({'desde':desde,'hasta':hasta,'beneficio':'BECAS'},ctx)
    exonerado=dict(becas['totales'])['Becas exoneradas']
    pendientes=sum(m.objects.filter(estado='PENDIENTE').count() for m,*_ in SOLICITUDES)
    egs=SolicitudEgreso.objects.filter(estado='APROBADA',desembolso__isnull=True)
    total_egs=egs.aggregate(n=Sum('monto'))['n'] or CERO
    operaciones=[tarjeta('Ingresos académicos recibidos',sum((montos[k] for k in ('MATRICULA','MENSUALIDAD','CONVENIO','ACADEMICO_OTRO')),CERO),'resultados',origen='ACADEMICOS'),
        tarjeta('Ingresos administrativos',montos['ADMINISTRATIVO'],'resultados',origen='ADMINISTRATIVO'),
        tarjeta('Donaciones recibidas',sum((montos[k] for k in ('DON_GENERAL','DON_DIRIGIDA','DON_PADRINAZGO')),CERO),'resultados',origen='DONACIONES'),
        tarjeta('Egresos desembolsados',egresos,'resultados',origen='EGRESO'),tarjeta('Resultado financiero verificado',ingresos-egresos,'resultados'),
        tarjeta('Becas otorgadas en el período (no son egresos)',exonerado,'beneficios',beneficio='BECAS')]
    actuales=[tarjeta('Cuentas pendientes de cobro',sum((r['saldo'] for r in corrientes),CERO),'cuentas'),
        tarjeta('Saldo a cargo de estudiantes, incluido convenio',sum((r['cargo_estudiante'] for r in corrientes),CERO),'cuentas'),
        tarjeta('Compromisos activos de padrinos pendientes de recepción',sum((r['reserva'] for r in corrientes),CERO),'beneficios',beneficio='PADRINAZGOS'),
        tarjeta('Cobertura de padrinazgo pendiente efectiva',sum((r['cobertura'] for r in corrientes),CERO),'beneficios',beneficio='PADRINAZGOS'),
        tarjeta('Convenios vigentes',sum(c.estado=='ACTIVO' for c in ctx.convenios),'convenios',estado='ACTIVO'),
        tarjeta('Convenios incumplidos',sum(c.estado=='INCUMPLIDO' for c in ctx.convenios),'convenios',estado='INCUMPLIDO'),
        tarjeta('Egresos autorizados pendientes (cantidad)',egs.count(),'auditoria',estado='DESEMBOLSO_PENDIENTE'),
        tarjeta('Importe autorizado aún sin desembolsar',total_egs,'auditoria',estado='DESEMBOLSO_PENDIENTE'),
        tarjeta('Solicitudes pendientes de autorización',pendientes,'auditoria',estado='PENDIENTE'),
        tarjeta('Cajas abiertas',Caja.objects.filter(estado='ABIERTA').count(),'cajas',estado='ABIERTA'),
        tarjeta('Cajas cerradas',Caja.objects.filter(estado='CERRADA').count(),'cajas',estado='CERRADA')]
    # La cobertura actual no debe arrastrar el período de flujos al abrir su detalle.
    for t in actuales:
        if 'padrinazgo' in t['titulo'] or 'padrinos' in t['titulo']:t['url']=reverse('finanzas_reporte',args=['beneficios'])+'?beneficio=PADRINAZGOS&desde=&hasta='
    res=resultado([],[],[('Ingresos efectivos vigentes verificados',ingresos),('Egresos efectivos vigentes',egresos),('Resultado del período seleccionado',ingresos-egresos)],NOTA_PERIODO,avisos)
    res.update(tarjetas_periodo=operaciones,tarjetas_actuales=actuales,graficos=graficos(datos,f))
    return res


def generar(tipo,f):
    return {'panel':panel,'resultados':movimientos,'cuentas':cuentas,'solvencia':solvencia,'beneficios':beneficios,'convenios':convenios,'cajas':cajas,'auditoria':auditoria}[tipo](f)
