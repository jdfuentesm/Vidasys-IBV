from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import AsistenciaForm, FilaCalificacionForm, SesionExtraordinariaForm
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

    contexto = {"cursos": [], "filas": [], "curso": None,
                "columnas": [(campo, Calificacion._meta.get_field(campo).verbose_name,
                              limite) for campo, limite in Calificacion.LIMITES_COMPONENTES.items()]}
    try:
        cursos = Curso.objects.filter(maestro__usuario=request.user).select_related("materia", "ciclo", "maestro")
        contexto["cursos"] = list(cursos)
        datos = request.POST if request.method == "POST" else request.GET
        curso_id = datos.get("curso")
        if not curso_id:
            if request.method == "POST":
                messages.error(request, "Seleccione primero uno de sus cursos.")
            return render(request, "academico/registrar_calificacion.html", contexto)
        if not curso_id.isascii() or not curso_id.isdecimal() or len(curso_id) > 18:
            return HttpResponseForbidden("El curso seleccionado no está disponible.")
        curso = get_object_or_404(cursos, pk=curso_id)
        contexto["curso"] = curso
        # El bloqueo y el guardado completo comparten transacción. Nunca cambia el esquema.
        with transaction.atomic():
            inscripciones = InscripcionCurso.objects.filter(curso=curso).order_by("pk")
            if request.method == "POST":
                inscripciones = inscripciones.select_for_update()
            inscripciones = list(inscripciones)
            if request.method == "POST":
                enviados = datos.getlist("inscripciones")
                esperados = {str(item.pk) for item in inscripciones}
                if len(enviados) != len(esperados) or set(enviados) != esperados:
                    return HttpResponseForbidden(
                        "La lista de estudiantes no corresponde a este curso. Recargue el libro antes de guardar."
                    )
            notas = {nota.inscripcion_id: nota for nota in
                     Calificacion.objects.filter(inscripcion__in=inscripciones)}
            # Relaciones precargadas después del bloqueo para evitar outer joins con FOR UPDATE.
            relaciones = InscripcionCurso.objects.filter(pk__in=[i.pk for i in inscripciones]).select_related(
                "matricula__estudiante", "curso__materia", "curso__ciclo"
            ).in_bulk()
            for inscripcion in inscripciones:
                inscripcion.matricula = relaciones[inscripcion.pk].matricula
                inscripcion.curso = relaciones[inscripcion.pk].curso
                nota = notas.get(inscripcion.pk) or Calificacion(inscripcion=inscripcion)
                nota.inscripcion = inscripcion
                form = FilaCalificacionForm(
                    request.POST if request.method == "POST" else None,
                    inscripcion=inscripcion, instance=nota,
                    inscripciones=InscripcionCurso.objects.filter(pk=inscripcion.pk),
                    prefix=f"nota-{inscripcion.pk}",
                )
                contexto["filas"].append({"inscripcion": inscripcion, "form": form,
                                         "nota": notas.get(inscripcion.pk)})
            if request.method == "POST":
                validas = [fila["form"].is_valid() for fila in contexto["filas"]]
                if datos.get("accion") == "calcular":
                    resultados = []
                    for fila, valida in zip(contexto["filas"], validas):
                        form = fila["form"]
                        nota = (form.instance.nota_final if form.bloqueada else
                                form.instance.calcular_nota() if valida and not form.omitir else None)
                        estado = ("Bloqueada por inasistencia" if form.bloqueada else
                                  "Revise esta fila" if not valida else
                                  dict(Calificacion.ESTADOS_CALIFICACION)[Calificacion.estado_para_nota(nota)])
                        resultados.append({"id": fila["inscripcion"].pk,
                                           "nota": str(nota) if nota is not None else "Pendiente",
                                           "estado": estado})
                    return JsonResponse({"filas": resultados})
                if all(validas):
                    guardadas = 0
                    try:
                        with transaction.atomic():
                            for fila in contexto["filas"]:
                                form = fila["form"]
                                if not form.omitir and form.has_changed():
                                    form.save()
                                    guardadas += 1
                    except ValidationError as error:
                        messages.error(request, "No se guardó ninguna calificación. " + " ".join(error.messages))
                    except IntegrityError:
                        messages.error(request, "No se guardó ninguna calificación. Recargue el libro: otra persona pudo registrar una nota.")
                    else:
                        messages.success(request, f"Libro guardado correctamente: {guardadas} calificaciones guardadas.")
                        return redirect(reverse("registrar_calificacion") + "?" + urlencode({"curso": curso.pk}))
                else:
                    messages.error(request, "No se guardó ninguna calificación. Revise las filas señaladas; sus valores escritos se conservan.")
    except DatabaseError:
        messages.error(request, "No se pudo completar la operación. No se guardaron cambios. La estructura de la base de datos debe ser revisada por la administración.")
        return render(request, "academico/registrar_calificacion.html", contexto, status=503)
    return render(request, "academico/registrar_calificacion.html", contexto)
