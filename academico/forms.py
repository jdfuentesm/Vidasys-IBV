from typing import ClassVar, cast

from django import forms

from .models import Asistencia, Calificacion, InscripcionCurso, SesionClase


class AsistenciaForm(forms.ModelForm):
    class Meta:
        model = Asistencia
        fields: ClassVar[list[str]] = [
            "inscripcion",
            "sesion",
            "estado_asistencia",
            "observaciones",
        ]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "observaciones": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "inscripcion": forms.Select(attrs={"class": "form-control"}),
            "sesion": forms.Select(attrs={"class": "form-control"}),
            "estado_asistencia": forms.Select(attrs={"class": "form-control"}),
        }
        labels: ClassVar[dict[str, str]] = {
            "inscripcion": "Estudiante (Inscripción)",
            "sesion": "Clase / Sesión",
            "estado_asistencia": "Estado de Asistencia",
            "observaciones": "Observaciones (opcional)",
        }


class SesionExtraordinariaForm(forms.ModelForm):
    # Filtramos para que solo muestre cursos activos
    class Meta:
        model = SesionClase
        fields: ClassVar[list[str]] = [
            "curso",
            "numero_clase",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "motivo_extension",
            "usuario_autoriza",
            "fecha_autorizacion",
            "estado",
        ]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "hora_inicio": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "hora_fin": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"}
            ),
            "fecha_autorizacion": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"}
            ),
            "motivo_extension": forms.Textarea(
                attrs={"rows": 3, "class": "form-control"}
            ),
            "curso": forms.Select(attrs={"class": "form-control"}),
            "numero_clase": forms.Select(attrs={"class": "form-control"}),
            "usuario_autoriza": forms.Select(attrs={"class": "form-control"}),
            "estado": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Forzamos a que el número de clase solo pueda ser 7 u 8 en este formulario
        cast(forms.ChoiceField, self.fields["numero_clase"]).choices = [
            (7, "Clase 7 extraordinaria"),
            (8, "Clase 8 extraordinaria"),
        ]
        self.fields["estado"].initial = "PROGRAMADA"
        # Filtramos los usuarios para que solo muestre a las directoras
        usuario_autoriza = cast(forms.ModelChoiceField, self.fields["usuario_autoriza"])
        if usuario_autoriza.queryset is not None:
            usuario_autoriza.queryset = usuario_autoriza.queryset.filter(
                rol="DIRECTORA"
            )


class CalificacionForm(forms.ModelForm):
    def __init__(self, *args, inscripciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Por defecto no expone estudiantes; la vista proporciona el ámbito autorizado.
        self.fields["inscripcion"].queryset = (
            inscripciones if inscripciones is not None else
            InscripcionCurso.objects.none()
        )
        self.fields["inscripcion"].error_messages["invalid_choice"] = (
            "Seleccione un estudiante inscrito en el curso elegido."
        )
        for campo, limite in Calificacion.LIMITES_COMPONENTES.items():
            self.fields[campo].widget.attrs.update(min="0", max=str(limite), step="0.01")
        self.fields["puntos_extras"].help_text = (
            "Opcional, a consideración del docente. Solo cubre puntaje faltante "
            "en la apreciación, sin superar 100 puntos."
        )
        self.fields["puntos_extras"].required = False

    def clean_puntos_extras(self):
        return self.cleaned_data.get("puntos_extras") or 0

    class Meta:
        model = Calificacion
        fields: ClassVar[list[str]] = [
            "inscripcion",
            "nota_asistencia",
            "nota_uniforme",
            "nota_participacion",
            "nota_companerismo",
            "puntos_extras",
            "tarea_1",
            "examen_1",
            "tarea_2",
            "examen_2",
            "observaciones",
        ]
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "inscripcion": forms.Select(attrs={"class": "form-control"}),
            "nota_asistencia": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "40"}
            ),
            "nota_uniforme": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "20"}
            ),
            "nota_participacion": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "20"}
            ),
            "nota_companerismo": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "20"}
            ),
            "puntos_extras": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "10"}
            ),
            "tarea_1": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "examen_1": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "tarea_2": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "examen_2": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "observaciones": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }


