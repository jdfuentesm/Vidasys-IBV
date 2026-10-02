"""
Modelos del módulo core de VidaSys-IBV.

Contiene:
- Usuario: autenticación y control de acceso con roles personalizados.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UsuarioManager


class Usuario(AbstractBaseUser, PermissionsMixin):
    """
    Modelo de usuario personalizado para el IBV.
    
    Mapea la tabla 'usuario' ya existente en PostgreSQL.
    Usa 'numero_usuario' o 'correo_acceso' para autenticación.
    """
    
    # ---- Roles disponibles en el sistema ----
    ROLES = [
        ('ADMINISTRADOR', 'Administrador del sistema'),
        ('SECRETARIA', 'Secretaría'),
        ('MAESTRO', 'Maestro'),
        ('DIRECTORA', 'Directora'),
        ('PASTOR_PRINCIPAL', 'Pastor principal'),
        ('ESTUDIANTE', 'Estudiante'),
    ]
    
    # ---- Estados de cuenta disponibles ----
    ESTADOS_CUENTA = [
        ('ACTIVA', 'Activa'),
        ('BLOQUEADA', 'Bloqueada'),
        ('INACTIVA', 'Inactiva'),
    ]
    
    # ---- Campos ----
    id_usuario = models.BigAutoField(
        primary_key=True,
        db_column='id_usuario'
    )
    
    numero_usuario = models.CharField(
        max_length=30,
        unique=True,
        db_column='numero_usuario',
        verbose_name='Número de usuario'
    )
    
    correo_acceso = models.CharField(
        max_length=150,
        unique=True,
        db_column='correo_acceso',
        verbose_name='Correo de acceso'
    )
    
    # ⚠️ Mapeo: en Python se llama 'password', en BD es 'password_hash'
    password = models.TextField(
        db_column='password_hash',
        verbose_name='Contraseña (hash)'
    )
    
    rol = models.CharField(
        max_length=30,
        choices=ROLES,
        db_column='rol',
        verbose_name='Rol'
    )
    
    estado_cuenta = models.CharField(
        max_length=20,
        choices=ESTADOS_CUENTA,
        default='ACTIVA',
        db_column='estado_cuenta',
        verbose_name='Estado de la cuenta'
    )
    
    debe_cambiar_password = models.BooleanField(
        default=True,
        db_column='debe_cambiar_password',
        verbose_name='¿Debe cambiar contraseña?'
    )
    
    # ⚠️ Django espera 'last_login', pero nuestra columna es 'ultimo_acceso'
    last_login = models.DateTimeField(
        null=True,
        blank=True,
        db_column='ultimo_acceso',
        verbose_name='Último acceso'
    )
    
    # ---- Campos requeridos por PermissionsMixin (agregados a la tabla) ----
    is_superuser = models.BooleanField(
        default=False,
        db_column='is_superuser',
        verbose_name='¿Es superusuario?'
    )
    
    is_staff = models.BooleanField(
        default=False,
        db_column='is_staff',
        verbose_name='¿Puede acceder al admin?'
    )
    
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        db_column='fecha_creacion',
        verbose_name='Fecha de creación'
    )
    
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        db_column='fecha_actualizacion',
        verbose_name='Fecha de última actualización'
    )
    
    # ---- Configuración del manager ----
    objects = UsuarioManager()
    
    # ---- Configuración de autenticación ----
    USERNAME_FIELD = 'numero_usuario'
    REQUIRED_FIELDS = ['correo_acceso']
    
    # ---- Configuración de la tabla ----
    class Meta:
        db_table = 'usuario'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        managed = False  # ⚠️ Django NO modifica esta tabla (ya existe)
    
    # ---- Propiedades calculadas ----
    @property
    def is_active(self):
        """¿La cuenta está activa?"""
        return self.estado_cuenta == 'ACTIVA'
    
    @property
    def ultimo_acceso(self):
        """Alias de compatibilidad para last_login."""
        return self.last_login
    
    # ---- Métodos ----
    def __str__(self):
        return f'{self.numero_usuario} ({self.get_rol_display()})'
    
    def get_full_name(self):
        return self.numero_usuario
    
    def get_short_name(self):
        return self.numero_usuario