"""
URLs principales del proyecto VidaSys-IBV.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Panel de administración de Django
    path("admin/", admin.site.urls),
    # URLs de la aplicación core (login, logout, dashboard)
    path("", include("core.urls")),
]
