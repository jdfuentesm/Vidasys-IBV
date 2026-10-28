from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import redirect, render

from .forms import AsistenciaForm, CalificacionForm, SesionExtraordinariaForm
from .models import Calificacion, Estudiante, InscripcionCurso


def probar_conexion(request):
    # Intentamos traer todos los estudiantes
    estudiantes = Estudiante.objects.all()
    total = estudiantes.count()

    # Armamos un texto simple para ver en el navegador
    respuesta = f"¡Conexión exitosa! Hay {total} estudiantes en la base de datos.<br>"
    for est in estudiantes[:5]:  # Solo mostramos los primeros 5
        respuesta += f"- {est.codigo_estudiante}: {est.nombres} {est.apellidos}<br>"

    return HttpResponse(respuesta)


def registrar_asistencia(request):
    if request.method == "POST":
        form = AsistenciaForm(request.POST)
        if form.is_valid():
            try:
                asistencia = form.save()
                messages.success(
                    request,
                    f"✅ Asistencia registrada: {asistencia.inscripcion} - Clase {asistencia.sesion.numero_clase} ({asistencia.estado_asistencia}).",
                )
                return redirect("registrar_asistencia")
            except IntegrityError as e:
                messages.error(request, f"❌ Error al guardar: {e}")
        else:
            messages.error(
                request, "❌ El formulario tiene errores. Revisa los campos."
            )
    else:
        form = AsistenciaForm()

    # Traemos el reporte de asistencias para mostrarlo en la misma página
    inscripciones = InscripcionCurso.objects.all()

    return render(
        request,
        "academico/registrar_asistencia.html",
        {"form": form, "inscripciones": inscripciones},
    )


def autorizar_clase_extraordinaria(request):
    if request.method == "POST":
        form = SesionExtraordinariaForm(request.POST)
        if form.is_valid():
            try:
                sesion = form.save()
                messages.success(
                    request,
                    f"✅ Clase {sesion.numero_clase} autorizada correctamente por {sesion.usuario_autoriza}.",
                )
                return redirect("autorizar_clase_extraordinaria")
            except IntegrityError as e:
                # Aquí caen los errores de tu clean() (ej: falta motivo o no es directora)
                messages.error(request, f"❌ Error al autorizar: {e}")
        else:
            messages.error(
                request, "❌ El formulario tiene errores. Revisa los campos."
            )
    else:
        form = SesionExtraordinariaForm()

    return render(request, "academico/autorizar_clase.html", {"form": form})


def registrar_calificacion(request):
    if request.method == "POST":
        form = CalificacionForm(request.POST)
        if form.is_valid():
            try:
                # Obtenemos la inscripción seleccionada
                inscripcion = form.cleaned_data["inscripcion"]

                # Buscamos si ya existe una calificación para esta inscripción
                calificacion_existente = Calificacion.objects.filter(
                    inscripcion=inscripcion
                ).first()

                if calificacion_existente:
                    # Si existe, actualizamos los campos manualmente
                    calificacion_existente.nota_asistencia = form.cleaned_data[
                        "nota_asistencia"
                    ]
                    calificacion_existente.nota_uniforme = form.cleaned_data[
                        "nota_uniforme"
                    ]
                    calificacion_existente.nota_participacion = form.cleaned_data[
                        "nota_participacion"
                    ]
                    calificacion_existente.nota_companerismo = form.cleaned_data[
                        "nota_companerismo"
                    ]
                    calificacion_existente.puntos_extras = form.cleaned_data[
                        "puntos_extras"
                    ]
                    calificacion_existente.tarea_1 = form.cleaned_data["tarea_1"]
                    calificacion_existente.examen_1 = form.cleaned_data["examen_1"]
                    calificacion_existente.tarea_2 = form.cleaned_data["tarea_2"]
                    calificacion_existente.examen_2 = form.cleaned_data["examen_2"]
                    calificacion_existente.observaciones = form.cleaned_data[
                        "observaciones"
                    ]
                    calificacion_existente.save()  # El save() recalcula la nota final
                    messages.success(
                        request,
                        f"✅ Nota ACTUALIZADA para {inscripcion}. Nota Final: {calificacion_existente.nota_final}. Estado: {calificacion_existente.estado}.",
                    )
                else:
                    # Si no existe, la creamos desde cero
                    calificacion = form.save()
                    messages.success(
                        request,
                        f"✅ Nota CREADA para {calificacion.inscripcion}. Nota Final: {calificacion.nota_final}. Estado: {calificacion.estado}.",
                    )

                return redirect("registrar_calificacion")
            except IntegrityError as e:
                messages.error(request, f"❌ Error al guardar: {e}")
        else:
            messages.error(request, "❌ Errores en el formulario. Revisa los datos.")
    else:
        form = CalificacionForm()

    return render(request, "academico/registrar_calificacion.html", {"form": form})
