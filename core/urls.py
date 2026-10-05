"""
URLs del módulo core de VidaSys-IBV.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Login
    path("login/", views.login_view, name="login"),
    # Logout
    path("logout/", views.logout_view, name="logout"),
    # Dashboard (raíz)
    path("", views.dashboard, name="dashboard"),
]
