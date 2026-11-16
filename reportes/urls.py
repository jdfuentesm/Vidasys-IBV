from django.urls import path
from . import views

urlpatterns=[
    path('',views.panel,name='reportes'),
    path('<slug:tipo>/',views.reporte,name='reportes_consultar'),
]
