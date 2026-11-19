import uuid
from django import forms
from django.core import signing
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from .models import SesionClase, SolicitudAcademica, InscripcionCurso, Calificacion
from .correcciones import validar_destino, propuesta_nota, firma_nota, solicitar_correccion
from .solicitudes import solicitar, decidir, bloqueo_cancelacion


class SolicitudForm(forms.Form):
    clave = forms.UUIDField(widget=forms.HiddenInput)
    motivo = forms.CharField(label="Motivo de la cancelación", max_length=4000, widget=forms.Textarea)


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(label="Decisión", choices=[("APROBADA", "Aprobar solicitud"), ("RECHAZADA", "Rechazar solicitud")])
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
    qs = SolicitudAcademica.objects.select_related("curso", "sesion", "solicitante", "directora", "inscripcion__matricula__estudiante")
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
    comparacion = []
    nota_vigente = None
    if solicitud.tipo == 'CORRECCION_CALIFICACION':
        nota_vigente = Calificacion.objects.filter(inscripcion_id=solicitud.inscripcion_id).first()
        comparacion = [{'nombre': Calificacion._meta.get_field(c).verbose_name,
                        'anterior': solicitud.anteriores.get('calificacion', {}).get(c),
                        'propuesto': solicitud.propuestos.get('componentes', {}).get(c)}
                       for c in Calificacion.COMPONENTES]
    return render(request, "academico/solicitud_detalle.html", {"solicitud": solicitud, "form": form, "comparacion": comparacion, "nota_vigente": nota_vigente})


class CorreccionForm(forms.Form):
    confirmacion = forms.CharField(required=False, widget=forms.HiddenInput)
    clave = forms.UUIDField(widget=forms.HiddenInput)
    revision = forms.CharField(widget=forms.HiddenInput)
    motivo = forms.CharField(label="Motivo de la corrección", max_length=4000, widget=forms.Textarea)

    def __init__(self, *args, nota=None, validar_propuesta=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.nota = nota
        self.validar_propuesta = validar_propuesta
        for campo, limite in Calificacion.LIMITES_COMPONENTES.items():
            self.fields[campo] = forms.DecimalField(label=Calificacion._meta.get_field(campo).verbose_name,
                min_value=0, max_value=limite, max_digits=5, decimal_places=2,
                initial=getattr(nota, campo) if nota else None,
                widget=forms.NumberInput(attrs={'step': '0.01'}))

    def clean(self):
        datos = super().clean()
        if self.validar_propuesta and self.nota and all(c in datos for c in Calificacion.COMPONENTES):
            self.propuesta = propuesta_nota(self.nota, {c: datos[c] for c in Calificacion.COMPONENTES})
        return datos


@login_required
def nueva_correccion(request, inscripcion_id):
    if not request.user.is_active or request.user.rol != 'MAESTRO':
        return HttpResponseForbidden('Solo el docente actual puede solicitar una corrección.')
    inscripcion = get_object_or_404(InscripcionCurso.objects.select_related('curso__maestro',
        'curso__ciclo', 'curso__materia', 'matricula__estudiante'), pk=inscripcion_id,
        curso__maestro__usuario=request.user)
    nota = Calificacion.objects.filter(inscripcion=inscripcion).first()
    previa = None
    if request.method == 'POST' and request.POST.get('accion') == 'enviar':
        try:
            clave = forms.UUIDField().clean(request.POST.get('clave'))
            previa = SolicitudAcademica.objects.filter(clave=clave).first()
        except ValidationError:
            pass  # El formulario informa la clave inválida sin consultar otras solicitudes.
    pendiente = SolicitudAcademica.objects.filter(tipo='CORRECCION_CALIFICACION',
        inscripcion=inscripcion, estado='PENDIENTE').first()
    bloqueo = ''
    try:
        validar_destino(inscripcion.curso, inscripcion, nota)
    except ValidationError as error:
        bloqueo = ' '.join(error.messages)
    if pendiente:
        bloqueo = 'Ya existe una corrección pendiente para esta inscripción. Debe resolverse antes de preparar otra propuesta.'
    pendiente_visible = pendiente if pendiente and pendiente.solicitante_id == request.user.pk else None
    form = CorreccionForm(request.POST if request.method == 'POST' else None, nota=nota,
        validar_propuesta=previa is None and pendiente is None,
        initial={'clave': uuid.uuid4(), 'revision': firma_nota(inscripcion.curso, inscripcion, nota) if nota else ''})
    comparacion = []
    propuesta = None
    # Reconocer un reenvío no es una propuesta nueva: conservar permisos y verificar
    # UUID/destino/autor/componentes en el servicio antes de mostrar su resolución.
    if request.method == 'POST' and (previa is not None or not bloqueo) and form.is_valid():
        propuesta = previa.propuestos if previa is not None else form.propuesta
        comparacion = [{'nombre': Calificacion._meta.get_field(c).verbose_name,
                        'anterior': getattr(nota, c) if nota else None,
                        'propuesto': propuesta.get('componentes', {}).get(c)}
                       for c in Calificacion.COMPONENTES]
        contenido = {'propuesta': propuesta, 'revision': form.cleaned_data['revision'],
                     'motivo': form.cleaned_data['motivo']}
        if request.POST.get('accion') == 'enviar':
            try:
                try:
                    confirmado = signing.loads(form.cleaned_data.get('confirmacion', ''), salt='vidasys-confirmar-nota')
                except signing.BadSignature:
                    raise ValidationError('Compare nuevamente la propuesta antes de enviar.')
                if confirmado != contenido:
                    raise ValidationError('La propuesta cambió. Compare nuevamente antes de enviarla.')
                datos = form.cleaned_data
                solicitud = solicitar_correccion(inscripcion_id=inscripcion.pk, usuario=request.user,
                    motivo=datos['motivo'], clave=datos['clave'], revision=datos['revision'],
                    componentes={c: datos[c] for c in Calificacion.COMPONENTES})
                if previa is not None:
                    messages.success(request, 'Solicitud ya registrada. Estado: ' + solicitud.get_estado_display() + '.')
                else:
                    messages.success(request, 'Corrección solicitada. La nota definitiva sigue vigente hasta la aprobación de Dirección.')
                return redirect('solicitud_academica', solicitud_id=solicitud.pk)
            except (ValidationError, DatabaseError) as error:
                error_form(form, error)
        if previa is None:
            form.data = form.data.copy()
            form.data['confirmacion'] = signing.dumps(contenido, salt='vidasys-confirmar-nota')
        else:
            # No devolver los valores de una solicitud localizada solo por UUID:
            # un reenvío inválido nunca muestra datos ni enlaces de esa solicitud.
            comparacion = []
            propuesta = None
    return render(request, 'academico/correccion_nueva.html', {'inscripcion': inscripcion,
        'nota': nota, 'form': form, 'bloqueo': bloqueo, 'comparacion': comparacion,
        'propuesta': propuesta, 'solicitud_pendiente': pendiente_visible})
