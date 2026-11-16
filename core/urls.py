"""
URLs del módulo core de VidaSys-IBV.
"""

from django.urls import path

from . import views, portal

urlpatterns = [
    path("portal/", portal.inicio, name="portal_inicio"),
    path("portal/academico/", portal.academico, name="portal_academico"),
    path("portal/cuenta/", portal.estado_cuenta, name="portal_cuenta"),
    path("portal/recibos/<int:pago_id>/", portal.recibo, name="portal_recibo"),
    # Login
    path("login/", views.login_view, name="login"),
    # Logout
    path("logout/", views.logout_view, name="logout"),
    # Dashboard (raíz)
    path("", views.dashboard, name="dashboard"),
]
