import uuid
from decimal import Decimal
from django import forms
from django.forms import formset_factory
from academico.models import Estudiante
from .models import Obligacion
from .consultas import importes


class PrepararForm(forms.Form):
    estudiante=forms.ModelChoiceField(queryset=Estudiante.objects.all().order_by('apellidos','pk'))
    cantidad=forms.IntegerField(min_value=1,max_value=100,initial=1,label='Número de cuotas a proponer')


class ObligacionesField(forms.ModelMultipleChoiceField):
    def label_from_instance(self,obj):
        return f'{obj.descripcion} · {obj.fecha_vencimiento} · saldo USD {importes(obj)[2]:.2f}'


class CondicionesForm(forms.Form):
    clave=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    obligaciones=ObligacionesField(queryset=Obligacion.objects.none(),widget=forms.CheckboxSelectMultiple,required=False)
    motivo=forms.CharField(max_length=4000,widget=forms.Textarea,label='Justificación / observaciones',required=False)
    revision=forms.CharField(widget=forms.HiddenInput,required=False)

    def __init__(self,*args,estudiante,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['obligaciones'].queryset=Obligacion.objects.filter(matricula__estudiante=estudiante).exclude(estado='ANULADA').select_related('concepto').order_by('fecha_vencimiento','pk')


class CuotaForm(forms.Form):
    fecha=forms.DateField(widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'),label='Vencimiento')
    monto=forms.DecimalField(max_digits=10,decimal_places=2,min_value=Decimal('.01'),widget=forms.NumberInput(attrs={'step':'.01'}),label='Importe USD')


CuotasFormSet=formset_factory(CuotaForm,extra=0,min_num=1,validate_min=True,max_num=100,validate_max=True,absolute_max=100)


def cuotas_limpias(formset):
    return [{'fecha':str(f.cleaned_data['fecha']),'monto':str(f.cleaned_data['monto'])} for f in formset]


class AbonoForm(forms.Form):
    token=forms.CharField(widget=forms.HiddenInput)
    metodo=forms.ChoiceField(choices=[('EFECTIVO','Efectivo'),('TRANSFERENCIA','Transferencia')])
    referencia=forms.CharField(required=False,max_length=100)

    def __init__(self,*args,resumen,obligaciones,**kwargs):
        super().__init__(*args,**kwargs)
        self.ids_cuotas=[];self.ids_obligaciones=[]
        for fila in resumen['filas']:
            cuota=fila['cuota']
            if cuota.estado=='ANULADA':continue
            self.ids_cuotas.append(cuota.pk)
            self.fields[f'cuota_{cuota.pk}']=forms.DecimalField(required=False,min_value=Decimal('.01'),max_digits=10,decimal_places=2,
                label=f'Abono cuota {cuota.numero_cuota} · vence {cuota.fecha_vencimiento} · saldo USD {fila["saldo"]:.2f}',widget=forms.NumberInput(attrs={'step':'.01'}))
        for o in obligaciones:
            self.ids_obligaciones.append(o.pk)
            self.fields[f'obligacion_{o.pk}']=forms.DecimalField(required=False,min_value=Decimal('.01'),max_digits=10,decimal_places=2,
                label=f'Desglose: {o.descripcion} · {o.fecha_vencimiento} · saldo USD {importes(o)[2]:.2f}',widget=forms.NumberInput(attrs={'step':'.01'}))

    def aplicaciones(self,prefijo,identificadores):
        return [(pk,self.cleaned_data[f'{prefijo}_{pk}']) for pk in identificadores if self.cleaned_data.get(f'{prefijo}_{pk}') is not None]
