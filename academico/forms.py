from django import forms

from .models import Asistencia


class AsistenciaForm(forms.ModelForm):
    class Meta:
        model = Asistencia
        fields = ["inscripcion", "sesion", "estado_asistencia", "observaciones"]
        widgets = {
            "observaciones": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "inscripcion": forms.Select(attrs={"class": "form-control"}),
            "sesion": forms.Select(attrs={"class": "form-control"}),
            "estado_asistencia": forms.Select(attrs={"class": "form-control"}),
        }
        labels = {
            "inscripcion": "Estudiante (Inscripción)",
            "sesion": "Clase / Sesión",
            "estado_asistencia": "Estado de Asistencia",
            "observaciones": "Observaciones (opcional)",
        }
