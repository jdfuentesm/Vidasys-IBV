from decimal import Decimal
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Q,Sum
from django.http import HttpResponseForbidden,HttpResponseNotFound
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from academico.models import Matricula
from . import aportes
from .caja import OPERADORES,LECTORES
from .caja_views import acceso,_csv
from .becas_views import error
from .aportes_forms import DonanteForm,SolicitudForm,RecepcionForm,RevisionForm
from .operaciones_forms import ResolucionForm,AnularForm
from .caja_forms import FechasForm
from .models import Donante,RecepcionDonacion,SolicitudPadrinazgo,RevisionPadrinazgo,AnulacionDonacion


def pagina(request,qs):return Paginator(qs,20).get_page(request.GET.get('page'))


@acceso(LECTORES)
@require_http_methods(['GET'])
def panel(request):
    q=request.GET.get('q','').strip()[:100]
    donantes=Donante.objects.filter(Q(nombre_completo__icontains=q)|Q(documento_identidad__icontains=q)).order_by('nombre_completo')
    if request.GET.get('directorio')=='csv':
        if request.user.rol not in ('DIRECTORA','ADMINISTRADOR'):return HttpResponseForbidden('El directorio consolidado corresponde a Dirección y Administración.')
        return _csv('directorio-donantes',['Nombre','Tipo','Estado','Correo','Teléfono'],[[d.nombre_completo,d.tipo,d.estado,d.correo or '',d.telefono or ''] for d in donantes])
    solicitudes=SolicitudPadrinazgo.objects.select_related('matricula__estudiante','padrinazgo','donante')
    vencidos=[s for s in solicitudes.filter(estado='APROBADA',padrinazgo__estado='ACTIVO',padrinazgo__fecha_fin__lt=timezone.localdate()) if any(aportes.pendiente(c)>0 for c in s.coberturas.filter(activa=True))]
    return render(request,'financiero/aportes/panel.html',{'pagina':pagina(request,donantes),'q':q,
        'solicitudes':solicitudes[:30],'vencidos':vencidos,'anulaciones':AnulacionDonacion.objects.select_related('recepcion')[:20]})


@acceso(OPERADORES)
@require_http_methods(['GET','POST'])
def donante_form(request,donante_id=None):
    d=get_object_or_404(Donante,pk=donante_id) if donante_id else None
    form=DonanteForm(request.POST if request.method=='POST' else None,initial={f:getattr(d,f) for f in DonanteForm.base_fields if f!='clave'} if d else None)
    if request.method=='POST' and form.is_valid():
        try:
            d=aportes.guardar_donante(usuario=request.user,donante_id=donante_id,**form.cleaned_data)
            messages.success(request,'Datos guardados. El historial de aportes se conserva.');return redirect('aportes_donante',donante_id=d.pk)
        except (ValidationError,DatabaseError) as e:error(form,e)
    return render(request,'financiero/aportes/form.html',{'form':form,'titulo':'Datos privados del donante','boton':'Guardar datos'})


@acceso(LECTORES)
@require_http_methods(['GET'])
def donante(request,donante_id):
    d=get_object_or_404(Donante,pk=donante_id)
    return render(request,'financiero/aportes/donante.html',{'donante':d,'recepciones':pagina(request,RecepcionDonacion.objects.filter(donante=d).select_related('ingreso').order_by('-ingreso__fecha_ingreso'))})


@acceso(OPERADORES)
@require_http_methods(['GET'])
def buscar_estudiante(request):
    q=request.GET.get('q','').strip()[:100]
    qs=Matricula.objects.filter(Q(estudiante__nombres__icontains=q)|Q(estudiante__apellidos__icontains=q)|Q(numero_matricula__icontains=q)).select_related('estudiante','ciclo').order_by('-fecha_matricula','pk')
    return render(request,'financiero/aportes/buscar.html',{'pagina':pagina(request,qs),'q':q})


