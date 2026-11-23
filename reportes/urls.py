from django.urls import path
from . import views, financiero_views

urlpatterns=[
    path('',views.panel,name='reportes'),
    path('finanzas/',financiero_views.reporte,name='finanzas_centro'),
    path('finanzas/<slug:tipo>/',financiero_views.reporte,name='finanzas_reporte'),
    path('<slug:tipo>/',views.reporte,name='reportes_consultar'),
]
