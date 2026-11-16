from django.urls import path
from . import views

urlpatterns = [
    path('', views.panel, name='finanzas_panel'),
    path('calendario/', views.calendario, name='finanzas_calendario'),
    path('conceptos/nuevo/', views.concepto, name='finanzas_concepto'),
    path('estudiantes/<int:estudiante_id>/', views.estado_cuenta, name='finanzas_cuenta'),
    path('estudiantes/<int:estudiante_id>/pago/', views.pago_nuevo, name='finanzas_pago'),
    path('recibos/<int:pago_id>/', views.recibo, name='finanzas_recibo'),
]
