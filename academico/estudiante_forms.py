"""Datos personales; no administra cuentas, docentes ni historial académico."""
from django import forms
from django.utils import timezone

from .models import Estudiante


class EstudianteForm(forms.ModelForm):
    class Meta:
        model = Estudiante
        fields = ('codigo_estudiante', 'nombres', 'apellidos', 'fecha_nacimiento',
                  'telefono', 'correo', 'direccion', 'fecha_ingreso', 'estado')
        labels = {'codigo_estudiante': 'Código de estudiante', 'fecha_nacimiento': 'Fecha de nacimiento',
                  'telefono': 'Teléfono', 'correo': 'Correo electrónico', 'direccion': 'Dirección',
                  'fecha_ingreso': 'Fecha de ingreso'}
        widgets = {
            'fecha_nacimiento': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'fecha_ingreso': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'direccion': forms.Textarea(attrs={'rows': 3}),
        }
        error_messages = {'codigo_estudiante': {'unique': 'Ya existe un estudiante con este código.'}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estado'].help_text = 'Estado del registro personal; no cambia matrículas ni inscripciones.'
        if self.instance.pk:
            for name in ('codigo_estudiante', 'fecha_ingreso'):
                self.fields[name].disabled = True
                self.fields[name].help_text = 'Se conserva para proteger la identificación y el historial.'
        else:
            self.initial.setdefault('fecha_ingreso', timezone.localdate())
            self.initial.setdefault('estado', 'ACTIVO')

    def clean_codigo_estudiante(self):
        codigo = self.cleaned_data['codigo_estudiante'].strip()
        if Estudiante.objects.filter(codigo_estudiante__iexact=codigo).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya existe un estudiante con este código. Busque su expediente antes de registrar otro.')
        return codigo

    def clean(self):
        datos = super().clean()
        nacimiento, ingreso = datos.get('fecha_nacimiento'), datos.get('fecha_ingreso')
        if nacimiento and nacimiento > timezone.localdate():
            self.add_error('fecha_nacimiento', 'La fecha de nacimiento no puede ser futura.')
        if nacimiento and ingreso and nacimiento > ingreso:
            self.add_error('fecha_nacimiento', 'La fecha de nacimiento debe ser anterior o igual a la fecha de ingreso.')
        return datos
