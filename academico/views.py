from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from .forms import FilaAsistenciaForm, FilaCalificacionForm
from .presentacion_docente import presentar_libro, presentar_asistencia
from .flujo_views import autorizar_clase_extraordinaria
from .models import Asistencia, Calificacion, Curso, Estudiante, InscripcionCurso, Maestro, Matricula, SesionClase


@never_cache
@login_required
@require_safe
def probar_conexion(request):
    if not request.user.is_active or request.user.rol not in ('SECRETARIA', 'DIRECTORA', 'ADMINISTRADOR'):
        return HttpResponseForbidden('La comprobación de conexión requiere un rol administrativo autorizado.')
    # Diagnóstico mínimo: no expone información personal ni interpreta datos como HTML.
    try:
        total = Estudiante.objects.count()
    except DatabaseError:
        respuesta = HttpResponse('No se pudo verificar la conexión.', status=503, content_type='text/plain; charset=utf-8')
    else:
        respuesta = HttpResponse(f'Conexión verificada. Total de estudiantes: {total}.', content_type='text/plain; charset=utf-8')
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@login_required
def registrar_asistencia(request):
    if not request.user.is_active or request.user.rol != "MAESTRO":
        return HttpResponseForbidden("Solo un docente con cuenta activa puede registrar asistencia.")
    contexto = {"cursos": [], "sesiones": [], "curso": None, "sesion": None, "filas": []}
    datos = request.POST if request.method == "POST" else request.GET

    def identificador(nombre):
        valor = datos.get(nombre, "")
        if valor and (not valor.isascii() or not valor.isdecimal() or len(valor) > 18):
            raise ValidationError("Identificador de curso o sesión inválido.")
        return valor

    try:
        curso_id, sesion_id = identificador("curso"), identificador("sesion")
        cursos = Curso.objects.filter(maestro__usuario=request.user).select_related("materia", "ciclo", "maestro")
        contexto["cursos"] = list(cursos)
        if not curso_id:
            if request.method == "POST":
                messages.error(request, "Seleccione un curso y una sesión antes de guardar.")
            return presentar_asistencia(request, contexto)
        with transaction.atomic():
            seleccion = cursos
            if request.method == "POST":
                # No hacer FOR UPDATE sobre joins; bloquear solo la tabla principal.
                seleccion = Curso.objects.filter(maestro__usuario=request.user).select_for_update(of=("self",))
            curso = get_object_or_404(seleccion, pk=curso_id)
            if request.method == "POST":
                get_object_or_404(Maestro.objects.select_for_update(), pk=curso.maestro_id, usuario=request.user)
            contexto["curso"] = curso
            if request.method == "POST" and curso.estado in ("FINALIZADO", "CANCELADO"):
                return HttpResponseForbidden("Curso cerrado: asistencia solo para consulta. Solicite revisión de Dirección.")
            contexto["sesiones"] = list(SesionClase.objects.filter(curso=curso).order_by("numero_clase"))
            if not sesion_id:
                if request.method == "POST":
                    messages.error(request, "Seleccione una sesión existente antes de guardar.")
                return presentar_asistencia(request, contexto)
            sesiones = SesionClase.objects.filter(curso=curso)
            if request.method == "POST":
                sesiones = sesiones.select_for_update()
            sesion = get_object_or_404(sesiones, pk=sesion_id)
            contexto["sesion"] = sesion
            if request.method == "POST":
                # Bloquear primero matrículas y luego inscripciones en orden estable.
                matriculas = InscripcionCurso.objects.filter(curso=curso).values_list("matricula_id", flat=True)
                list(Matricula.objects.filter(pk__in=matriculas).order_by("pk").select_for_update())
                list(InscripcionCurso.objects.filter(curso=curso).order_by("pk").select_for_update())
            habilitadas = Q(estado="CURSANDO", matricula__estado="ACTIVA", matricula__ciclo_id=curso.ciclo_id)
            historicas = Q(asistencias__sesion=sesion)
            inscripciones = list(InscripcionCurso.objects.filter(habilitadas | historicas, curso=curso).select_related(
                "matricula__estudiante", "curso__ciclo"
            ).distinct().order_by("pk"))
            if request.method == "POST":
                enviados = datos.getlist("inscripciones")
                if len(enviados) != len(inscripciones) or set(enviados) != {str(i.pk) for i in inscripciones}:
                    return HttpResponseForbidden("La lista de estudiantes o su habilitación cambió. Recargue la sesión antes de guardar.")
                if sesion.estado not in ("PROGRAMADA", "IMPARTIDA"):
                    return HttpResponseForbidden("No se permite registrar en sesiones suspendidas o canceladas.")
            registros = {a.inscripcion_id: a for a in Asistencia.objects.filter(sesion=sesion, inscripcion__curso=curso)}
            ausencias = dict(Asistencia.objects.filter(inscripcion__curso=curso, estado_asistencia="AUSENTE_INJUSTIFICADA")
                            .values("inscripcion_id").annotate(total=Count("pk")).values_list("inscripcion_id", "total"))
            for inscripcion in inscripciones:
                registro = registros.get(inscripcion.pk) or Asistencia(inscripcion=inscripcion, sesion=sesion)
                registro.inscripcion = inscripcion
                registro.sesion = sesion
                form = FilaAsistenciaForm(datos if request.method == "POST" else None,
                    inscripcion=inscripcion, sesion=sesion, instance=registro, prefix=f"asistencia-{inscripcion.pk}")
                contexto["filas"].append({"inscripcion": inscripcion, "form": form,
                    "ausencias": ausencias.get(inscripcion.pk, 0), "registro": registros.get(inscripcion.pk)})
            if request.method == "POST":
                validas = [fila["form"].is_valid() for fila in contexto["filas"]]
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
                        messages.error(request, "No se guardó ninguna asistencia. " + " ".join(error.messages))
                    except IntegrityError:
                        messages.error(request, "No se guardó ninguna asistencia. Otra persona pudo registrar cambios; recargue la sesión.")
                    else:
                        messages.success(request, f"Asistencia guardada correctamente: {guardadas} registros guardados.")
                        return redirect(reverse("registrar_asistencia") + "?" + urlencode({"curso": curso.pk, "sesion": sesion.pk}))
                else:
                    messages.error(request, "No se guardó ninguna asistencia. Revise las filas señaladas; los valores escritos se conservan.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return presentar_asistencia(request, contexto, status=400)
    except DatabaseError:
        messages.error(request, "No se pudo completar la operación. No se guardaron cambios; contacte a la administración para revisar la base de datos.")
        return presentar_asistencia(request, contexto, status=503)
    return presentar_asistencia(request, contexto)


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
            return presentar_libro(request, contexto)
        if not curso_id.isascii() or not curso_id.isdecimal() or len(curso_id) > 18:
            return HttpResponseForbidden("El curso seleccionado no está disponible.")
        curso = get_object_or_404(cursos, pk=curso_id)
        contexto["curso"] = curso
        if request.method == "POST" and curso.estado != "ACTIVO":
            return HttpResponseForbidden("Curso no activo: calificaciones solo para consulta. Solicite revisión de Dirección.")
        # El bloqueo y el guardado completo comparten transacción. Nunca cambia el esquema.
        with transaction.atomic():
            if request.method == "POST":
                curso = get_object_or_404(Curso.objects.select_for_update(), pk=curso.pk)
                get_object_or_404(Maestro.objects.select_for_update(), pk=curso.maestro_id, usuario=request.user)
                if curso.estado != "ACTIVO":
                    return HttpResponseForbidden("El curso dejó de estar activo. Recargue el libro.")
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
                        estado = (form.motivo_bloqueo if form.bloqueada else
                                  "Revise esta fila" if not valida else
                                  "Provisional · pendiente de cierre")
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
        return presentar_libro(request, contexto, status=503)
    return presentar_libro(request, contexto)
