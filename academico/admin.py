from django.contrib import admin

from .models import (
    Asistencia,
    Calificacion,
    CicloAcademico,
    Curso,
    Estudiante,
    InscripcionCurso,
    Maestro,
    Materia,
    Matricula,
    SesionClase,
)


@admin.register(Estudiante)
class EstudianteAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_estudiante",
        "nombres",
        "apellidos",
        "correo",
        "telefono",
        "fecha_ingreso",
        "estado",
    )

    search_fields = (
        "codigo_estudiante",
        "nombres",
        "apellidos",
        "correo",
    )

    list_filter = (
        "estado",
        "fecha_ingreso",
    )

    ordering = (
        "apellidos",
        "nombres",
    )


@admin.register(Maestro)
class MaestroAdmin(admin.ModelAdmin):
    list_display = (
        "nombres",
        "apellidos",
        "correo",
        "telefono",
        "pais",
        "estado",
    )

    search_fields = (
        "nombres",
        "apellidos",
        "correo",
    )

    list_filter = (
        "estado",
        "pais",
    )

    ordering = (
        "apellidos",
        "nombres",
    )


@admin.register(Materia)
class MateriaAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_materia",
        "nombre",
        "estado",
    )

    search_fields = (
        "codigo_materia",
        "nombre",
    )

    list_filter = ("estado",)

    ordering = ("nombre",)


@admin.register(CicloAcademico)
class CicloAcademicoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "numero_ciclo",
        "fecha_inicio",
        "fecha_fin",
        "estado",
    )

    search_fields = ("nombre",)

    list_filter = (
        "estado",
        "fecha_inicio",
    )

    ordering = ("-fecha_inicio",)


@admin.register(Curso)
class CursoAdmin(admin.ModelAdmin):
    list_display = (
        "materia",
        "maestro",
        "ciclo",
        "fecha_inicio",
        "fecha_fin",
        "modalidad",
        "estado",
    )

    search_fields = (
        "materia__codigo_materia",
        "materia__nombre",
        "maestro__nombres",
        "maestro__apellidos",
    )

    list_filter = (
        "estado",
        "modalidad",
        "ciclo",
    )

    autocomplete_fields = (
        "materia",
        "maestro",
        "ciclo",
    )

    ordering = ("-fecha_inicio",)


@admin.register(Matricula)
class MatriculaAdmin(admin.ModelAdmin):
    list_display = (
        "numero_matricula",
        "estudiante",
        "ciclo",
        "fecha_matricula",
        "estado",
    )

    search_fields = (
        "numero_matricula",
        "estudiante__codigo_estudiante",
        "estudiante__nombres",
        "estudiante__apellidos",
    )

    list_filter = (
        "estado",
        "ciclo",
        "fecha_matricula",
    )

    autocomplete_fields = (
        "estudiante",
        "ciclo",
    )

    ordering = ("-fecha_matricula",)


@admin.register(InscripcionCurso)
class InscripcionCursoAdmin(admin.ModelAdmin):
    list_display = (
        "matricula",
        "curso",
        "fecha_inscripcion",
        "estado",
        "fecha_cierre",
    )

    search_fields = (
        "matricula__numero_matricula",
        "matricula__estudiante__codigo_estudiante",
        "matricula__estudiante__nombres",
        "matricula__estudiante__apellidos",
        "curso__materia__nombre",
    )

    list_filter = (
        "estado",
        "curso",
        "fecha_inscripcion",
    )

    autocomplete_fields = (
        "matricula",
        "curso",
    )

    ordering = ("-fecha_inscripcion",)


@admin.register(SesionClase)
class SesionClaseAdmin(admin.ModelAdmin):
    list_display = (
        "curso",
        "numero_clase",
        "fecha",
        "hora_inicio",
        "hora_fin",
        "estado",
    )

    search_fields = (
        "curso__materia__nombre",
        "curso__maestro__nombres",
        "curso__maestro__apellidos",
    )

    list_filter = (
        "estado",
        "fecha",
        "curso",
    )

    autocomplete_fields = ("curso",)

    ordering = (
        "-fecha",
        "numero_clase",
    )


@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = (
        "inscripcion",
        "sesion",
        "estado_asistencia",
    )

    search_fields = (
        "inscripcion__matricula__numero_matricula",
        "inscripcion__matricula__estudiante__codigo_estudiante",
        "inscripcion__matricula__estudiante__nombres",
        "inscripcion__matricula__estudiante__apellidos",
    )

    list_filter = (
        "estado_asistencia",
        "sesion__fecha",
    )

    autocomplete_fields = (
        "inscripcion",
        "sesion",
    )


@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = (
        "inscripcion",
        "nota_final",
        "fecha_registro",
        "estado",
    )

    search_fields = (
        "inscripcion__matricula__numero_matricula",
        "inscripcion__matricula__estudiante__codigo_estudiante",
        "inscripcion__matricula__estudiante__nombres",
        "inscripcion__matricula__estudiante__apellidos",
        "inscripcion__curso__materia__nombre",
    )

    list_filter = (
        "estado",
        "fecha_registro",
    )

    autocomplete_fields = ("inscripcion",)

    ordering = ("-fecha_registro",)
