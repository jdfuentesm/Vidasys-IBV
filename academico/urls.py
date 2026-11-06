from django.urls import path

from . import views, flujo_views

urlpatterns = [
    path("matriculas/nueva/", flujo_views.matricula_secretaria, name="matricula_secretaria"),
    path("mis-cursos/", flujo_views.mis_cursos, name="mis_cursos"),
    path("cursos/<int:curso_id>/programar/", flujo_views.programar_sesiones, name="programar_sesiones"),
    path("cursos/<int:curso_id>/cierre/", flujo_views.cierre_curso, name="cierre_curso"),
    path("asistencia/", views.registrar_asistencia, name="registrar_asistencia"),
    path(
        "autorizar-clase/",
        views.autorizar_clase_extraordinaria,
        name="autorizar_clase_extraordinaria",
    ),
    path("calificacion/", views.registrar_calificacion, name="registrar_calificacion"),
]
