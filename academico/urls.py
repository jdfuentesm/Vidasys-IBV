from django.urls import path

from . import views, flujo_views, estudiante_views

urlpatterns = [
    path("estudiantes/", estudiante_views.estudiantes, name="estudiantes"),
    path("estudiantes/nuevo/", estudiante_views.estudiante_formulario, name="estudiante_nuevo"),
    path("estudiantes/<int:estudiante_id>/", estudiante_views.estudiante_expediente, name="estudiante_expediente"),
    path("estudiantes/<int:estudiante_id>/editar/", estudiante_views.estudiante_formulario, name="estudiante_editar"),
    path("estudiantes/<int:estudiante_id>/matricular/", flujo_views.matricula_secretaria, name="estudiante_matricular"),
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
