"""
Managers personalizados para el modelo Usuario de VidaSys-IBV.
"""

from django.contrib.auth.base_user import BaseUserManager


class UsuarioManager(BaseUserManager):
    """
    Manager personalizado para el modelo Usuario.
    """
    
    use_in_migrations = True
    
    def _create_user(self, numero_usuario, correo_acceso, password, **extra_fields):
        if not numero_usuario:
            raise ValueError('El número de usuario es obligatorio')
        if not correo_acceso:
            raise ValueError('El correo de acceso es obligatorio')
        
        correo_acceso = self.normalize_email(correo_acceso)
        
        usuario = self.model(
            numero_usuario=numero_usuario,
            correo_acceso=correo_acceso,
            **extra_fields
        )
        
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario
    
    def create_user(self, numero_usuario, correo_acceso, password=None, **extra_fields):
        """Crear usuario normal."""
        extra_fields.setdefault('rol', 'ESTUDIANTE')
        extra_fields.setdefault('estado_cuenta', 'ACTIVA')
        extra_fields.setdefault('debe_cambiar_password', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('is_staff', False)
        
        return self._create_user(
            numero_usuario, correo_acceso, password, **extra_fields
        )
    
    def create_superuser(self, numero_usuario, correo_acceso, password=None, **extra_fields):
        """Crear superusuario."""
        extra_fields.setdefault('rol', 'ADMINISTRADOR')
        extra_fields.setdefault('estado_cuenta', 'ACTIVA')
        extra_fields.setdefault('debe_cambiar_password', False)
        extra_fields['is_superuser'] = True
        extra_fields['is_staff'] = True
        
        return self._create_user(
            numero_usuario, correo_acceso, password, **extra_fields
        )