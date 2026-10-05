"""
Vistas del módulo core de VidaSys-IBV.

Contiene:
- login_view: Vista de inicio de sesión.
- logout_view: Vista para cerrar sesión.
- dashboard: Vista del panel principal (temporal).
"""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


def login_view(request):
    """
    Vista de inicio de sesión.

    Acepta:
    - GET:  Muestra el formulario de login.
    - POST: Procesa el formulario.

    El usuario puede iniciar sesión con:
    - Su número de usuario (ej: admin)
    - Su correo de acceso (ej: admin@ibv.local)
    """

    # Si el usuario ya está logueado, redirigir al dashboard
    if request.user.is_authenticated:
        return redirect("dashboard")

    # Si es una petición POST → procesar el formulario
    if request.method == "POST":
        identificador = request.POST.get("numero_usuario", "").strip()
        password = request.POST.get("password", "")

        # Validaciones básicas
        if not identificador or not password:
            return render(
                request,
                "core/login.html",
                {"error": "Por favor, complete todos los campos."},
            )

        # Intentar autenticar con número de usuario O correo
        usuario = None

        # Opción 1: Autenticar por número de usuario
        usuario = authenticate(request, username=identificador, password=password)

        # Opción 2: Si no funcionó, intentar por correo
        if usuario is None:
            from .models import Usuario

            try:
                # Buscar usuario por correo
                user_obj = Usuario.objects.get(correo_acceso=identificador)
                # Autenticar con su número de usuario real
                usuario = authenticate(
                    request, username=user_obj.numero_usuario, password=password
                )
            except Usuario.DoesNotExist:
                pass

        # Verificar si la autenticación fue exitosa
        if usuario is not None:
            # Verificar que la cuenta esté activa
            if usuario.is_active:
                login(request, usuario)
                messages.success(request, f"¡Bienvenido, {usuario.numero_usuario}!")
                return redirect("dashboard")
            else:
                return render(
                    request,
                    "core/login.html",
                    {
                        "error": "Su cuenta está bloqueada o inactiva. Contacte a la administración."
                    },
                )
        else:
            return render(
                request,
                "core/login.html",
                {"error": "Usuario o contraseña incorrectos."},
            )

    # Si es GET → mostrar el formulario
    return render(request, "core/login.html")


def logout_view(request):
    """
    Vista para cerrar sesión.
    """
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    """
    Vista del dashboard principal.
    TEMPORAL: por ahora solo muestra un mensaje.
    Se reemplazará por el dashboard real de cada rol.
    """
    return render(request, "core/dashboard.html", {"usuario": request.user})
