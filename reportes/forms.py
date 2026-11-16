from django import forms
from academico.models import CicloAcademico, Curso, Estudiante, InscripcionCurso


class FiltrosReporteForm(forms.Form):
    ciclo=forms.ModelChoiceField(queryset=CicloAcademico.objects.none(),required=False,label='Ciclo académico',empty_label='Todos los ciclos')
    curso=forms.ModelChoiceField(queryset=Curso.objects.none(),required=False,empty_label='Todos los cursos')
    estudiante=forms.ModelChoiceField(queryset=Estudiante.objects.none(),required=False,empty_label='Todos los estudiantes')
    desde=forms.DateField(required=False,widget=forms.DateInput(attrs={'type':'date'}),label='Desde')
    hasta=forms.DateField(required=False,widget=forms.DateInput(attrs={'type':'date'}),label='Hasta')

    def __init__(self,*args,usuario,**kwargs):
        super().__init__(*args,**kwargs)
        cursos=Curso.objects.select_related('materia','ciclo').order_by('-ciclo__anio','materia__nombre','pk')
        estudiantes=Estudiante.objects.order_by('apellidos','nombres','pk')
        ciclos=CicloAcademico.objects.order_by('-anio','numero_ciclo','pk')
        if usuario.rol=='MAESTRO':
            cursos=cursos.filter(maestro__usuario=usuario)
            ciclos=ciclos.filter(pk__in=cursos.values('ciclo_id'))
            estudiantes=estudiantes.filter(pk__in=InscripcionCurso.objects.filter(curso__in=cursos).values('matricula__estudiante_id'))
        self.fields['curso'].queryset=cursos
        self.fields['ciclo'].queryset=ciclos
        self.fields['estudiante'].queryset=estudiantes

    def clean(self):
        datos=super().clean()
        if datos.get('desde') and datos.get('hasta') and datos['desde']>datos['hasta']:
            raise forms.ValidationError('La fecha inicial no puede ser posterior a la fecha final.')
        if datos.get('curso') and datos.get('ciclo') and datos['curso'].ciclo_id!=datos['ciclo'].pk:
            raise forms.ValidationError('El curso seleccionado no pertenece al ciclo indicado.')
        return datos
