from django.contrib import messages
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.http import require_http_methods
from django import forms
from academico.models import Estudiante
from core.portal import acceso_portal
from .becas_views import acceso,error
from .models import SolicitudConvenio,ConvenioPago
from .convenios_forms import PrepararForm,CondicionesForm,CuotasFormSet,cuotas_limpias
from . import convenios

ROLES=('SECRETARIA','DIRECTORA','ADMINISTRADOR')


def cantidad_iniciales(request,filas):
    try:
        cantidad=int(request.GET.get('cantidad',len(filas)))
    except (ValueError,TypeError):
        cantidad=len(filas)
    if not 1<=cantidad<=100:cantidad=len(filas)
    return filas[:cantidad]+[{} for _ in range(max(0,cantidad-len(filas)))]



@acceso(ROLES)
@require_http_methods(['GET'])
def listado(request):
    from django.core.paginator import Paginator
    estado=request.GET.get('estado','')
    qs=ConvenioPago.objects.select_related('estudiante').order_by('-pk')
    if estado in ('ACTIVO','CUMPLIDO','INCUMPLIDO','CANCELADO'):qs=qs.filter(estado=estado)
    solicitudes=SolicitudConvenio.objects.select_related('estudiante','solicitante').order_by('-pk')
    return render(request,'financiero/convenios/listado.html',{'pagina':Paginator(qs,20).get_page(request.GET.get('page')),
        'solicitudes':Paginator(solicitudes,20).get_page(request.GET.get('sol_page')),'estado':estado})


@acceso(('SECRETARIA',))
@require_http_methods(['GET','POST'])
def nueva(request):
    preparar=PrepararForm(request.GET or None)
    estudiante=None;form=None;cuotas=None
    if preparar.is_valid():
        estudiante=preparar.cleaned_data['estudiante']
        form=CondicionesForm(request.POST if request.method=='POST' else None,estudiante=estudiante)
        cuotas=CuotasFormSet(request.POST if request.method=='POST' else None,prefix='cuotas',initial=[{}]*preparar.cleaned_data['cantidad'])
        if request.method=='POST':
            valida=form.is_valid();validas=cuotas.is_valid()
            if valida and validas:
                try:
                    s=convenios.solicitar(usuario=request.user,estudiante_id=estudiante.pk,
                        obligaciones=[o.pk for o in form.cleaned_data['obligaciones']],cuotas=cuotas_limpias(cuotas),
                        justificacion=form.cleaned_data['motivo'],clave=form.cleaned_data['clave'])
                    messages.success(request,'Solicitud registrada sin modificar deuda ni solvencia.')
                    return redirect('convenios_solicitud',solicitud_id=s.pk)
                except PermissionDenied:return HttpResponseForbidden('Solo Secretaría activa puede solicitar.')
                except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/convenios/formulario.html',{'preparar':preparar,'form':form,'cuotas':cuotas,'estudiante':estudiante,'nueva':True})


class DecisionForm(CondicionesForm):
    decision=forms.ChoiceField(choices=[('APROBADA','Aprobar convenio'),('RECHAZADA','Rechazar solicitud')])


@acceso(ROLES)
@require_http_methods(['GET','POST'])
def solicitud(request,solicitud_id):
    s=get_object_or_404(SolicitudConvenio.objects.select_related('estudiante','directora','solicitante','convenio'),pk=solicitud_id)
    if request.method=='POST' and request.user.rol!='DIRECTORA':return HttpResponseForbidden('Solo Dirección decide.')
    form=DecisionForm(request.POST if request.method=='POST' else None,estudiante=s.estudiante,
        initial={'obligaciones':s.propuesta['obligaciones'],'motivo':''})
    cuotas=CuotasFormSet(request.POST if request.method=='POST' else None,prefix='cuotas',initial=cantidad_iniciales(request,s.propuesta['cuotas']))
    plan=None
    if request.method=='POST' and form.is_valid():
        rechazo=form.cleaned_data['decision']=='RECHAZADA'
        if rechazo or cuotas.is_valid():
            try:
                datos={'obligaciones':[o.pk for o in form.cleaned_data['obligaciones']],
                       'cuotas':cuotas_limpias(cuotas) if not rechazo else None,'motivo':form.cleaned_data['motivo']}
                if not rechazo and request.POST.get('accion')!='resolver':
                    plan,revision=convenios.previsualizar(usuario=request.user,solicitud_id=s.pk,**datos)
                    form.data=form.data.copy();form.data['revision']=revision
                else:
                    convenios.resolver(usuario=request.user,solicitud_id=s.pk,decision=form.cleaned_data['decision'],revision=form.cleaned_data['revision'],**datos)
                    return redirect('convenios_solicitud',solicitud_id=s.pk)
            except PermissionDenied:return HttpResponseForbidden('Solo Dirección activa decide.')
            except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/convenios/solicitud.html',{'solicitud':s,'form':form,'cuotas':cuotas,'plan':plan})