@acceso(OPERADORES)
@require_http_methods(['GET','POST'])
def solicitar(request,matricula_id):
    m=get_object_or_404(Matricula.objects.select_related('estudiante','ciclo'),pk=matricula_id)
    form=SolicitudForm(request.POST if request.method=='POST' else None,obligaciones=m.obligaciones.order_by('pk'))
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data
        try:
            s=aportes.solicitar(usuario=request.user,clave=d['clave'],donante_id=d['donante'].pk,matricula_id=m.pk,
                inicio=d['inicio'],limite=d['limite'],modalidad=d['modalidad'],porcentaje=d['porcentaje'],asignaciones=form.asignaciones(),observaciones=d['observaciones'])
            messages.success(request,'Solicitud enviada. Aún no hay cobertura autorizada ni ingreso de dinero.');return redirect('aportes_solicitud',solicitud_id=s.pk)
        except (ValidationError,DatabaseError) as e:error(form,e)
    return render(request,'financiero/aportes/form.html',{'form':form,'titulo':'Preparar padrinazgo','matricula':m,'boton':'Enviar a Dirección','dinamico':True})


@acceso(LECTORES)
@require_http_methods(['GET','POST'])
def solicitud(request,solicitud_id):
    s=get_object_or_404(SolicitudPadrinazgo.objects.select_related('matricula__estudiante','padrinazgo__donante','donante','directora'),pk=solicitud_id)
    form=ResolucionForm(request.POST if request.method=='POST' else None);comparacion=False
    if request.method=='POST':
        if request.user.rol!='DIRECTORA':return HttpResponseForbidden('Solo Dirección autoriza.')
        if form.is_valid():
            d=form.cleaned_data
            try:
                r=aportes.resolver(usuario=request.user,solicitud_id=s.pk,decision=d['decision'],motivo=d['resolucion'],revision=d['revision'],confirmar=request.POST.get('accion')=='confirmar')
                if isinstance(r,str):form.data=form.data.copy();form.data['revision']=r;comparacion=True
                else:messages.success(request,'Resolución guardada; el compromiso no se registra como ingreso.');return redirect('aportes_solicitud',solicitud_id=s.pk)
            except (ValidationError,DatabaseError) as e:error(form,e)
    return render(request,'financiero/aportes/solicitud.html',{'solicitud':s,'form':form,'comparacion':comparacion,
        'coberturas':[{'obligacion':c.obligacion,'original':c.monto,'pendiente':aportes.pendiente(c),'activa':c.activa} for c in s.coberturas.select_related('obligacion')],
        'lineas_propuestas':[{'descripcion':next((o.descripcion for o in s.matricula.obligaciones.all() if o.pk==f['id']),'Obligación no disponible'),'monto':f['monto']} for f in s.propuesta['lineas']],
        'historial':s.revisiones.select_related('directora')})


@acceso(OPERADORES)
@require_http_methods(['GET','POST'])
def recibir(request,matricula_id=None):
    m=get_object_or_404(Matricula.objects.select_related('estudiante','ciclo'),pk=matricula_id) if matricula_id else None
    form=RecepcionForm(request.POST if request.method=='POST' else None,request.FILES if request.method=='POST' else None,matricula=m)
    if request.method=='POST' and form.is_valid():
        d={k:v for k,v in form.cleaned_data.items() if not k.startswith('aporte_')};d['donante_id']=d.pop('donante').pk;s=d.pop('solicitud');d['solicitud_id']=s.pk if s else None
        try:
            r=aportes.recibir(usuario=request.user,matricula_id=m.pk if m else None,asignaciones=form.asignaciones(),**d)
            messages.success(request,'Aporte recibido y aplicado una sola vez; comprobante y caja registrados.');return redirect('aportes_recibo',recepcion_id=r.pk)
        except (ValidationError,DatabaseError) as e:error(form,e)
    return render(request,'financiero/aportes/form.html',{'form':form,'titulo':'Registrar dinero recibido','matricula':m,'boton':'Confirmar recepción efectiva','dinamico':bool(m)})


