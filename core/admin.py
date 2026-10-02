"""
Configuración del panel de administración de Django
para el modelo Usuario de VidaSys-IBV.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    """
    Panel de administración personalizado para el modelo Usuario.
    """
    
    # ---- Lista de usuarios ----
    list_display = (
        'numero_usuario',
        'correo_acceso',
        'rol',
        'estado_cuenta',
        'is_superuser',
        'is_staff',
    )
    
    list_filter = (
        'rol',
        'estado_cuenta',
        'is_superuser',
        'is_staff',
    )
    
    search_fields = (
        'numero_usuario',
        'correo_acceso',
    )
    
    ordering = ('numero_usuario',)
    
    # ---- Formulario de edición ----
    fieldsets = (
        (None, {
            'fields': (
                'numero_usuario',
                'correo_acceso',
                'password',
            )
        }),
        (_('Información personal'), {
            'fields': (
                'rol',
                'estado_cuenta',
                'debe_cambiar_password',
            )
        }),
        (_('Permisos'), {
            'fields': (
                'is_superuser',
                'is_staff',
            )
        }),
        (_('Fechas'), {
            'fields': (
                'last_login',
                'fecha_creacion',
                'fecha_actualizacion',
            )
        }),
    )
    
    readonly_fields = (
        'last_login',
        'fecha_creacion',
        'fecha_actualizacion',
    )
    
    # ---- Formulario de creación ----
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'numero_usuario',
                'correo_acceso',
                'password1',
                'password2',
                'rol',
                'estado_cuenta',
                'is_superuser',
                'is_staff',
            ),
        }),
    )