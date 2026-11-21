from django.urls import path
from . import views, becas_views, convenios_views

urlpatterns = [
    path('convenios/<int:convenio_id>/cobro/',convenios_views.cobro,name='convenios_cobro'),
    path('convenios/',convenios_views.listado,name='convenios_listado'),
    path('convenios/nuevo/',convenios_views.nueva,name='convenios_nuevo'),
    path('convenios/solicitudes/<int:solicitud_id>/',convenios_views.solicitud,name='convenios_solicitud'),
    path('convenios/<int:convenio_id>/',convenios_views.detalle,name='convenios_detalle'),
    path('convenios/<int:convenio_id>/revision/',convenios_views.revision,name='convenios_revision'),
    path('mis-convenios/<int:convenio_id>/',convenios_views.portal,name='convenios_portal'),
    path('becas/', becas_views.listado, name='becas_listado'),
    path('becas/nueva/', becas_views.nueva, name='becas_nueva'),
    path('becas/<int:solicitud_id>/', becas_views.detalle, name='becas_detalle'),
    path('', views.panel, name='finanzas_panel'),
    path('calendario/', views.calendario, name='finanzas_calendario'),
    path('conceptos/nuevo/', views.concepto, name='finanzas_concepto'),
    path('estudiantes/<int:estudiante_id>/', views.estado_cuenta, name='finanzas_cuenta'),
    path('estudiantes/<int:estudiante_id>/pago/', views.pago_nuevo, name='finanzas_pago'),
    path('recibos/<int:pago_id>/', views.recibo, name='finanzas_recibo'),
]
