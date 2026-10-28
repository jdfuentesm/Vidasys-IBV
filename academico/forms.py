from typing import ClassVar, cast

from django import forms

from .models import Asistencia, Calificacion, SesionClase


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
