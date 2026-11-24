"""Paneles y bandeja F8.2: solo consulta y enlaces a los procedimientos originales."""
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from financiero.lectura import lectura_consistente
from reportes.financiero_forms import FiltrosFinancierosForm
from .paneles import TIPOS,cargar_bandeja,indicadores_direccion,indicadores_administracion


class FiltrosBandeja(forms.Form):
    vista=forms.ChoiceField(choices=[('ATENCION','Requieren atención'),('HISTORIAL','Todas las solicitudes')])
    tipo=forms.ChoiceField(required=False,choices=[('','Todos los trámites'),*TIPOS.items()])
    estado=forms.ChoiceField(required=False,choices=[('','Todos los estados'),('PENDIENTE','Pendiente'),('APROBADA','Aprobada'),('RECHAZADA','Rechazada')])
    q=forms.CharField(required=False,max_length=150,label='Persona, expediente o solicitante')
    desde=forms.DateField(required=False,label='Solicitada desde',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    hasta=forms.DateField(required=False,label='Solicitada hasta',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    def clean(self):
        d=super().clean()
        if d.get('desde') and d.get('hasta') and d['desde']>d['hasta']:raise forms.ValidationError('La fecha inicial debe ser anterior o igual a la final.')
        return d


@never_cache
@login_required
def inicio(request):
    if not request.user.is_active or request.user.rol not in ('DIRECTORA','ADMINISTRADOR'):
        return HttpResponseForbidden('Panel restringido a su rol institucional.')
    contexto={'usuario':request.user,'titulo_panel':'Dirección' if request.user.rol=='DIRECTORA' else 'Administración',
        'bajada_panel':'Situación actual y asuntos por revisar.' if request.user.rol=='DIRECTORA' else 'Control de operaciones y situación financiera.'}
    if request.user.rol=='ADMINISTRADOR':
        hoy=timezone.localdate();parametros={k:request.GET[k] for k in ('desde','hasta') if k in request.GET}
        if not parametros:parametros={'desde':hoy.replace(day=1).isoformat(),'hasta':hoy.isoformat()}
        form=FiltrosFinancierosForm(parametros,tipo='panel');contexto['form_panel']=form
        if not form.is_valid():return render(request,'core/dashboard.html',contexto,status=400)
    try:
        with lectura_consistente():
            contexto['panel_rol']=indicadores_direccion(request.user) if request.user.rol=='DIRECTORA' else indicadores_administracion(request.user,form.cleaned_data)
    except DatabaseError:
        contexto['error_panel']='No se pudieron consultar todas las fuentes. No se muestran indicadores incompletos; intente de nuevo.'
        return render(request,'core/dashboard.html',contexto,status=503)
    return render(request,'core/dashboard.html',contexto)


@never_cache
@login_required
@require_safe
def pendientes(request):
    if not request.user.is_active or request.user.rol!='DIRECTORA':
        return HttpResponseForbidden('La bandeja unificada corresponde exclusivamente a Dirección.')
    parametros=request.GET.copy()
    if 'vista' not in parametros:parametros['vista']='ATENCION'
    form=FiltrosBandeja(parametros);contexto={'form':form}
    if not form.is_valid():return render(request,'core/paneles/bandeja.html',contexto,status=400)
    try:
        with lectura_consistente():filas=cargar_bandeja(request.user)
    except DatabaseError:
        contexto['error_bandeja']='No se pudo cargar la bandeja completa. Intente de nuevo; no se muestran pendientes parciales.'
        return render(request,'core/paneles/bandeja.html',contexto,status=503)
    f=form.cleaned_data
    if f['vista']=='ATENCION':filas=[r for r in filas if r['atencion']]
    if f['tipo']:filas=[r for r in filas if r['tipo']==f['tipo']]
    if f['estado']:filas=[r for r in filas if r['estado']==f['estado']]
    if f['q']:
        palabras=f['q'].casefold().split()
        filas=[r for r in filas if all(p in (' '.join(str(r[k]) for k in ('persona','solicitante','titulo','clave','motivo','consecuencia'))).casefold() for p in palabras)]
    if f['desde']:filas=[r for r in filas if timezone.localdate(r['fecha'])>=f['desde']]
    if f['hasta']:filas=[r for r in filas if timezone.localdate(r['fecha'])<=f['hasta']]
    parametros.pop('page',None)
    contexto.update(pagina=Paginator(filas,20).get_page(request.GET.get('page')),cantidad=len(filas),parametros=parametros.urlencode())
    return render(request,'core/paneles/bandeja.html',contexto)
