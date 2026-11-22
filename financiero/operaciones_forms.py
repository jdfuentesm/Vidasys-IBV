import uuid
from decimal import Decimal
from django import forms
from django.utils import timezone
from .models import CategoriaIngreso,CategoriaEgreso


class BaseForm(forms.Form):
    clave=forms.UUIDField(initial=uuid.uuid4,widget=forms.HiddenInput)
    archivo=forms.FileField(label='Comprobante opcional: PDF, PNG o JPEG (máximo 5 MiB)',required=False,
        widget=forms.ClearableFileInput(attrs={'accept':'.pdf,.png,.jpg,.jpeg'}))


class FechaForm(BaseForm):
    metodo=forms.ChoiceField(label='Método de pago',choices=[('EFECTIVO','Efectivo'),('TRANSFERENCIA','Transferencia')])
    referencia=forms.CharField(required=False,max_length=100)
    fecha=forms.DateTimeField(label='Fecha efectiva',initial=timezone.now,
        widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M',attrs={'type':'datetime-local'}))


class IngresoForm(FechaForm):
    categoria=forms.ModelChoiceField(queryset=CategoriaIngreso.objects.none())
    concepto=forms.CharField(max_length=200)
    origen=forms.CharField(label='Persona o entidad de origen',max_length=200,required=False)
    monto=forms.DecimalField(label='Importe (USD)',min_value=Decimal('.01'),max_digits=10,decimal_places=2)
    observaciones=forms.CharField(required=False,max_length=4000,widget=forms.Textarea)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['categoria'].queryset=(CategoriaIngreso.objects.all() if self.is_bound else CategoriaIngreso.objects.filter(estado='ACTIVO')).order_by('nombre')


class EgresoForm(BaseForm):
    categoria=forms.ModelChoiceField(queryset=CategoriaEgreso.objects.none())
    concepto=forms.CharField(max_length=200)
    beneficiario=forms.CharField(label='Beneficiario o proveedor',max_length=200)
    monto=forms.DecimalField(label='Importe solicitado (USD)',min_value=Decimal('.01'),max_digits=10,decimal_places=2)
    justificacion=forms.CharField(max_length=4000,widget=forms.Textarea)
    observaciones=forms.CharField(required=False,max_length=4000,widget=forms.Textarea)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['categoria'].queryset=(CategoriaEgreso.objects.all() if self.is_bound else CategoriaEgreso.objects.filter(estado='ACTIVO')).order_by('nombre')


class ResolucionForm(forms.Form):
    decision=forms.ChoiceField(choices=[('APROBADA','Aprobar'),('RECHAZADA','Rechazar')])
    resolucion=forms.CharField(label='Observaciones (obligatorias al rechazar)',required=False,max_length=4000,widget=forms.Textarea)
    revision=forms.CharField(required=False,widget=forms.HiddenInput)


class AnularForm(forms.Form):
    clave=forms.UUIDField(initial=uuid.uuid4,widget=forms.HiddenInput)
    motivo=forms.CharField(max_length=4000,widget=forms.Textarea)


class CategoriaForm(forms.Form):
    tipo=forms.ChoiceField(choices=[('INGRESO','Ingreso administrativo'),('EGRESO','Egreso')])
    nombre=forms.CharField(max_length=100,required=False)
    descripcion=forms.CharField(max_length=4000,required=False,widget=forms.Textarea)
    categoria_id=forms.IntegerField(min_value=1,required=False,widget=forms.HiddenInput)
    estado=forms.ChoiceField(choices=[('ACTIVO','Activa'),('INACTIVO','Inactiva')])


class FiltrosForm(forms.Form):
    desde=forms.DateField(required=False,widget=forms.DateInput(attrs={'type':'date'}))
    hasta=forms.DateField(required=False,widget=forms.DateInput(attrs={'type':'date'}))
    tipo=forms.ChoiceField(required=False,choices=[('','Ingresos y egresos'),('INGRESO','Ingresos'),('EGRESO','Egresos')])
    estado=forms.ChoiceField(required=False,choices=[('','Todos'),('REGISTRADO','Ingreso registrado'),('PENDIENTE','Egreso pendiente de autorización'),('APROBADA','Autorizado pendiente de desembolso'),('RECHAZADA','Egreso rechazado'),('DESEMBOLSADO','Egreso desembolsado'),('ANULADO','Movimiento anulado')])
    metodo=forms.ChoiceField(required=False,choices=[('','Todos'),('EFECTIVO','Efectivo'),('TRANSFERENCIA','Transferencia')])
    categoria=forms.CharField(label='Categoría (nombre)',required=False,max_length=100)
    operador=forms.IntegerField(label='ID de operador',required=False,min_value=1,max_value=9223372036854775807)

    def clean(self):
        d=super().clean()
        if d.get('desde') and d.get('hasta') and d['desde']>d['hasta']:raise forms.ValidationError('Rango de fechas inválido.')
        return d
