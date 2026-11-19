import uuid
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from .models import SesionClase, SolicitudAcademica
from .solicitudes import solicitar, decidir, bloqueo_cancelacion


class SolicitudForm(forms.Form):
    clave = forms.UUIDField(widget=forms.HiddenInput)
    motivo = forms.CharField(label="Motivo de la cancelación", max_length=4000, widget=forms.Textarea)


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(label="Decisión", choices=[("APROBADA", "Aprobar cancelación"), ("RECHAZADA", "Rechazar solicitud")])
    motivo = forms.CharField(label="Motivo de la decisión (obligatorio al rechazar)", required=False, max_length=4000, widget=forms.Textarea)

    def clean(self):
        datos = super().clean()
        if datos.get("decision") == "RECHAZADA" and not datos.get("motivo"):
            self.add_error("motivo", "Indique el motivo del rechazo.")
        return datos


def error_form(form, error):
    form.add_error(None, " ".join(error.messages) if isinstance(error, ValidationError)
                   else "No se pudo guardar; no se aplicó ningún cambio. Recargue e intente nuevamente.")


@login_required
def nueva_solicitud(request, sesion_id):
    if not request.user.is_active or request.user.rol != "MAESTRO":
        return HttpResponseForbidden("Solo el maestro del curso puede solicitar una cancelación.")
    sesion = get_object_or_404(SesionClase.objects.select_related("curso"), pk=sesion_id, curso__maestro__usuario=request.user)
    form = SolicitudForm(request.POST if request.method == "POST" else None, initial={"clave": uuid.uuid4()})
    bloqueo = bloqueo_cancelacion(sesion.curso, sesion)
    if request.method == "POST" and form.is_valid():
        try:
            solicitud = solicitar(sesion_id=sesion.pk, usuario=request.user, **form.cleaned_data)
            messages.success(request, "Solicitud registrada. La sesión conserva su estado hasta la aprobación de Dirección.")
            return redirect("solicitud_academica", solicitud_id=solicitud.pk)
        except (ValidationError, DatabaseError) as error:
            error_form(form, error)
    return render(request, "academico/solicitud_nueva.html", {"sesion": sesion, "form": form, "bloqueo": bloqueo})


def ambito(usuario):
    qs = SolicitudAcademica.objects.select_related("curso", "sesion", "solicitante", "directora")
    if usuario.rol == "MAESTRO":
        qs = qs.filter(solicitante=usuario, curso__maestro__usuario=usuario)
    return qs


@login_required
def bandeja(request):
    if not request.user.is_active or request.user.rol not in ("MAESTRO", "DIRECTORA"):
        return HttpResponseForbidden("Esta bandeja corresponde a maestros y Dirección.")
    qs = ambito(request.user)
    return render(request, "academico/solicitudes.html", {"pendientes": qs.filter(estado="PENDIENTE"), "resueltas": qs.exclude(estado="PENDIENTE")})


@login_required
def detalle(request, solicitud_id):
    if not request.user.is_active or request.user.rol not in ("MAESTRO", "DIRECTORA"):
        return HttpResponseForbidden("No tiene acceso a solicitudes académicas.")
    solicitud = get_object_or_404(ambito(request.user), pk=solicitud_id)
    form = DecisionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if request.user.rol != "DIRECTORA":
            return HttpResponseForbidden("Solo Dirección puede resolver solicitudes.")
        if form.is_valid():
            try:
                decidir(solicitud_id=solicitud.pk, usuario=request.user, **form.cleaned_data)
                messages.success(request, "Decisión registrada. Consulte el resultado y el historial.")
                return redirect("solicitud_academica", solicitud_id=solicitud.pk)
            except (ValidationError, DatabaseError) as error:
                error_form(form, error)
    return render(request, "academico/solicitud_detalle.html", {"solicitud": solicitud, "form": form})
