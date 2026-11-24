"""F8.2: adaptadores de lectura. No resuelven trámites ni almacenan estados."""
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from academico.models import Estudiante,Curso,InscripcionCurso,SolicitudAcademica
from financiero.lectura import EstadoFinanciero
from financiero.models import (SolicitudBeca,SolicitudConvenio,SolicitudEgreso,SolicitudPadrinazgo,
    SolicitudAnulacion,SolicitudAnulacionOperacion,AnulacionDonacion)
from reportes.financiero_consultas import panel as panel_financiero,beneficios,solvencia,cajas
from reportes.financiero_consultas import valor,motivo_resolucion
from urllib.parse import urlencode

TIPOS={
 'CANCELACION_SESION':'Cancelación de sesión','CORRECCION_CALIFICACION':'Corrección de calificación',
 'BECA':'Beca','CONVENIO':'Convenio de pago','EGRESO':'Egreso','PADRINAZGO':'Padrinazgo',
 'ANULACION_PAGO':'Anulación de pago','ANULACION_OPERACION':'Anulación de ingreso/egreso',
 'ANULACION_DONACION':'Anulación de donación',
}
FUENTES=[
 ('BECA',SolicitudBeca,'fecha_solicitud','becas_detalle','solicitud_id',['matricula__estudiante']),
 ('CONVENIO',SolicitudConvenio,'fecha_solicitud','convenios_solicitud','solicitud_id',['estudiante']),
 ('EGRESO',SolicitudEgreso,'fecha','operaciones_egreso','solicitud_id',['categoria','desembolso']),
 ('PADRINAZGO',SolicitudPadrinazgo,'fecha','aportes_solicitud','solicitud_id',['matricula__estudiante','padrinazgo']),
 ('ANULACION_PAGO',SolicitudAnulacion,'fecha_solicitud','anulaciones_detalle','solicitud_id',['pago__estudiante']),
 ('ANULACION_OPERACION',SolicitudAnulacionOperacion,'fecha','operaciones_anulacion','solicitud_id',
     ['ingreso__ingreso','desembolso__egreso','desembolso__solicitud']),
 ('ANULACION_DONACION',AnulacionDonacion,'fecha','aportes_anulacion','anulacion_id',
     ['recepcion__ingreso','recepcion__matricula__estudiante']),
]


def autorizar_lectura(usuario,roles):
    if not usuario.is_active or usuario.rol not in roles:raise PermissionDenied('Consulta no autorizada para su cuenta.')


def url_reporte(tipo,**filtros):
    return reverse('finanzas_reporte',args=[tipo])+('?' + urlencode(filtros) if filtros else '')


def cargar_bandeja(usuario,ctx=None):
    """Una fila por solicitud de origen; seguimiento no crea una segunda solicitud."""
    autorizar_lectura(usuario,('DIRECTORA',))
    ctx=ctx or EstadoFinanciero()
    revision=beneficios({'beneficio':'PADRINAZGOS','estado':'VENCIDO'},ctx)
    urls_revision={r['url'] for r in revision['filas']}
    filas=[]
    def base(s,tipo,fecha,url):
        return dict(clave=f'{tipo}:{s.pk}',tipo=tipo,titulo=TIPOS[tipo],fecha=fecha,
            estado=s.estado,persona='',solicitante=s.solicitante.numero_usuario,
            motivo=str(getattr(s,'justificacion','') or getattr(s,'motivo','') or ''),
            decision=motivo_resolucion(s),fecha_decision=getattr(s,'fecha_resolucion',None),
            responsable=s.directora.numero_usuario if s.directora_id else '',
            consecuencia='',atencion=s.estado=='PENDIENTE',etapa='Decisión pendiente' if s.estado=='PENDIENTE' else 'Resuelta',
            url=url,accion='Abrir expediente')
    for tipo,modelo,campo,ruta,param,relaciones in FUENTES:
        for s in modelo.objects.select_related('solicitante','directora',*relaciones).order_by('pk'):
            url=reverse(ruta,kwargs={param:s.pk});r=base(s,tipo,getattr(s,campo),url)
            if tipo=='BECA':
                r['persona']=str(s.matricula.estudiante)
                r['consecuencia']=f'Solicita {s.porcentaje_solicitado} % para '+', '.join(s.conceptos_solicitados)+'. Dirección determina obligaciones y condiciones definitivas.'
            elif tipo=='CONVENIO':
                r['persona']=str(s.estudiante);r['consecuencia']='Plan de cuotas sobre obligaciones existentes; no es un ingreso ni deuda adicional.'
            elif tipo=='EGRESO':
                r['persona']=s.beneficiario;r['consecuencia']=f'{valor(s.monto)} · {s.concepto}. Aprobar no desembolsa.'
                if s.estado=='APROBADA' and not hasattr(s,'desembolso'):
                    r.update(atencion=True,etapa='Seguimiento de desembolso',accion='Consultar autorización')
            elif tipo=='PADRINAZGO':
                r['persona']=str(s.matricula.estudiante);r['consecuencia']='Compromiso de apoyo; no registra dinero recibido.'
                if url in urls_revision:
                    r.update(atencion=True,etapa='Aporte vencido: revisar cobertura',consecuencia='El estudiante conserva la protección hasta resolución de Dirección.',
                        url=reverse('aportes_revision',args=[s.pk]),accion='Revisar cobertura')
            elif tipo=='ANULACION_PAGO':
                r['persona']=str(s.pago.estudiante);r['consecuencia']=f'{s.pago.numero_recibo} · {valor(s.pago.monto_total)}. Anular no devuelve dinero.'
            elif tipo=='ANULACION_OPERACION':
                r['persona']=s.ingreso.numero if s.ingreso_id else s.desembolso.egreso.numero_egreso
                r['consecuencia']='Anulación administrativa: conserva historial; no devuelve ni recupera dinero físico.'
            else:
                r['persona']=str(s.recepcion.matricula.estudiante) if s.recepcion.matricula_id else 'Aporte institucional'
                r['consecuencia']=f'{s.recepcion.numero} · {valor(s.recepcion.ingreso.monto)}. Revisar aplicaciones y cobertura en su expediente.'
            filas.append(r)
    qs=SolicitudAcademica.objects.select_related('solicitante','directora','curso__materia','curso__ciclo',
        'sesion','inscripcion__matricula__estudiante').order_by('pk')
    for s in qs:
        r=base(s,s.tipo,s.fecha_solicitud,reverse('solicitud_academica',args=[s.pk]))
        r.update(persona=str(s.inscripcion.matricula.estudiante) if s.inscripcion_id else s.solicitante.numero_usuario,
            motivo=s.motivo,decision=s.motivo_decision,fecha_decision=s.fecha_decision)
        if s.tipo=='CORRECCION_CALIFICACION':
            r['consecuencia']=f"{s.curso} · Nota propuesta {s.propuestos.get('nota_final','No consta')} · Resultado propuesto {s.propuestos.get('estado','No consta')}. No reabre el curso."
        else:r['consecuencia']=f'{s.curso} · Clase {s.sesion.numero_clase}. Solo se cancela si conserva las condiciones autorizadas.'
        filas.append(r)
    filas.sort(key=lambda r:(r['fecha'],r['clave']),reverse=True)
    return filas


