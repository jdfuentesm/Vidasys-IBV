from django.contrib import messages
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import redirect, render

from .forms import AsistenciaForm, SesionExtraordinariaForm
from .models import Estudiante, InscripcionCurso


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
