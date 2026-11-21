from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from . import becas
from .becas_forms import SolicitudBecaForm, ResolucionBecaForm
from .models import SolicitudBeca


def acceso(roles):
    def decorar(view):
        @login_required
        @wraps(view)
        def protegida(request,*args,**kwargs):
            if not request.user.is_active or request.user.rol not in roles:
                return HttpResponseForbidden('Su cuenta no puede realizar esta operación de becas.')
            return view(request,*args,**kwargs)
        return protegida
    return decorar


def error(form,excepcion):
    form.add_error(None,' '.join(excepcion.messages) if isinstance(excepcion,ValidationError) else 'No se pudo completar la operación; no se aplicaron cambios parciales. Recargue y consulte el historial.')


@acceso(('SECRETARIA','DIRECTORA','ADMINISTRADOR'))
@require_http_methods(['GET'])
def listado(request):
    from django.core.paginator import Paginator
    qs=SolicitudBeca.objects.select_related('matricula__estudiante','matricula__ciclo','solicitante','directora')
    estado=request.GET.get('estado','')
    if estado in ('PENDIENTE','APROBADA','RECHAZADA'):qs=qs.filter(estado=estado)
    return render(request,'financiero/becas/listado.html',{'pagina':Paginator(qs,20).get_page(request.GET.get('page')),'estado':estado})


@acceso(('SECRETARIA',))
@require_http_methods(['GET','POST'])
def nueva(request):
    form=SolicitudBecaForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data
        try:
            s=becas.solicitar(usuario=request.user,matricula_id=d['matricula'].pk,porcentaje=d['porcentaje'],
                conceptos=d['conceptos'],alcance=d['alcance'],justificacion=d['justificacion'],clave=d['clave'])
            messages.success(request,'Solicitud registrada. Las obligaciones no cambian hasta la aprobación de Dirección.')
            return redirect('becas_detalle',solicitud_id=s.pk)
        except PermissionDenied:
            return HttpResponseForbidden('Su cuenta ya no puede solicitar becas.')
        except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/becas/nueva.html',{'form':form})


@acceso(('SECRETARIA','DIRECTORA','ADMINISTRADOR'))
@require_http_methods(['GET','POST'])
def detalle(request,solicitud_id):
    s=get_object_or_404(SolicitudBeca.objects.select_related('matricula__estudiante','matricula__ciclo','directora','beca','solicitante'),pk=solicitud_id)
    if request.method=='POST' and request.user.rol!='DIRECTORA':
        return HttpResponseForbidden('Solo Dirección puede resolver solicitudes.')
    form=ResolucionBecaForm(request.POST if request.method=='POST' else None,solicitud=s,
        initial={'porcentaje':str(int(s.porcentaje_solicitado)),'conceptos':s.conceptos_solicitados,'alcance':s.alcance_solicitado})
    propuesta=None
    if request.method=='POST' and form.is_valid():
        try:
            datos=form.resolucion()
            if form.cleaned_data['decision']=='APROBADA' and request.POST.get('accion')!='resolver':
                propuesta,token=becas.previsualizar(usuario=request.user,solicitud_id=s.pk,**datos)
                form.data=form.data.copy();form.data['revision']=token
            else:
                becas.resolver(usuario=request.user,solicitud_id=s.pk,decision=form.cleaned_data['decision'],
                    revision=form.cleaned_data['revision'],**datos)
                messages.success(request,'Resolución registrada. Consulte el resultado aplicado y el historial.')
                return redirect('becas_detalle',solicitud_id=s.pk)
        except PermissionDenied:
            return HttpResponseForbidden('Solo Dirección activa puede resolver solicitudes.')
        except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/becas/detalle.html',{'solicitud':s,'form':form,'propuesta':propuesta})