def indicadores_direccion(usuario):
    autorizar_lectura(usuario,('DIRECTORA',))
    ctx=EstadoFinanciero();fin=solvencia({},ctx);bandeja=cargar_bandeja(usuario,ctx)
    estados=dict(InscripcionCurso.objects.values('estado').annotate(n=Count('pk')).values_list('estado','n'))
    etiquetas={'CURSANDO':'Cursando','APROBADA':'Aprobadas','REPROBADA_ACADEMICAMENTE':'Reprobadas por nota',
        'REPROBADA_POR_INASISTENCIA':'Reprobadas por inasistencia'}
    cursos=list(Curso.objects.filter(estado='ACTIVO').select_related('materia','ciclo','maestro').order_by('materia__nombre','pk'))
    pendientes=[r for r in bandeja if r['atencion']]
    decisiones=sum(r['estado']=='PENDIENTE' for r in bandeja)
    insolventes=dict(fin['totales'])['Insolvente'];total=dict(fin['totales'])['Estudiantes distintos de la selección']
    return dict(rol='DIRECTORA',generado=timezone.now(),activos=Estudiante.objects.filter(estado='ACTIVO').count(),
        cursos=cursos,estados=[(etiquetas.get(k,k),n) for k,n in sorted(estados.items())],
        inscripciones=sum(estados.values()),solventes=total-insolventes,insolventes=insolventes,
        expedientes=total,decisiones=decisiones,seguimientos=len(pendientes)-decisiones,
        pendientes=len(pendientes),vista_previa=pendientes[:3],
        padrinazgos_vencidos=sum(r['tipo']=='PADRINAZGO' and r['estado']=='APROBADA' and r['atencion'] for r in bandeja))


def indicadores_administracion(usuario,filtros):
    autorizar_lectura(usuario,('ADMINISTRADOR',))
    financiero=panel_financiero(filtros);totales=dict(financiero['totales']);actuales={r['titulo']:r for r in financiero['tarjetas_actuales']}
    caja=cajas({})
    return dict(rol='ADMINISTRADOR',generado=timezone.now(),desde=filtros.get('desde'),hasta=filtros.get('hasta'),
        periodo=[dict(titulo='Ingresos efectivos',valor=valor(totales['Ingresos efectivos vigentes verificados']),url=url_reporte('resultados',desde=str(filtros.get('desde') or ''),hasta=str(filtros.get('hasta') or ''))),
            dict(titulo='Egresos desembolsados',valor=valor(totales['Egresos efectivos vigentes']),url=url_reporte('resultados',origen='EGRESO',desde=str(filtros.get('desde') or ''),hasta=str(filtros.get('hasta') or ''))),
            dict(titulo='Resultado de efectivo',valor=valor(totales['Resultado del período seleccionado']),url=url_reporte('resultados',desde=str(filtros.get('desde') or ''),hasta=str(filtros.get('hasta') or '')))],
        actuales=[actuales[k] for k in ('Cuentas pendientes de cobro','Saldo a cargo de estudiantes, incluido convenio','Cobertura de padrinazgo pendiente efectiva')],
        cajas_abiertas=sum(r['celdas'][2]=='ABIERTA' for r in caja['filas']),
        cajas_cerradas=sum(r['celdas'][2]=='CERRADA' for r in caja['filas']),
        retenido=valor(dict(caja['totales'])['Retenido conocido, no libremente disponible']),
        cierres_con_diferencia=sum(r['celdas'][10] is not None and r['celdas'][10]!=0 for r in caja['filas']),
        avisos=list(dict.fromkeys(financiero['avisos']+caja['avisos'])),
        solicitudes=actuales['Solicitudes pendientes de autorización'],
        sin_desembolsar=actuales['Importe autorizado aún sin desembolsar'],
        acciones=[('Registrar ingreso','operaciones_ingreso_nuevo'),('Solicitar egreso','operaciones_egreso_nuevo'),('Caja y cierres','caja_listado')])
