from django import forms
from django.utils import timezone
from academico.models import CicloAcademico,Estudiante
from core.models import Usuario
from financiero.models import CategoriaIngreso,CategoriaEgreso,ConceptoCobro
from .financiero_fuentes import ORIGENES

REPORTES={
 'panel':('Panel financiero ejecutivo',('desde','hasta')),
 'resultados':('Estado de resultados simplificado sobre base de efectivo',('desde','hasta','ciclo','estudiante','categoria','metodo','operador','estado','origen')),
 'cuentas':('Cuentas por cobrar · saldos actuales',('ciclo','estudiante','estado')),
 'solvencia':('Solvencia estudiantil actual',('ciclo','estudiante','estado')),
 'beneficios':('Beneficios educativos',('desde','hasta','ciclo','estudiante','estado','beneficio')),
 'convenios':('Convenios y conciliación actual',('desde','hasta','ciclo','estudiante','estado')),
 'cajas':('Control consolidado de caja',('desde','hasta','operador','estado')),
 'auditoria':('Auditoría financiera',('desde','hasta','estado','operador')),
}


class EstudianteChoice(forms.ModelChoiceField):
    def label_from_instance(self,e):return f'{e.apellidos}, {e.nombres} · {e.codigo_estudiante}'


class OperadorChoice(forms.ModelChoiceField):
    def label_from_instance(self,u):return u.numero_usuario


class FiltrosFinancierosForm(forms.Form):
    desde=forms.DateField(required=False,label='Desde',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    hasta=forms.DateField(required=False,label='Hasta',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    ciclo=forms.ModelChoiceField(queryset=CicloAcademico.objects.none(),required=False,label='Ciclo académico',empty_label='Todos los ciclos')
    estudiante=EstudianteChoice(queryset=Estudiante.objects.none(),required=False,empty_label='Todos los estudiantes')
    categoria=forms.ChoiceField(label='Categoría',required=False)
    metodo=forms.ChoiceField(label='Método de pago',required=False,choices=[('','Todos'),('EFECTIVO','Efectivo'),('TRANSFERENCIA','Transferencia')])
    operador=OperadorChoice(queryset=Usuario.objects.none(),label='Operador o responsable',required=False,empty_label='Todos los operadores')
    estado=forms.ChoiceField(required=False)
    origen=forms.ChoiceField(required=False,choices=[('','Todos los orígenes'),('ACADEMICOS','Todos los cobros académicos'),('DONACIONES','Todas las donaciones'),*ORIGENES.items()])
    beneficio=forms.ChoiceField(label='Beneficio',required=False,choices=[('','Becas y padrinazgos'),('BECAS','Becas'),('PADRINAZGOS','Padrinazgos')])

    def __init__(self,*args,tipo,**kwargs):
        super().__init__(*args,**kwargs);self.tipo=tipo
        for campo in list(self.fields):
            if campo not in REPORTES[tipo][1]:self.fields.pop(campo)
        if 'ciclo' in self.fields:self.fields['ciclo'].queryset=CicloAcademico.objects.order_by('-anio','numero_ciclo','pk')
        if 'estudiante' in self.fields:self.fields['estudiante'].queryset=Estudiante.objects.order_by('apellidos','nombres','pk')
        if 'operador' in self.fields:self.fields['operador'].queryset=Usuario.objects.only('numero_usuario').order_by('numero_usuario')
        if 'categoria' in self.fields:
            self.fields['categoria'].choices=[('','Todas las categorías')]+[(f'C:{c.pk}',f'Cargo académico · {c.nombre}') for c in ConceptoCobro.objects.order_by('nombre')]+[(f'I:{c.pk}',f'Ingreso · {c.nombre}') for c in CategoriaIngreso.objects.order_by('nombre')]+[(f'E:{c.pk}',f'Egreso · {c.nombre}') for c in CategoriaEgreso.objects.order_by('nombre')]
        opciones={
          'resultados':['REGISTRADO','ANULADO'],
          'cuentas':['VENCIDA','NO_VENCIDA','SALDADA'],
          'solvencia':['SOLVENTE','INSOLVENTE','PADRINAZGO','CONVENIO','COMBINADA'],
          'beneficios':['VIGENTE','VENCIDO','CUMPLIDO','CANCELADO'],
          'convenios':['ACTIVO','INCUMPLIDO','CUMPLIDO','CANCELADO'],
          'cajas':['ABIERTA','CERRADA'],
          'auditoria':['PENDIENTE','APROBADA','RECHAZADA','ANULADO','REGULARIZACION','RESOLUCION','DESEMBOLSO_PENDIENTE'],
        }
        if 'estado' in self.fields:
            self.fields['estado'].choices=[('','Todos los estados')]+[(s,s.replace('_',' ').title()) for s in opciones[tipo]]

    def clean(self):
        d=super().clean()
        if d.get('desde') and d.get('hasta') and d['desde']>d['hasta']:raise forms.ValidationError('La fecha inicial no puede ser posterior a la final.')
        extras=set(self.data)-set(self.fields)-{'page','formato'}
        if extras:raise forms.ValidationError('Este reporte no admite esos filtros. Use los campos visibles; los saldos actuales no son saldos históricos a una fecha de corte.')
        return d
