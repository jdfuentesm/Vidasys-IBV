import uuid
from decimal import Decimal
from django import forms
from django.utils import timezone
from .models import Donante,SolicitudPadrinazgo
from .aportes import reservada
from .consultas import importes
from .operaciones_forms import FechaForm


class Secciones:
    def secciones(self):
        resultado=[];usados=set()
        for titulo,nombres in self.grupos:
            campos=[self[n] for n in nombres if n in self.fields and not self[n].is_hidden]
            if campos:resultado.append({'titulo':titulo,'campos':campos});usados.update(nombres)
        resto=[f for f in self.visible_fields() if f.name not in usados]
        if resto:resultado.append({'titulo':'Obligaciones e importes (USD)','campos':resto})
        return resultado


class DonanteChoice(forms.ModelChoiceField):
    def label_from_instance(self,o):return o.nombre_completo


class PadrinazgoSelect(forms.Select):
    def create_option(self,name,value,label,selected,index,subindex=None,attrs=None):
        opcion=super().create_option(name,value,label,selected,index,subindex,attrs)
        if getattr(value,'instance',None):opcion['attrs']['data-donante']=value.instance.padrinazgo.donante_id
        return opcion


class PadrinazgoChoice(forms.ModelChoiceField):
    def label_from_instance(self,o):return f'{o.padrinazgo.donante.nombre_completo} · {o.matricula.numero_matricula} · hasta {o.padrinazgo.fecha_fin:%d/%m/%Y}'


class DonanteForm(Secciones,forms.Form):
    grupos=[('Identificación del donante',['tipo','nombre_completo','documento_identidad','es_anonimo','estado']),('Contacto privado',['correo','telefono','pais','direccion']),('Notas internas',['notas'])]
    clave=forms.UUIDField(initial=uuid.uuid4,widget=forms.HiddenInput)
    tipo=forms.ChoiceField(choices=[('PERSONA','Persona natural'),('INSTITUCION','Institución')])
    nombre_completo=forms.CharField(label='Nombre de la persona o institución',max_length=150)
    documento_identidad=forms.CharField(label='Documento (privado)',max_length=50,required=False)
    correo=forms.EmailField(required=False,max_length=150)
    telefono=forms.CharField(label='Teléfono',required=False,max_length=25)
    pais=forms.CharField(label='País',required=False,max_length=80)
    direccion=forms.CharField(label='Dirección',required=False,max_length=4000,widget=forms.Textarea)
    es_anonimo=forms.BooleanField(label='Identificar públicamente como donante anónimo',required=False)
    notas=forms.CharField(label='Notas internas',required=False,max_length=4000,widget=forms.Textarea)
    estado=forms.ChoiceField(choices=[('ACTIVO','Activo'),('INACTIVO','Inactivo')])


class LineasMixin:
    def cargar(self,obligaciones):
        self.obligaciones=list(obligaciones)
        for o in self.obligaciones:
            if getattr(self,'seleccion_porcentaje',False):self.fields[f'seleccionar_{o.pk}']=forms.BooleanField(label=f'Incluir {o.descripcion} en porcentaje',required=False,widget=forms.CheckboxInput(attrs={'data-seleccion':str(o.pk)}))
            self.fields[f'aporte_{o.pk}']=forms.DecimalField(label=f'{o.descripcion} · saldo USD {importes(o)[2]:.2f} · reserva USD {reservada(o):.2f}',required=False,min_value=Decimal('0'),max_digits=10,decimal_places=2,
                widget=forms.NumberInput(attrs={'step':'.01','data-aporte':'1','data-saldo':str(importes(o)[2]-reservada(o))}))
    def asignaciones(self,porcentaje=False):
        return [(o.pk,Decimal('.01') if self.cleaned_data.get('modalidad')=='PORCENTAJE' else self.cleaned_data[f'aporte_{o.pk}']) for o in self.obligaciones if (self.cleaned_data.get(f'seleccionar_{o.pk}') if self.cleaned_data.get('modalidad')=='PORCENTAJE' else (self.cleaned_data.get(f'aporte_{o.pk}') or 0)>0)]