@acceso(LECTORES)
@require_http_methods(['GET'])
def recibo(request,recepcion_id):
    r=get_object_or_404(RecepcionDonacion.objects.select_related('ingreso__usuario_registra','donante','comprobante','matricula__estudiante').defer('comprobante__contenido'),pk=recepcion_id)
    return render(request,'financiero/aportes/recibo.html',{'recepcion':r,'lineas':r.lineas.select_related('donacion__obligacion'),'anulaciones':r.anulaciones.select_related('directora')})


@acceso(('DIRECTORA',))
@require_http_methods(['GET','POST'])
def revision(request,solicitud_id):
    s=get_object_or_404(SolicitudPadrinazgo.objects.select_related('padrinazgo','matricula__estudiante'),pk=solicitud_id)
    form=RevisionForm(request.POST if request.method=='POST' else None);comparacion=False
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data.copy();donante=d.pop('donante');d['donante_id']=donante.pk if donante else None;token=d.pop('revision')
        try:
            r=aportes.revisar(usuario=request.user,solicitud_id=s.pk,revision=token,confirmar=request.POST.get('paso')=='confirmar',**d)
            if isinstance(r,str):form.data=form.data.copy();form.data['revision']=r;comparacion=True
            else:messages.success(request,'Resolución guardada con historial y notificación cuando corresponde.');return redirect('aportes_solicitud',solicitud_id=s.pk)
        except (ValidationError,DatabaseError) as e:error(form,e)
    return render(request,'financiero/aportes/form.html',{'form':form,'titulo':'Resolver compromiso de padrinazgo','boton':'Comparar resolución','comparacion':comparacion})


@acceso(OPERADORES)
@require_http_methods(['GET','POST'])
def pedir_anulacion(request,recepcion_id):
    r=get_object_or_404(RecepcionDonacion,pk=recepcion_id,ingreso__usuario_registra=request.user)
    form=AnularForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            a=aportes.pedir_anulacion(usuario=request.user,recepcion_id=r.pk,**form.cleaned_data);return redirect('aportes_anulacion',anulacion_id=a.pk)
        except (ValidationError,DatabaseError) as e:error(form,e)
    return render(request,'financiero/aportes/form.html',{'form':form,'titulo':'Solicitar anulación del aporte','boton':'Enviar a Dirección'})


@acceso(LECTORES)
@require_http_methods(['GET','POST'])
def anulacion(request,anulacion_id):
    a=get_object_or_404(AnulacionDonacion.objects.select_related('recepcion__ingreso','solicitante','directora'),pk=anulacion_id)
    form=ResolucionForm(request.POST if request.method=='POST' else None);comparacion=False
    if request.method=='POST':
        if request.user.rol!='DIRECTORA':return HttpResponseForbidden('Solo Dirección resuelve.')
        if form.is_valid():
            d=form.cleaned_data
            try:
                r=aportes.anular(usuario=request.user,anulacion_id=a.pk,decision=d['decision'],resolucion=d['resolucion'],revision=d['revision'],confirmar=request.POST.get('accion')=='confirmar')
                if isinstance(r,str):form.data=form.data.copy();form.data['revision']=r;comparacion=True
                else:return redirect('aportes_anulacion',anulacion_id=a.pk)
            except (ValidationError,DatabaseError) as e:error(form,e)
    return render(request,'financiero/aportes/anulacion.html',{'anulacion':a,'form':form,'comparacion':comparacion})


