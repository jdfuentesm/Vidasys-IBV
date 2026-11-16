from django.shortcuts import redirect
from django.urls import reverse


class CambioPasswordObligatorioMiddleware:
    """Impide usar una clave temporal para operar antes de reemplazarla."""
    def __init__(self,get_response):
        self.get_response=get_response

    def __call__(self,request):
        if request.user.is_authenticated and request.user.debe_cambiar_password:
            permitidas={reverse('cambiar_password'),reverse('logout'),reverse('login')}
            if request.path not in permitidas:
                respuesta=redirect('cambiar_password')
                respuesta['Cache-Control']='no-store, private'
                return respuesta
        return self.get_response(request)
