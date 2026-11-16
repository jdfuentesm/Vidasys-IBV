import csv
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .catalogo import CATALOGO
from .consultas import generar
from .forms import FiltrosReporteForm


def acceso_reportes(view):
    @never_cache
    @login_required
    @wraps(view)
    def protegida(request,*args,**kwargs):
        if not request.user.is_active or request.user.rol not in ('ADMINISTRADOR','DIRECTORA','SECRETARIA','MAESTRO'):
            return HttpResponseForbidden('Su cuenta no tiene acceso a reportes institucionales.')
        return view(request,*args,**kwargs)
    return protegida


@acceso_reportes
@require_safe
def panel(request):
    disponibles=[{'tipo':tipo,'titulo':datos[0],'fecha':datos[2]} for tipo,datos in CATALOGO.items() if request.user.rol in datos[1]]
    return render(request,'reportes/panel.html',{'reportes':disponibles})


def celda_csv(valor):
    texto=str(valor)
    # Neutralizar fórmulas de hoja de cálculo sin modificar los registros originales.
    if texto.lstrip().startswith(('=','+','-','@')) or texto.startswith(('\t','\r','\n')):
        return "'"+texto
    return texto


@acceso_reportes
@require_safe
def reporte(request,tipo):
    if tipo not in CATALOGO:raise Http404('Reporte inexistente')
    titulo,roles,fecha=CATALOGO[tipo]
    if request.user.rol not in roles:
        return HttpResponseForbidden('Su rol no está autorizado para generar o consultar este reporte.')
    formato=request.GET.get('formato','html')
    if formato not in ('html','csv','imprimir'):
        return HttpResponseBadRequest('Formato no disponible. Use CSV o Imprimir / Guardar PDF.')
    form=FiltrosReporteForm(request.GET,usuario=request.user)
    contexto={'form':form,'titulo':titulo,'tipo':tipo,'fecha_filtro':fecha,'imprimir':formato=='imprimir'}
    if not form.is_valid():
        return render(request,'reportes/reporte.html',contexto,status=400)
    try:
        datos=generar(tipo,request.user,form.cleaned_data)
    except DatabaseError:
        contexto['error_reporte']='No se pudo consultar el reporte. Contacte a Administración; no se muestran cifras incompletas.'
        return render(request,'reportes/reporte.html',contexto,status=503)
    alcance=[(form.fields[nombre].label or nombre.capitalize(),str(valor)) for nombre,valor in form.cleaned_data.items() if valor is not None]
    if formato=='csv':
        respuesta=HttpResponse(content_type='text/csv; charset=utf-8')
        respuesta['Content-Disposition']=f'attachment; filename="reporte-{tipo}.csv"'
        respuesta.write('\ufeff')
        writer=csv.writer(respuesta)
        writer.writerow([titulo]);writer.writerow(['Fecha del filtro',fecha])
        for etiqueta,valor in alcance:writer.writerow([celda_csv(etiqueta),celda_csv(valor)])
        writer.writerow([datos['nota']]);writer.writerow([])
        writer.writerow(datos['columnas'])
        for fila in datos['filas']:writer.writerow([celda_csv(valor) for valor in fila])
        writer.writerow([])
        for etiqueta,valor in datos['totales']:writer.writerow([celda_csv(etiqueta),celda_csv(valor)])
        return respuesta
    contexto.update(datos)
    contexto['alcance']=alcance
    contexto['cantidad']=len(datos['filas'])
    celdas=[[{'etiqueta':etiqueta,'valor':valor} for etiqueta,valor in zip(datos['columnas'],fila)] for fila in datos['filas']]
    contexto['pagina']=Paginator(celdas,50).get_page(request.GET.get('page'))
    contexto['filas_visibles']=celdas if formato=='imprimir' else contexto['pagina']
    parametros=request.GET.copy();parametros.pop('formato',None);parametros.pop('page',None)
    contexto['parametros']=parametros.urlencode()
    return render(request,'reportes/reporte.html',contexto)