@acceso(('DIRECTORA','ADMINISTRADOR'))
@require_http_methods(['GET'])
def reporte(request):
    form=FechasForm(request.GET);qs=RecepcionDonacion.objects.select_related('ingreso__usuario_registra','donante','matricula__estudiante').order_by('-ingreso__fecha_ingreso')
    if not form.is_valid():qs=qs.none()
    else:
        for parametro,op in [('desde','gte'),('hasta','lte')]:
            if form.cleaned_data.get(parametro):qs=qs.filter(**{f'ingreso__fecha_ingreso__date__{op}':form.cleaned_data[parametro]})
    if request.GET.get('tipo') in ('GENERAL','DIRIGIDA','PADRINAZGO'):qs=qs.filter(datos__modalidad=request.GET['tipo'])
    if request.GET.get('estado') in ('REGISTRADO','ANULADO'):qs=qs.filter(ingreso__estado=request.GET['estado'])
    q=request.GET.get('q','').strip()[:100]
    if q:qs=qs.filter(Q(donante__nombre_completo__icontains=q)|Q(matricula__estudiante__nombres__icontains=q)|Q(matricula__estudiante__apellidos__icontains=q))
    if request.GET.get('metodo') in ('EFECTIVO','TRANSFERENCIA'):qs=qs.filter(ingreso__metodo_pago=request.GET['metodo'])
    comprometidos=SolicitudPadrinazgo.objects.filter(estado='APROBADA').select_related('padrinazgo','matricula__estudiante')
    if form.is_valid():
        for parametro,op in [('desde','gte'),('hasta','lte')]:
            if form.cleaned_data.get(parametro):comprometidos=comprometidos.filter(**{f'fecha__date__{op}':form.cleaned_data[parametro]})
    else:comprometidos=comprometidos.none()
    if q:comprometidos=comprometidos.filter(Q(padrinazgo__donante__nombre_completo__icontains=q)|Q(matricula__estudiante__nombres__icontains=q)|Q(matricula__estudiante__apellidos__icontains=q))
    filas=[{'solicitud':s,'total':sum((c.monto for c in s.coberturas.all()),Decimal('0')),'pendiente':sum((aportes.pendiente(c) for c in s.coberturas.filter(activa=True)),Decimal('0'))} for s in comprometidos]
    for f in filas:
        s=f['solicitud'];seleccion={l['id'] for l in s.propuesta['lineas']}
        original=sum((Decimal(l['saldo']) for l in s.anteriores['obligaciones'] if l['id'] in seleccion),Decimal('0'))
        f['cobertura']='TOTAL' if f['total']==original else 'PARCIAL'
        f['estado']='CANCELADO' if s.padrinazgo.estado!='ACTIVO' else 'CUMPLIDO' if f['pendiente']==0 else 'VENCIDO' if s.padrinazgo.fecha_fin<timezone.localdate() else 'ACTIVO'
    if request.GET.get('compromiso') in ('ACTIVO','VENCIDO','CANCELADO','CUMPLIDO'):filas=[f for f in filas if f['estado']==request.GET['compromiso']]
    if request.GET.get('cobertura') in ('TOTAL','PARCIAL'):filas=[f for f in filas if f['cobertura']==request.GET['cobertura']]
    if request.GET.get('formato')=='csv' or request.GET.get('seccion')=='COMPROMISOS':
        if request.GET.get('seccion')=='COMPROMISOS':return _csv('compromisos-padrinazgo',['Estudiante','Comprometido histórico','Pendiente comprometido','Fecha límite','Estado','Cobertura'],[[f['solicitud'].matricula.estudiante.codigo_estudiante,f['total'],f['pendiente'],f['solicitud'].padrinazgo.fecha_fin,f['estado'],f['cobertura']] for f in filas])
        return _csv('donaciones-recibidas',['Comprobante','Donante','Estudiante','Tipo','Fecha','Método','Importe','Estado'],[[r.numero,r.donante.nombre_completo,r.matricula.estudiante.codigo_estudiante if r.matricula_id else '',r.datos['modalidad'],r.ingreso.fecha_ingreso,r.ingreso.metodo_pago,r.ingreso.monto,r.ingreso.estado] for r in qs])
    return render(request,'financiero/aportes/reporte.html',{'form':form,'pagina':pagina(request,qs),'compromisos':filas,'recibido':qs.filter(ingreso__estado='REGISTRADO').aggregate(n=Sum('ingreso__monto'))['n'] or 0,'filtros':request.GET.urlencode()})
