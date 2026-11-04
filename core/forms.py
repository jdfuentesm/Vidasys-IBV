"""Formularios de Django Admin vinculados explícitamente al usuario de VidaSys."""
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import Usuario


class UsuarioCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = Usuario
        fields = ("numero_usuario", "correo_acceso", "rol", "estado_cuenta", "is_staff", "is_superuser")


class UsuarioChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Usuario
        fields = "__all__"
