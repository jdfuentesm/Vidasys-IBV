"""Formularios del flujo integrado; fechas y frecuencia siempre explícitas."""
from django import forms
from django.utils import timezone

from .forms import SesionExtraordinariaForm
from .models import CicloAcademico, Curso, Estudiante, Matricula


class MatriculaSecretariaForm(forms.Form):
    estudiante = forms.ModelChoiceField(queryset=Estudiante.objects.none())
    ciclo = forms.ModelChoiceField(queryset=CicloAcademico.objects.none(), label='Ciclo académico')
    numero_matricula = forms.CharField(max_length=30, label='Número de matrícula')
    fecha_matricula = forms.DateField(widget=forms.DateInput(attrs={'type':'date'}), label='Fecha de matrícula')
    observaciones = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows':2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estudiante'].queryset = Estudiante.objects.order_by('apellidos','nombres')
        self.fields['ciclo'].queryset = CicloAcademico.objects.order_by('-anio','numero_ciclo')


class MatriculaAutomaticaAdminForm(forms.ModelForm):
    class Meta:
        model = Matricula
        fields = '__all__'

    def clean(self):
        from .flujo import cursos_del_ciclo
        datos = super().clean()
        if not self.instance.pk and datos.get('estado') == 'ACTIVA' and datos.get('ciclo'):
            cursos_del_ciclo(datos['ciclo'])
        return datos


class PropuestaCalendarioForm(forms.Form):
    fecha_inicial = forms.DateField(widget=forms.DateInput(attrs={'type':'date'}))
    frecuencia = forms.ChoiceField(choices=[('', 'Seleccione la frecuencia'), ('semanal','Semanal (7 días)'),
        ('quincenal','Quincenal (14 días)'), ('personalizada','Personalizada: intervalo en días')])
    intervalo_dias = forms.IntegerField(required=False, min_value=1, label='Intervalo personalizado (días)')
    hora_inicio = forms.TimeField(widget=forms.TimeInput(attrs={'type':'time'}))
    duracion_minutos = forms.IntegerField(min_value=1, label='Duración (minutos)')

    def clean(self):
        datos = super().clean()
        if datos.get('frecuencia') == 'personalizada' and not datos.get('intervalo_dias'):
            self.add_error('intervalo_dias', 'Indique el intervalo personalizado; no se asumirá una frecuencia.')
        return datos


class SesionPropuestaForm(forms.Form):
    numero_clase = forms.IntegerField(min_value=1, max_value=6, widget=forms.HiddenInput)
    fecha = forms.DateField(widget=forms.DateInput(attrs={'type':'date'}, format='%Y-%m-%d'))
    hora_inicio = forms.TimeField(widget=forms.TimeInput(attrs={'type':'time'}, format='%H:%M'))
    hora_fin = forms.TimeField(widget=forms.TimeInput(attrs={'type':'time'}, format='%H:%M'))

    def __init__(self, *args, numero, existente=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['numero_clase'].disabled = True
        self.initial['numero_clase'] = numero
        self.existente = existente
        if existente:
            for field in self.fields.values():
                field.disabled = True

    def clean(self):
        datos = super().clean()
        if datos.get('hora_inicio') and datos.get('hora_fin') and datos['hora_fin'] <= datos['hora_inicio']:
            self.add_error('hora_fin','La hora final debe ser posterior a la inicial.')
        return datos


class ExtraordinariaDireccionForm(SesionExtraordinariaForm):
    class Meta(SesionExtraordinariaForm.Meta):
        fields = [f for f in SesionExtraordinariaForm.Meta.fields
                  if f not in ('usuario_autoriza','fecha_autorizacion')]

    def __init__(self, *args, usuario, **kwargs):
        # El inicializador heredado busca un selector de autorizante; esta variante
        # lo elimina deliberadamente y vincula la autorización a la sesión.
        forms.ModelForm.__init__(self, *args, **kwargs)
        self.fields['numero_clase'].choices = [(7, 'Clase 7 extraordinaria'), (8, 'Clase 8 extraordinaria')]
        self.fields['estado'].initial = 'PROGRAMADA'
        self.instance.usuario_autoriza = usuario
        self.instance.fecha_autorizacion = timezone.now()
        self.fields['curso'].queryset = Curso.objects.filter(estado__in=('PROGRAMADO','ACTIVO'))
