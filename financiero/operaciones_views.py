"""Interfaces F5, documentos privados y reportes: sin escrituras en GET."""
import hashlib
from collections import defaultdict
from decimal import Decimal
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import HttpResponse,HttpResponseForbidden,HttpResponseNotFound
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.http import require_http_methods
from .caja import LECTORES,OPERADORES
from .caja_views import acceso,_csv
from .becas_views import error
from . import operaciones
from .operaciones_forms import IngresoForm,EgresoForm,FechaForm,ResolucionForm,AnularForm,CategoriaForm,FiltrosForm
from .models import (RegistroIngreso,SolicitudEgreso,DesembolsoEgreso,ComprobantePrivado,
    SolicitudAnulacionOperacion,CategoriaIngreso,CategoriaEgreso)


def ingresos_visibles(usuario):
    qs=RegistroIngreso.objects.select_related('ingreso__categoria_ingreso','ingreso__usuario_registra','comprobante').defer('comprobante__contenido')
    return qs.filter(ingreso__usuario_registra=usuario) if usuario.rol=='SECRETARIA' else qs


def egresos_visibles(usuario):
    qs=SolicitudEgreso.objects.select_related('categoria','solicitante','directora','comprobante','desembolso__egreso','desembolso__comprobante').defer('comprobante__contenido','desembolso__comprobante__contenido')
    return qs.filter(solicitante=usuario) if usuario.rol=='SECRETARIA' else qs


@acceso(LECTORES)
@require_http_methods(['GET'])
def panel(request):
    return render(request,'financiero/operaciones/panel.html',{'ingresos':Paginator(ingresos_visibles(request.user).order_by('-ingreso__fecha_creacion'),20).get_page(request.GET.get('ing_page')),
        'egresos':Paginator(egresos_visibles(request.user),20).get_page(request.GET.get('egr_page')),
        'anulaciones':Paginator(SolicitudAnulacionOperacion.objects.filter(solicitante=request.user) if request.user.rol=='SECRETARIA' else SolicitudAnulacionOperacion.objects.select_related('solicitante'),20).get_page(request.GET.get('anul_page'))})


