"""Centro F7: permisos antes de consultar y exportaciones con el mismo alcance."""
import csv
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from financiero.lectura import lectura_consistente
from .financiero_forms import FiltrosFinancierosForm, REPORTES
from .financiero_consultas import generar, valor
from .views import celda_csv
from .presentacion import cuentas_por_estudiante,menu_agrupado


@never_cache
@login_required
@require_safe
def reporte(request,tipo='panel'):
    if not request.user.is_active or request.user.rol not in ('DIRECTORA','ADMINISTRADOR'):
        return HttpResponseForbidden('Los reportes financieros consolidados están disponibles únicamente para Dirección y Administración.')
    if tipo not in REPORTES:raise Http404('Reporte financiero inexistente')
    formato=request.GET.get('formato','html')
    if formato not in ('html','csv','imprimir'):return HttpResponseBadRequest('Use CSV o Imprimir / Guardar PDF.')
    parametros=request.GET.copy()
    if tipo in ('panel','resultados','auditoria') and not any(k in parametros for k in ('desde','hasta')):
        hoy=timezone.localdate();parametros['desde']=hoy.replace(day=1).isoformat();parametros['hasta']=hoy.isoformat()
    form=FiltrosFinancierosForm(parametros,tipo=tipo)
    contexto={'form':form,'tipo':tipo,'titulo':REPORTES[tipo][0],
        'menu':[{'tipo':k,'titulo':v[0]} for k,v in REPORTES.items()],
        'generado':timezone.now(),'imprimir':formato=='imprimir'}
    contexto['grupos_reportes']=menu_agrupado(contexto['menu'])
    try:
        with lectura_consistente():
            if not form.is_valid():
                return render(request,'reportes/financiero.html',contexto,status=400)
            datos=generar(tipo,form.cleaned_data)
            alcance=[]
            for k,v in form.cleaned_data.items():
                if v is None or v=='':continue
                campo=form.fields[k]
                etiqueta=campo.label or k.capitalize()
                if hasattr(campo,'label_from_instance'):v=campo.label_from_instance(v)
                elif hasattr(campo,'choices'):v=dict(campo.choices).get(v,v)
                else:v=valor(v)
                alcance.append((etiqueta,str(v)))
            # Materializar etiquetas/modelos y consultas de filtros dentro de la misma lectura.
            contexto['form_html']=form.as_div()
    except DatabaseError:
        contexto['error_reporte']='No fue posible consultar todas las fuentes. No se muestran cifras incompletas. Contacte a Administración.'
        return render(request,'reportes/financiero.html',contexto,status=503)
    if formato=='csv':
        respuesta=HttpResponse(content_type='text/csv; charset=utf-8')
        respuesta['Content-Disposition']=f'attachment; filename="vidasys-finanzas-{tipo}.csv"'
        respuesta.write('\ufeff');writer=csv.writer(respuesta)
        def escribir(celdas):writer.writerow([celda_csv(valor(c)) for c in celdas])
        escribir([contexto['titulo']]);escribir(['Generado',contexto['generado']])
        for filtro in alcance:escribir(filtro)
        escribir([datos['nota']])
        for aviso in datos['avisos']:escribir(['Advertencia',aviso])
        for clave,etiqueta in [('tarjetas_periodo','Operaciones del período'),('tarjetas_actuales','Situación actual')]:
            if clave in datos:
                escribir([etiqueta])
                for t in datos[clave]:escribir([t['titulo'],t['valor']])
        escribir(datos['columnas'])
        for fila in datos['filas']:escribir(fila['celdas'])
        escribir([])
        for total in datos['totales']:escribir(total)
        for clave in ('resumen_origen','resumen_egresos'):
            for resumen in datos.get(clave,[]):escribir(resumen)
        return respuesta
    contexto.update(datos);contexto['alcance']=alcance;contexto['cantidad']=len(datos['filas'])
    if tipo=='cuentas' and formato!='imprimir':
        grupos=cuentas_por_estudiante(datos)
        contexto['cantidad_estudiantes']=len(grupos)
        totales_cuentas=dict(datos['totales'])
        contexto['saldo_seleccion']=valor(totales_cuentas['Saldo financiero pendiente'])
        contexto['cargo_seleccion']=valor(totales_cuentas['A cargo del estudiante, incluido convenio y no vencido'])
        contexto['cobertura_seleccion']=valor(totales_cuentas['Protección pendiente efectiva'])
        contexto['pagina_cuentas']=Paginator(grupos,25).get_page(request.GET.get('page'))
    visibles=[{'celdas':[{'etiqueta':c,'valor':valor(v)} for c,v in zip(datos['columnas'],r['celdas'])], 'url':r['url']} for r in datos['filas']]
    contexto['pagina']=Paginator(visibles,25).get_page(request.GET.get('page'))
    contexto['filas_visibles']=visibles if formato=='imprimir' else contexto['pagina']
    contexto['totales']=[(n,valor(v)) for n,v in datos['totales']]
    parametros.pop('page',None);parametros.pop('formato',None);contexto['parametros']=parametros.urlencode()
    return render(request,'reportes/financiero.html',contexto)
