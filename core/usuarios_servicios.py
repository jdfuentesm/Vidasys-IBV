"""Operaciones institucionales de cuentas: autorización y cambios atómicos."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from academico.models import Estudiante, Maestro
from .models import Usuario


def es_administrador(usuario):
    return usuario.is_authenticated and usuario.is_active and usuario.rol == 'ADMINISTRADOR'


def bloquear_administracion(actor):
    # Bloqueo común y ordenado: dos administradores no pueden desactivar al último a la vez.
    activos = list(Usuario.objects.select_for_update().filter(rol='ADMINISTRADOR', estado_cuenta='ACTIVA').order_by('pk'))
    actual = Usuario.objects.select_for_update().get(pk=actor.pk)
    if not es_administrador(actual):
        raise PermissionDenied('La administración de cuentas requiere un administrador activo.')
    return activos


def validar_identificadores(usuario):
    otros = Usuario.objects.exclude(pk=usuario.pk)
    if otros.filter(Q(numero_usuario__iexact=usuario.numero_usuario) | Q(correo_acceso__iexact=usuario.numero_usuario)).exists():
        raise ValidationError('El número de usuario ya está utilizado como identificador de acceso.')
    if otros.filter(Q(correo_acceso__iexact=usuario.correo_acceso) | Q(numero_usuario__iexact=usuario.correo_acceso)).exists():
        raise ValidationError('El correo ya está utilizado como identificador de acceso.')


@transaction.atomic
def guardar_cuenta(*, actor, datos, usuario_id=None, password=None):
    activos = bloquear_administracion(actor)
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id) if usuario_id else Usuario()
    era_admin = usuario.pk and usuario.rol == 'ADMINISTRADOR' and usuario.is_active
    for nombre in ('numero_usuario', 'correo_acceso', 'rol', 'estado_cuenta'):
        setattr(usuario, nombre, datos[nombre])
    if era_admin and (usuario.rol != 'ADMINISTRADOR' or not usuario.is_active) and len(activos) <= 1:
        raise ValidationError('No puede desactivar, bloquear ni cambiar el rol del último administrador activo.')
    if usuario.pk and Estudiante.objects.filter(usuario=usuario).exists() and usuario.rol != 'ESTUDIANTE':
        raise ValidationError('La cuenta está vinculada a un estudiante. No se puede cambiar su rol desde esta pantalla.')
    if usuario.pk and Maestro.objects.filter(usuario=usuario).exists() and usuario.rol != 'MAESTRO':
        raise ValidationError('La cuenta tiene un perfil docente. Su cambio de rol requiere revisar ese vínculo previamente.')
    validar_identificadores(usuario)
    if not usuario.pk:
        if not password:
            raise ValidationError('Defina una contraseña temporal válida.')
        validate_password(password, usuario)
        usuario.set_password(password)
        usuario.debe_cambiar_password = True
        usuario.is_staff = False
        usuario.is_superuser = False
        usuario.full_clean()
        usuario.save(force_insert=True)
    else:
        # El módulo asigna roles institucionales, nunca permisos de superusuario.
        if usuario.rol != 'ADMINISTRADOR':
            usuario.is_staff = False
            usuario.is_superuser = False
        usuario.full_clean()
        usuario.save(update_fields=['numero_usuario', 'correo_acceso', 'rol', 'estado_cuenta',
                                    'is_staff', 'is_superuser', 'fecha_actualizacion'])
    return usuario


@transaction.atomic
def vincular_estudiante(*, actor, usuario_id, estudiante_id):
    bloquear_administracion(actor)
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id)
    if usuario.rol != 'ESTUDIANTE':
        raise ValidationError('Solo las cuentas de rol ESTUDIANTE pueden vincularse a expedientes estudiantiles.')
    if Maestro.objects.filter(usuario=usuario).exists():
        raise ValidationError('La cuenta tiene un perfil docente y no puede vincularse como estudiante.')
    estudiante = Estudiante.objects.select_for_update().get(pk=estudiante_id)
    if Estudiante.objects.filter(usuario=usuario).exclude(pk=estudiante.pk).exists():
        raise ValidationError('Esta cuenta ya tiene otro expediente vinculado. No se reasignó ninguna identidad.')
    if estudiante.usuario_id not in (None, usuario.pk):
        raise ValidationError('El expediente seleccionado ya tiene una cuenta vinculada.')
    if estudiante.usuario_id is None:
        estudiante.usuario = usuario
        estudiante.full_clean()
        estudiante.save(update_fields=['usuario'])
    return estudiante


@transaction.atomic
def restablecer_acceso(*, actor, usuario_id, password):
    bloquear_administracion(actor)
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id)
    validate_password(password, usuario)
    usuario.set_password(password)
    usuario.debe_cambiar_password = True
    usuario.save(update_fields=['password', 'debe_cambiar_password', 'fecha_actualizacion'])
    # No reactiva cuentas ni cambia vínculos o roles como efecto secundario.
    return usuario