class FilaCalificacionForm(CalificacionForm):
    """Una fila del libro; reutiliza la validación y persistencia de CalificacionForm."""
    revision = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, inscripcion, **kwargs):
        from django.core import signing
        from hashlib import sha256
        import json

        self.inscripcion_libro = inscripcion
        super().__init__(*args, **kwargs)
        self.fields["inscripcion"].disabled = True
        self.fields["inscripcion"].widget = forms.HiddenInput()
        self.initial["inscripcion"] = inscripcion.pk
        self.bloqueada = inscripcion.estado == "REPROBADA_POR_INASISTENCIA"
        self.omitir = False
        # Una nota existente tiene que conservar exactamente su versión al editarla.
        datos = {campo: str(getattr(self.instance, campo)) for campo in self.Meta.fields
                 if campo != "inscripcion"}
        datos.update(pk=self.instance.pk, estado=inscripcion.estado,
                     nota_final=str(self.instance.nota_final))
        digest = sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()
        self.revision_actual = signing.Signer(salt="vidasys-libro").sign(f"{inscripcion.pk}:{digest}")
        self.initial["revision"] = self.revision_actual
        if not self.instance.pk:
            for campo in Calificacion.COMPONENTES:
                self.initial[campo] = None
        for campo in Calificacion.COMPONENTES:
            self.fields[campo].required = False
            self.fields[campo].widget.attrs["aria-label"] = (
                f"{self.fields[campo].label}: {inscripcion.matricula.estudiante}"
            )
        self.fields["observaciones"].widget = forms.TextInput(attrs={
            "aria-label": f"Observaciones: {inscripcion.matricula.estudiante}",
        })
        if self.bloqueada:
            for campo in self.fields.values():
                campo.disabled = True

    @property
    def componentes(self):
        return [self[campo] for campo in Calificacion.COMPONENTES]

    def clean(self):
        from django.utils.crypto import constant_time_compare

        datos = super().clean()
        vacia = not any(self.data.get(self.add_prefix(campo), "").strip()
                        for campo in (*Calificacion.COMPONENTES, "observaciones"))
        self.omitir = self.bloqueada or (not self.instance.pk and vacia)
        if self.omitir:
            return datos
        if not constant_time_compare(datos.get("revision", ""), self.revision_actual):
            raise forms.ValidationError(
                "Esta fila cambió desde que abrió el libro. Recargue y revise la calificación antes de guardar."
            )
        for campo in Calificacion.COMPONENTES:
            if campo != "puntos_extras" and datos.get(campo) is None and campo not in self.errors:
                self.add_error(campo, "Complete esta nota. Use 0 si la evaluación vale cero.")
        return datos

    def _post_clean(self):
        # Una fila nueva vacía no representa una evaluación: no crear un registro con ceros.
        if not self.omitir:
            super()._post_clean()


class FilaAsistenciaForm(AsistenciaForm):
    revision = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, inscripcion, sesion, **kwargs):
        from django.core import signing
        from hashlib import sha256
        import json
        from .asistencia import motivo_bloqueo

        super().__init__(*args, **kwargs)
        self.motivo_bloqueo = motivo_bloqueo(inscripcion, sesion)
        self.omitir = False
        self.fields["inscripcion"].queryset = InscripcionCurso.objects.filter(pk=inscripcion.pk)
        self.fields["sesion"].queryset = SesionClase.objects.filter(pk=sesion.pk)
        for nombre, pk in (("inscripcion", inscripcion.pk), ("sesion", sesion.pk)):
            self.fields[nombre].disabled = True
            self.fields[nombre].widget = forms.HiddenInput()
            self.initial[nombre] = pk
        self.fields["estado_asistencia"].required = False
        self.fields["estado_asistencia"].choices = [("", "Pendiente · sin registrar"), *Asistencia.ESTADOS_ASISTENCIA]
        self.fields["estado_asistencia"].widget.attrs["aria-label"] = f"Asistencia: {inscripcion.matricula.estudiante}"
        self.fields["observaciones"].widget = forms.TextInput(attrs={
            "aria-label": f"Observaciones: {inscripcion.matricula.estudiante}",
            "placeholder": "Observación opcional",
        })
        datos = {
            "inscripcion": inscripcion.pk, "estado_inscripcion": inscripcion.estado,
            "cierre": str(inscripcion.fecha_cierre), "motivo": inscripcion.motivo_cierre,
            "matricula": inscripcion.matricula_id, "estado_matricula": inscripcion.matricula.estado,
            "ciclo_matricula": inscripcion.matricula.ciclo_id, "curso": inscripcion.curso_id,
            "ciclo_curso": inscripcion.curso.ciclo_id, "docente": inscripcion.curso.maestro_id,
            "sesion": sesion.pk, "estado_sesion": sesion.estado, "curso_sesion": sesion.curso_id,
            "fecha_sesion": str(sesion.fecha), "asistencia": self.instance.pk,
            "estado_asistencia": self.instance.estado_asistencia,
            "observaciones": self.instance.observaciones,
        }
        digest = sha256(json.dumps(datos, sort_keys=True).encode()).hexdigest()
        self.revision_actual = signing.Signer(salt="vidasys-asistencia").sign(digest)
        self.initial["revision"] = self.revision_actual
        if self.motivo_bloqueo:
            self.fields["estado_asistencia"].disabled = True
            self.fields["observaciones"].disabled = True

    def clean(self):
        from django.utils.crypto import constant_time_compare

        datos = super().clean()
        if not constant_time_compare(datos.get("revision", ""), self.revision_actual):
            self.omitir = True
            raise forms.ValidationError("Esta fila o su habilitación cambió. Recargue la sesión y revise los datos antes de guardar.")
        if self.motivo_bloqueo:
            self.omitir = True
            for campo in ("estado_asistencia", "observaciones"):
                recibido = self.data.get(self.add_prefix(campo))
                anterior = getattr(self.instance, campo) or ""
                if recibido is not None and recibido != anterior:
                    raise forms.ValidationError(self.motivo_bloqueo)
            return datos
        if not datos.get("estado_asistencia"):
            if self.instance.pk:
                self.add_error("estado_asistencia", "Seleccione un estado. Dejarlo vacío no elimina una asistencia registrada.")
            elif datos.get("observaciones"):
                self.add_error("estado_asistencia", "Seleccione un estado para guardar la observación.")
            self.omitir = True
        return datos

    def _post_clean(self):
        if not self.omitir:
            super()._post_clean()