def contexto_detalle(convenio,portal=False):
    datos=convenios.resumen(convenio)
    datos.update(portal=portal,solvente=convenios.solvente(convenio.estudiante),
        revisiones=convenio.revisiones.select_related('directora','nuevo'),
        movimientos=convenio.cuotas.all().prefetch_related('aplicaciones_pago__pago'))
    return datos


@acceso(ROLES)
@require_http_methods(['GET'])
def detalle(request,convenio_id):
    convenio=get_object_or_404(ConvenioPago.objects.select_related('estudiante','usuario_autoriza'),pk=convenio_id)
    return render(request,'financiero/convenios/detalle.html',contexto_detalle(convenio))


@acceso_portal()
@require_http_methods(['GET'])
def portal(request,convenio_id):
    convenio=get_object_or_404(ConvenioPago.objects.select_related('estudiante'),pk=convenio_id,estudiante=request.estudiante)
    return render(request,'financiero/convenios/detalle.html',contexto_detalle(convenio,portal=True))


class RevisionForm(CondicionesForm):
    tipo_revision=forms.ChoiceField(choices=[('CANCELACION','Cancelar sin pagos de cuotas'),('MODIFICACION','Modificar sin pagos de cuotas')])


@acceso(('DIRECTORA',))
@require_http_methods(['GET','POST'])
def revision(request,convenio_id):
    convenio=get_object_or_404(ConvenioPago.objects.select_related('estudiante'),pk=convenio_id)
    form=RevisionForm(request.POST if request.method=='POST' else None,estudiante=convenio.estudiante,
        initial={'obligaciones':list(convenio.obligaciones_incluidas.values_list('obligacion_id',flat=True))})
    iniciales=[{'fecha':c.fecha_vencimiento,'monto':c.monto_cuota} for c in convenio.cuotas.order_by('numero_cuota')]
    cuotas=CuotasFormSet(request.POST if request.method=='POST' else None,prefix='cuotas',initial=cantidad_iniciales(request,iniciales))
    plan=None
    if request.method=='POST' and form.is_valid():
        modificar=form.cleaned_data['tipo_revision']=='MODIFICACION'
        if not modificar or cuotas.is_valid():
            try:
                resultado=convenios.revisar(usuario=request.user,convenio_id=convenio.pk,
                    accion=form.cleaned_data['tipo_revision'],motivo=form.cleaned_data['motivo'],clave=form.cleaned_data['clave'],
                    obligaciones=[o.pk for o in form.cleaned_data['obligaciones']],cuotas=cuotas_limpias(cuotas) if modificar else None,
                    revision=form.cleaned_data['revision'],confirmar=request.POST.get('accion')=='resolver')
                if hasattr(resultado,'pk'):return redirect('convenios_detalle',convenio_id=convenio.pk)
                form.data=form.data.copy();form.data['revision']=resultado['revision'];plan=resultado['plan'] or {'cancelacion':True}
            except PermissionDenied:return HttpResponseForbidden('Solo Dirección activa puede revisar.')
            except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/convenios/formulario.html',{'form':form,'cuotas':cuotas,'plan':plan,'convenio':convenio})


@acceso(('SECRETARIA','ADMINISTRADOR'))
@require_http_methods(['GET','POST'])
def cobro(request,convenio_id):
    from .servicios import reservar_recibo
    from .convenios_forms import AbonoForm
    from .models import Obligacion
    convenio=get_object_or_404(ConvenioPago.objects.select_related('estudiante'),pk=convenio_id)
    token=request.POST.get('token','') if request.method=='POST' else reservar_recibo(request.user,convenio.estudiante)
    form=AbonoForm(request.POST if request.method=='POST' else None,resumen=convenios.resumen(convenio),
        obligaciones=Obligacion.objects.filter(convenios__convenio=convenio).order_by('pk'),initial={'token':token})
    if request.method=='POST' and form.is_valid():
        try:
            pago,_=convenios.registrar_abono(usuario=request.user,convenio_id=convenio.pk,
                token=form.cleaned_data['token'],metodo=form.cleaned_data['metodo'],referencia=form.cleaned_data['referencia'],
                cuotas=form.aplicaciones('cuota',form.ids_cuotas),obligaciones=form.aplicaciones('obligacion',form.ids_obligaciones))
            return redirect('finanzas_recibo',pago_id=pago.pk)
        except PermissionDenied:return HttpResponseForbidden('Su cuenta ya no puede cobrar.')
        except (ValidationError,DatabaseError) as ex:error(form,ex)
    return render(request,'financiero/convenios/cobro.html',{'form':form,'convenio':convenio})