class SolicitudForm(LineasMixin,Secciones,forms.Form):
    grupos=[('Padrino, modalidad y fechas',['donante','inicio','limite','modalidad','porcentaje']),('Motivo institucional',['observaciones'])]
    seleccion_porcentaje=True
    clave=forms.UUIDField(initial=uuid.uuid4,widget=forms.HiddenInput)
    donante=DonanteChoice(queryset=Donante.objects.none())
    inicio=forms.DateField(label='Inicio de la cobertura',initial=timezone.localdate,widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    limite=forms.DateField(label='Fecha límite del aporte (puede superar el fin del ciclo)',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    modalidad=forms.ChoiceField(choices=[('FIJO','Importes fijos por obligación'),('PORCENTAJE','Porcentaje del saldo libre seleccionado')])
    porcentaje=forms.DecimalField(label='Porcentaje (solo modalidad porcentaje)',required=False,min_value=Decimal('.01'),max_value=100,max_digits=5,decimal_places=2)
    observaciones=forms.CharField(label='Motivo y observaciones',max_length=4000,widget=forms.Textarea)
    def __init__(self,*a,obligaciones=(),**k):
        super().__init__(*a,**k);self.fields['donante'].queryset=Donante.objects.filter(estado='ACTIVO').order_by('nombre_completo');self.cargar(obligaciones)

    def clean(self):
        d=super().clean()
        if d.get('modalidad')=='PORCENTAJE' and not d.get('porcentaje'):self.add_error('porcentaje','Indique el porcentaje solicitado.')
        return d


class RecepcionForm(LineasMixin,Secciones,FechaForm):
    grupos=[('Origen y destino',['donante','modalidad','solicitud']),('Dinero recibido',['monto','fecha','metodo','referencia']),('Respaldo y observaciones',['archivo','observaciones'])]
    donante=DonanteChoice(queryset=Donante.objects.none())
    modalidad=forms.ChoiceField(label='Destino del aporte',choices=[('GENERAL','Funcionamiento institucional'),('DIRIGIDA','Obligaciones de este estudiante'),('PADRINAZGO','Recepción de un padrinazgo autorizado')])
    solicitud=PadrinazgoChoice(label='Padrinazgo autorizado (si corresponde)',queryset=SolicitudPadrinazgo.objects.none(),required=False,widget=PadrinazgoSelect)
    monto=forms.DecimalField(label='Dinero efectivamente recibido (USD)',min_value=Decimal('.01'),max_digits=10,decimal_places=2)
    observaciones=forms.CharField(required=False,max_length=4000,widget=forms.Textarea)
    def __init__(self,*a,matricula=None,**k):
        super().__init__(*a,**k);self.fields['donante'].queryset=Donante.objects.filter(estado='ACTIVO').order_by('nombre_completo')
        self.fields['solicitud'].queryset=SolicitudPadrinazgo.objects.filter(matricula=matricula,estado='APROBADA',padrinazgo__estado='ACTIVO').select_related('padrinazgo__donante','matricula') if matricula else SolicitudPadrinazgo.objects.none()
        if not matricula:self.fields['modalidad'].choices=[('GENERAL','Funcionamiento institucional')]
        else:self.fields['modalidad'].choices=[('DIRIGIDA','Obligaciones de este estudiante'),('PADRINAZGO','Recepción de padrinazgo autorizado')]
        self.cargar(matricula.obligaciones.order_by('pk') if matricula else [])


class RevisionForm(Secciones,forms.Form):
    grupos=[('Resolución y motivo',['accion','motivo']),('Condiciones que corresponden a la resolución',['limite','donante','porcentaje']),('Notificación al estudiante',['notificacion'])]
    clave=forms.UUIDField(initial=uuid.uuid4,widget=forms.HiddenInput)
    accion=forms.ChoiceField(label='Resolución',choices=[('PRORROGA','Ampliar la fecha límite'),('SUSTITUCION','Sustituir padrino'),('CANCELACION','Cancelar cobertura pendiente'),('BECA','Convertir el pendiente en beca F2')])
    motivo=forms.CharField(max_length=4000,widget=forms.Textarea)
    limite=forms.DateField(label='Nueva fecha límite (para prórroga)',required=False,widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    donante=DonanteChoice(label='Nuevo padrino (para sustitución)',queryset=Donante.objects.filter(estado='ACTIVO'),required=False)
    porcentaje=forms.ChoiceField(label='Beca (solo conversión)',required=False,choices=[('','No corresponde'),('50','50 %'),('100','100 %')])
    notificacion=forms.CharField(label='Mensaje al estudiante al cancelar/convertir (sin datos privados del donante)',max_length=1000,required=False,widget=forms.Textarea)
    revision=forms.CharField(required=False,widget=forms.HiddenInput)

    def clean(self):
        d=super().clean();accion=d.get('accion')
        if accion=='PRORROGA' and not d.get('limite'):self.add_error('limite','Indique la nueva fecha límite.')
        if accion=='SUSTITUCION' and not d.get('donante'):self.add_error('donante','Seleccione el nuevo padrino.')
        if accion=='BECA' and not d.get('porcentaje'):self.add_error('porcentaje','Seleccione la beca del 50 % o del 100 %.')
        if accion in ('BECA','CANCELACION') and not d.get('notificacion'):self.add_error('notificacion','Escriba el mensaje que verá el estudiante.')
        return d
