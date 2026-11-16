from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from academico.models import Estudiante
from .models import Usuario
from .usuarios_forms import CuentaForm, AltaCuentaForm, VinculoEstudianteForm
from .usuarios_servicios import es_administrador, guardar_cuenta, vincular_estudiante, restablecer_acceso


def administracion(view):
    @never_cache
    @login_required
    @wraps(view)
    def protegida(request, *args, **kwargs):
        if not es_administrador(request.user):
            return HttpResponseForbidden('La administración de usuarios es exclusiva de ADMINISTRADOR activo.')
        return view(request, *args, **kwargs)
    return protegida


def mostrar_error(form, error):
    if isinstance(error, ValidationError):
        form.add_error(None, ' '.join(error.messages))
    elif isinstance(error, IntegrityError):
        form.add_error(None, 'Existe un identificador o vínculo duplicado. No se guardó la operación.')
    else:
        form.add_error(None, 'No se pudo guardar. Recargue y revise los datos antes de intentar nuevamente.')


@administracion
@require_http_methods(['GET'])
def listado(request):
    q=request.GET.get('q','').strip()[:150]
    rol=request.GET.get('rol','')
    estado=request.GET.get('estado','')
    usuarios=Usuario.objects.only('id_usuario','numero_usuario','correo_acceso','rol','estado_cuenta').order_by('numero_usuario','pk')
    if q:
        usuarios=usuarios.filter(Q(numero_usuario__icontains=q)|Q(correo_acceso__icontains=q))
    if rol in dict(Usuario.ROLES):usuarios=usuarios.filter(rol=rol)
    else:rol=''
    if estado in dict(Usuario.ESTADOS_CUENTA):usuarios=usuarios.filter(estado_cuenta=estado)
    else:estado=''
    parametros=request.GET.copy();parametros.pop('page',None)
    return render(request,'core/usuarios/listado.html',{'pagina':Paginator(usuarios,20).get_page(request.GET.get('page')),
        'q':q,'rol':rol,'estado':estado,'roles':Usuario.ROLES,'estados':Usuario.ESTADOS_CUENTA,'parametros':parametros.urlencode()})


@administracion
@require_http_methods(['GET','POST'])
@sensitive_post_parameters()
def formulario(request, usuario_id=None):
    usuario=get_object_or_404(Usuario,pk=usuario_id) if usuario_id else None
    clase=CuentaForm if usuario else AltaCuentaForm
    form=clase(request.POST if request.method=='POST' else None,instance=usuario)
    if request.method=='POST' and form.is_valid():
        try:
            cuenta=guardar_cuenta(actor=request.user,usuario_id=usuario_id,datos=form.cleaned_data,password=form.cleaned_data.get('password1'))
            if cuenta.pk==request.user.pk and not es_administrador(cuenta):
                logout(request)
                messages.success(request,'Cuenta actualizada. Su sesión administrativa se cerró por el cambio de acceso.')
                return redirect('login')
            messages.success(request,'Cuenta actualizada.' if usuario_id else 'Cuenta creada. Debe cambiar su contraseña temporal al ingresar.')
            return redirect('usuarios_editar',usuario_id=cuenta.pk)
        except (ValidationError,DatabaseError) as error:
            mostrar_error(form,error)
    return render(request,'core/usuarios/formulario.html',{'form':form,'cuenta':usuario})


@administracion
@require_http_methods(['GET','POST'])
def vinculo(request, usuario_id):
    usuario=get_object_or_404(Usuario,pk=usuario_id)
    if usuario.rol!='ESTUDIANTE':
        return HttpResponseForbidden('Solo se vinculan cuentas de rol ESTUDIANTE.')
    form=VinculoEstudianteForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            estudiante=vincular_estudiante(actor=request.user,usuario_id=usuario.pk,estudiante_id=form.cleaned_data['estudiante'].pk)
            messages.success(request,f'Vínculo confirmado con el expediente {estudiante.codigo_estudiante}.')
            return redirect('usuarios_editar',usuario_id=usuario.pk)
        except (ValidationError,DatabaseError) as error:
            mostrar_error(form,error)
    return render(request,'core/usuarios/vinculo.html',{'form':form,'cuenta':usuario,
        'vinculado':Estudiante.objects.filter(usuario=usuario).first()})


@administracion
@require_http_methods(['GET','POST'])
@sensitive_post_parameters()
def restablecer(request,usuario_id):
    usuario=get_object_or_404(Usuario,pk=usuario_id)
    form=SetPasswordForm(usuario,request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            cuenta=restablecer_acceso(actor=request.user,usuario_id=usuario.pk,password=form.cleaned_data['new_password1'])
            if cuenta.pk==request.user.pk:update_session_auth_hash(request,cuenta)
            messages.success(request,'Acceso restablecido. Entregue la contraseña temporal por un canal seguro; deberá cambiarse al ingresar.')
            return redirect('usuarios_editar',usuario_id=cuenta.pk)
        except (ValidationError,DatabaseError) as error:
            mostrar_error(form,error)
    return render(request,'core/usuarios/restablecer.html',{'form':form,'cuenta':usuario})


@never_cache
@login_required
@require_http_methods(['GET','POST'])
@sensitive_post_parameters()
def cambiar_password(request):
    form=PasswordChangeForm(request.user,request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        try:
            if form.cleaned_data['new_password1'] == form.cleaned_data['old_password']:
                raise ValidationError('Elija una contraseña nueva diferente de la contraseña temporal o anterior.')
            with transaction.atomic():
                usuario=Usuario.objects.select_for_update().get(pk=request.user.pk)
                # Evita sobrescribir un restablecimiento concurrente con una clave anterior.
                if not usuario.check_password(form.cleaned_data['old_password']):
                    raise ValidationError('Su acceso cambió. Ingrese nuevamente antes de cambiar la contraseña.')
                usuario.set_password(form.cleaned_data['new_password1'])
                usuario.debe_cambiar_password=False
                usuario.save(update_fields=['password','debe_cambiar_password','fecha_actualizacion'])
            update_session_auth_hash(request,usuario)
            messages.success(request,'Contraseña actualizada. Su cuenta está lista para continuar.')
            return redirect('dashboard')
        except (ValidationError,DatabaseError) as error:
            mostrar_error(form,error)
    return render(request,'core/usuarios/cambiar_password.html',{'form':form})
