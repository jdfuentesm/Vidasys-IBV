from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import AsistenciaForm, CalificacionForm, SesionExtraordinariaForm
from .models import Calificacion, Curso, Estudiante, InscripcionCurso


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


@login_required
def registrar_calificacion(request):
    if not request.user.is_active or request.user.rol != "MAESTRO":
        return HttpResponseForbidden("Solo un docente con cuenta activa puede registrar calificaciones.")

    contexto = {"form": None, "cursos": [], "inscripciones": [], "curso": None}
    try:
        cursos = Curso.objects.filter(maestro__usuario=request.user).select_related("materia", "ciclo", "maestro")
        contexto["cursos"] = list(cursos)
        datos = request.POST if request.method == "POST" else request.GET
        curso_id = datos.get("curso")
        if curso_id:
            if not curso_id.isdecimal():
                return HttpResponseForbidden("El curso seleccionado no está disponible.")
            curso = get_object_or_404(cursos, pk=curso_id)
            contexto["curso"] = curso
            inscripciones = InscripcionCurso.objects.filter(curso=curso).select_related(
                "matricula__estudiante", "curso__materia", "curso__ciclo"
            )
            contexto["inscripciones"] = list(inscripciones.select_related("calificacion"))
            seleccion = datos.get("inscripcion")
            if request.method == "POST" and not seleccion:
                messages.error(request, "Seleccione un estudiante antes de guardar su calificación.")
                return render(request, "academico/registrar_calificacion.html", contexto)
            inscripcion = None
            if seleccion:
                if not seleccion.isdecimal():
                    return HttpResponseForbidden("La inscripción seleccionada no está disponible.")
                inscripcion = get_object_or_404(inscripciones, pk=seleccion)
            existente = Calificacion.objects.filter(inscripcion=inscripcion).first() if inscripcion else None
            form = CalificacionForm(
                request.POST if request.method == "POST" else None,
                instance=existente, inscripciones=inscripciones,
                initial={"inscripcion": inscripcion},
            )
            contexto["form"] = form
            contexto["seleccionada"] = inscripcion
            if inscripcion is not None:
                form.fields["inscripcion"].disabled = True
            if request.method == "POST" and form.is_valid():
                try:
                    with transaction.atomic():
                        form.save()
                except ValidationError as error:
                    form.add_error(None, " ".join(error.messages))
                except IntegrityError:
                    form.add_error(None, "No se pudo guardar. Puede que otra persona haya registrado la nota; recargue y revise los datos.")
                else:
                    messages.success(request, "Calificación actualizada correctamente." if existente else "Calificación registrada correctamente.")
                    return redirect(reverse("registrar_calificacion") + "?" + urlencode({
                        "curso": curso.pk, "inscripcion": form.instance.inscripcion_id,
                    }))
        elif request.method == "POST":
            messages.error(request, "Seleccione primero uno de sus cursos.")
    except DatabaseError:
        # No expone SQL ni detalles de conexión al usuario.
        contexto = {"form": None, "cursos": [], "inscripciones": [], "curso": None}
        messages.error(request, "No se pudieron consultar o guardar las calificaciones. La estructura de la base de datos debe ser revisada por la administración.")
        return render(request, "academico/registrar_calificacion.html", contexto, status=503)
    return render(request, "academico/registrar_calificacion.html", contexto)
