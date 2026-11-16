from django import forms
from django.contrib.auth.password_validation import validate_password, password_validators_help_text_html

from academico.models import Estudiante
from .models import Usuario


class CuentaForm(forms.ModelForm):
    correo_acceso = forms.EmailField(max_length=150, label='Correo de acceso')

    class Meta:
        model = Usuario
        fields = ('numero_usuario', 'correo_acceso', 'rol', 'estado_cuenta')
        labels = {'numero_usuario': 'Número de usuario', 'estado_cuenta': 'Estado de cuenta'}


class AltaCuentaForm(CuentaForm):
    password1 = forms.CharField(label='Contraseña temporal', strip=False, widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}), help_text=password_validators_help_text_html())
    password2 = forms.CharField(label='Confirmar contraseña temporal', strip=False, widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}))

    def clean(self):
        datos = super().clean()
        if datos.get('password1') and datos.get('password2'):
            if datos['password1'] != datos['password2']:
                self.add_error('password2', 'Las contraseñas no coinciden.')
            else:
                prueba = Usuario(**{k:datos[k] for k in self.Meta.fields if k in datos})
                validate_password(datos['password1'], prueba)
        return datos


class VinculoEstudianteForm(forms.Form):
    estudiante = forms.ModelChoiceField(queryset=Estudiante.objects.none(), label='Expediente verificado')
    confirmar = forms.BooleanField(label='He verificado que esta cuenta corresponde a la persona del expediente seleccionado.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Selección explícita, nunca coincidencias por nombre o correo.
        self.fields['estudiante'].queryset = Estudiante.objects.order_by('apellidos', 'nombres', 'pk')