@acceso(OPERADORES)
@require_http_methods(['GET','POST'])
def ingreso_nuevo(request):
    form=IngresoForm(request.POST if request.method=='POST' else None,request.FILES if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data.copy();d['categoria_id']=d.pop('categoria').pk
        try:
            r=operaciones.registrar_ingreso(usuario=request.user,**d)
            messages.success(request,'Ingreso registrado con un único movimiento de caja.')
            return redirect('operaciones_ingreso',registro_id=r.pk)
        except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/operaciones/form.html',{'form':form,'titulo':'Registrar ingreso administrativo','accion':'Registrar ingreso'})


@acceso(LECTORES)
@require_http_methods(['GET'])
def ingreso_detalle(request,registro_id):
    r=get_object_or_404(ingresos_visibles(request.user),pk=registro_id)
    return render(request,'financiero/operaciones/ingreso.html',{'registro':r,'anulaciones':r.anulaciones.select_related('directora')})


@acceso(OPERADORES)
@require_http_methods(['GET','POST'])
def egreso_nuevo(request):
    form=EgresoForm(request.POST if request.method=='POST' else None,request.FILES if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data.copy();d['categoria_id']=d.pop('categoria').pk
        try:
            s=operaciones.solicitar_egreso(usuario=request.user,**d)
            messages.success(request,'Solicitud enviada. Todavía no hay salida de dinero.')
            return redirect('operaciones_egreso',solicitud_id=s.pk)
        except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/operaciones/form.html',{'form':form,'titulo':'Solicitar egreso','accion':'Enviar a Dirección'})


@acceso(LECTORES)
@require_http_methods(['GET','POST'])
def egreso_detalle(request,solicitud_id):
    s=get_object_or_404(egresos_visibles(request.user),pk=solicitud_id)
    form=ResolucionForm(request.POST if request.method=='POST' else None)
    if request.method=='POST':
        if request.user.rol!='DIRECTORA':return HttpResponseForbidden('Solo Dirección autoriza o rechaza.')
        if form.is_valid():
            try:
                operaciones.decidir_egreso(usuario=request.user,solicitud_id=s.pk,decision=form.cleaned_data['decision'],resolucion=form.cleaned_data['resolucion'])
                messages.success(request,'Resolución registrada. Aprobar no desembolsa dinero.')
                return redirect('operaciones_egreso',solicitud_id=s.pk)
            except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/operaciones/egreso.html',{'solicitud':s,'form':form})


@acceso(OPERADORES)
@require_http_methods(['GET','POST'])
def desembolso(request,solicitud_id):
    s=get_object_or_404(egresos_visibles(request.user),pk=solicitud_id)
    form=FechaForm(request.POST if request.method=='POST' else None,request.FILES if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            operaciones.desembolsar(usuario=request.user,solicitud_id=s.pk,**form.cleaned_data)
            messages.success(request,'Desembolso registrado. El importe autorizado no fue alterado.')
            return redirect('operaciones_egreso',solicitud_id=s.pk)
        except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/operaciones/form.html',{'form':form,'titulo':f'Desembolsar egreso #{s.pk} · USD {s.monto:.2f}',
        'accion':'Confirmar pago efectivo','solicitud':s})


@acceso(LECTORES)
@require_http_methods(['GET'])
def documento(request,documento_id):
    d=get_object_or_404(ComprobantePrivado.objects.defer('contenido'),pk=documento_id)
    if request.user.rol=='SECRETARIA':
        permitido=(ingresos_visibles(request.user).filter(comprobante=d).exists() or
            egresos_visibles(request.user).filter(comprobante=d).exists() or
            egresos_visibles(request.user).filter(desembolso__comprobante=d).exists())
        if not permitido:
            from .models import RecepcionDonacion
            permitido=RecepcionDonacion.objects.filter(comprobante=d).exists()
        if not permitido:return HttpResponseNotFound('Documento no disponible.')
    contenido=bytes(d.contenido)
    if len(contenido)!=d.tamano or hashlib.sha256(contenido).hexdigest()!=d.sha256:
        return HttpResponse('La integridad del comprobante no pudo verificarse.',status=503)
    response=HttpResponse(contenido,content_type=d.mime)
    response['Content-Disposition']=f'attachment; filename="{d.nombre}"'
    response['X-Content-Type-Options']='nosniff'
    response['Content-Security-Policy']="sandbox; default-src 'none'"
    response['Cache-Control']='private, no-store'
    return response


@acceso(OPERADORES)
@require_http_methods(['GET','POST'])
def anular(request,tipo,registro_id):
    if tipo=='INGRESO':r=get_object_or_404(ingresos_visibles(request.user),pk=registro_id);pk=r.pk
    elif tipo=='EGRESO':
        r=get_object_or_404(DesembolsoEgreso.objects.filter(solicitud__in=egresos_visibles(request.user)),pk=registro_id);pk=r.pk
    else:return HttpResponseNotFound()
    form=AnularForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            s=operaciones.solicitar_anulacion(usuario=request.user,tipo=tipo,registro_id=pk,**form.cleaned_data)
            return redirect('operaciones_anulacion',solicitud_id=s.pk)
        except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/operaciones/form.html',{'form':form,'titulo':'Solicitar anulación administrativa','accion':'Solicitar a Dirección'})


@acceso(LECTORES)
@require_http_methods(['GET','POST'])
def anulacion(request,solicitud_id):
    qs=SolicitudAnulacionOperacion.objects.select_related('solicitante','directora','ingreso__ingreso','desembolso__egreso')
    if request.user.rol=='SECRETARIA':qs=qs.filter(solicitante=request.user)
    s=get_object_or_404(qs,pk=solicitud_id)
    form=ResolucionForm(request.POST if request.method=='POST' else None);comparacion=False
    if request.method=='POST':
        if request.user.rol!='DIRECTORA':return HttpResponseForbidden('Solo Dirección resuelve anulaciones.')
        if form.is_valid():
            d=form.cleaned_data
            try:
                resultado=operaciones.decidir_anulacion(usuario=request.user,solicitud_id=s.pk,decision=d['decision'],
                    resolucion=d['resolucion'],revision=d['revision'],confirmar=request.POST.get('accion')=='confirmar')
                if isinstance(resultado,str):
                    form.data=form.data.copy();form.data['revision']=resultado;comparacion=True
                else:
                    messages.success(request,'Resolución registrada. No hubo devolución ni recuperación de fondos.')
                    return redirect('operaciones_anulacion',solicitud_id=s.pk)
            except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/operaciones/anulacion.html',{'solicitud':s,'form':form,'comparacion':comparacion})


@acceso(LECTORES)
@require_http_methods(['GET','POST'])
def categorias(request):
    form=CategoriaForm(request.POST if request.method=='POST' else None)
    if request.method=='POST':
        if request.user.rol!='ADMINISTRADOR':return HttpResponseForbidden('Solo Administración configura categorías.')
        if form.is_valid():
            try:
                operaciones.configurar_categoria(usuario=request.user,**form.cleaned_data)
                messages.success(request,'Categoría guardada. Los movimientos históricos se conservan.')
                return redirect('operaciones_categorias')
            except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/operaciones/categorias.html',{'form':form,
        'ingresos':CategoriaIngreso.objects.order_by('nombre'),'egresos':CategoriaEgreso.objects.order_by('nombre')})


