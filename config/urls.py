"""
URLs principales del proyecto VidaSys-IBV.
"""

from django.contrib import admin
from django.urls import include, path

from academico import views

urlpatterns = [
    # Panel de administración de Django
    path("admin/", admin.site.urls),
    # URLs de la aplicación core (login, logout, dashboard)
    path("", include("core.urls")),
]
urlpatterns = [
    # ... tus otras rutas ...
    path("probar-conexion/", views.probar_conexion, name="probar_conexion"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("academico.urls")),  # <--- Esta línea es la clave
]
