"""
URLs del módulo core de VidaSys-IBV.
"""

from django.urls import include, path

from . import views, portal, usuarios_views

urlpatterns = [
    path("reportes/", include("reportes.urls")),
    path("usuarios/", usuarios_views.listado, name="usuarios"),
    path("usuarios/nuevo/", usuarios_views.formulario, name="usuarios_nuevo"),
    path("usuarios/<int:usuario_id>/editar/", usuarios_views.formulario, name="usuarios_editar"),
    path("usuarios/<int:usuario_id>/vincular/", usuarios_views.vinculo, name="usuarios_vincular"),
    path("usuarios/<int:usuario_id>/restablecer/", usuarios_views.restablecer, name="usuarios_restablecer"),
    path("mi-cuenta/contrasena/", usuarios_views.cambiar_password, name="cambiar_password"),
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
