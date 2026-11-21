import uuid
from django import forms
from academico.models import Matricula
from .models import Obligacion

PORCENTAJES=[('50','50 %'),('100','100 %')]
CONCEPTOS=[('MATRICULA','Matrícula'),('MENSUALIDAD','Mensualidades')]
ALCANCES=[('VENCIDAS','Vencidas (retroactiva)'),('NO_VENCIDAS','No vencidas'),('AMBAS','Vencidas y no vencidas')]


class MatriculaBecaField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.estudiante} · {obj.ciclo} · Matrícula {obj.numero_matricula}'


class SolicitudBecaForm(forms.Form):
    clave=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    matricula=MatriculaBecaField(queryset=Matricula.objects.none(),label='Estudiante y ciclo (matrícula activa)')
    porcentaje=forms.ChoiceField(choices=PORCENTAJES)
    conceptos=forms.MultipleChoiceField(choices=CONCEPTOS,widget=forms.CheckboxSelectMultiple)
    alcance=forms.ChoiceField(choices=ALCANCES)
    justificacion=forms.CharField(label='Justificación',max_length=4000,widget=forms.Textarea)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['matricula'].queryset=Matricula.objects.filter(estado='ACTIVA').select_related('estudiante','ciclo').order_by('estudiante__apellidos','pk')


class ResolucionBecaForm(forms.Form):
    decision=forms.ChoiceField(choices=[('APROBADA','Aprobar beca'),('RECHAZADA','Rechazar solicitud')])
    porcentaje=forms.ChoiceField(choices=[('','Seleccione'),*PORCENTAJES],required=False)
    conceptos=forms.MultipleChoiceField(choices=CONCEPTOS,required=False,widget=forms.CheckboxSelectMultiple)
    alcance=forms.ChoiceField(choices=[('','Seleccione'),*ALCANCES],required=False)
    obligaciones=forms.ModelMultipleChoiceField(queryset=Obligacion.objects.none(),required=False,widget=forms.CheckboxSelectMultiple)
    observaciones=forms.CharField(label='Observaciones (obligatorias al rechazar)',required=False,max_length=4000,widget=forms.Textarea)
    revision=forms.CharField(required=False,widget=forms.HiddenInput)

    def __init__(self,*args,solicitud,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['obligaciones'].queryset=Obligacion.objects.filter(matricula=solicitud.matricula).select_related('concepto').order_by('fecha_vencimiento','pk')

    def clean(self):
        datos=super().clean()
        if datos.get('decision')=='RECHAZADA':
            if not datos.get('observaciones'):self.add_error('observaciones','Indique la justificación del rechazo.')
        elif datos.get('decision')=='APROBADA':
            for campo in ('porcentaje','conceptos','alcance','obligaciones'):
                if not datos.get(campo):self.add_error(campo,'Seleccione expresamente este campo para aprobar.')
        return datos

    def resolucion(self):
        d=self.cleaned_data
        if d['decision']=='RECHAZADA':return {'observaciones':d['observaciones']}
        return {'porcentaje':d['porcentaje'],'conceptos':d['conceptos'],'alcance':d['alcance'],
                'obligaciones':[o.pk for o in d['obligaciones']],'observaciones':d['observaciones']}
