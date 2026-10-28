from django.urls import path

from . import views

urlpatterns = [
    path("asistencia/", views.registrar_asistencia, name="registrar_asistencia"),
    path(
        "autorizar-clase/",
        views.autorizar_clase_extraordinaria,
        name="autorizar_clase_extraordinaria",
    ),
    path("calificacion/", views.registrar_calificacion, name="registrar_calificacion"),
]