def filas_reporte(usuario,filtros):
    filas=[]
    for r in ingresos_visibles(usuario):
        i=r.ingreso
        filas.append({'tipo':'INGRESO','id':r.pk,'numero':r.numero,'fecha':i.fecha_ingreso,'categoria':i.categoria_ingreso.nombre,
            'concepto':r.concepto,'operador':i.usuario_registra_id,'usuario':i.usuario_registra.numero_usuario,'estado':i.estado,
            'metodo':i.metodo_pago,'monto':i.monto,'realizado':i.estado=='REGISTRADO'})
    for s in egresos_visibles(usuario):
        d=getattr(s,'desembolso',None);e=d.egreso if d else None
        filas.append({'tipo':'EGRESO','id':s.pk,'numero':e.numero_egreso if e else f'SOL-{s.pk}',
            'fecha':e.fecha_egreso if e else s.fecha,'categoria':s.categoria.nombre,'concepto':s.concepto,
            'operador':e.usuario_registra_id if e else s.solicitante_id,'usuario':e.usuario_registra.numero_usuario if e else s.solicitante.numero_usuario,
            'estado':('ANULADO' if e.estado=='ANULADO' else 'DESEMBOLSADO') if e else s.estado,
            'metodo':e.metodo_pago if e else '', 'monto':s.monto,'realizado':e is not None and e.estado=='REGISTRADO'})
    resultado=[]
    for f in filas:
        if any(filtros.get(c) and f[c]!=filtros[c] for c in ('tipo','estado','metodo','operador')):continue
        if filtros.get('categoria') and filtros['categoria'].casefold() not in f['categoria'].casefold():continue
        if filtros.get('desde') and timezone.localdate(f['fecha'])<filtros['desde']:continue
        if filtros.get('hasta') and timezone.localdate(f['fecha'])>filtros['hasta']:continue
        resultado.append(f)
    return sorted(resultado,key=lambda f:(f['fecha'],f['tipo'],f['id']),reverse=True)


@acceso(('DIRECTORA','ADMINISTRADOR'))
@require_http_methods(['GET'])
def reporte(request):
    form=FiltrosForm(request.GET)
    filas=filas_reporte(request.user,form.cleaned_data) if form.is_valid() else []
    totales=defaultdict(lambda:Decimal('0.00'));categorias=defaultdict(lambda:Decimal('0.00'))
    for f in filas:
        if f['realizado']:
            totales[f['tipo']]+=f['monto'];categorias[(f['tipo'],f['categoria'],f['metodo'])]+=f['monto']
    if request.GET.get('formato')=='csv':
        return _csv('ingresos-egresos',['Tipo','Comprobante','Fecha efectiva o de solicitud','Categoría','Concepto','Operador','Estado','Método','Importe','Realizado vigente'],
            [[f[c] for c in ('tipo','numero','fecha','categoria','concepto','usuario','estado','metodo','monto','realizado')] for f in filas])
    return render(request,'financiero/operaciones/reporte.html',{'form':form,'pagina':Paginator(filas,30).get_page(request.GET.get('page')),
        'filtros':request.GET.urlencode(),'total_ingresos':totales['INGRESO'],'total_egresos':totales['EGRESO'],
        'resumen_categorias':[(tipo,cat,metodo,total) for (tipo,cat,metodo),total in sorted(categorias.items())]})
