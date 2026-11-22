from decimal import Decimal

from django import forms

from academico.models import CicloAcademico
from .calendario import validar
from .models import ConceptoCobro


class CalendarioForm(forms.Form):
    ciclo = forms.ModelChoiceField(queryset=CicloAcademico.objects.all().order_by('-anio', 'numero_ciclo'))
    concepto_matricula = forms.ModelChoiceField(queryset=ConceptoCobro.objects.all(), label='Concepto de matrícula')
    concepto_mensualidad = forms.ModelChoiceField(queryset=ConceptoCobro.objects.all(), label='Concepto de mensualidad')
    emision = forms.DateField(label='Emisión de las seis obligaciones', widget=forms.DateInput(attrs={'type': 'date'}))
    matricula = forms.DateField(label='Vencimiento de matrícula', widget=forms.DateInput(attrs={'type': 'date'}))
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for n in range(1, 6):
            self.fields[f'mes_{n}'] = forms.RegexField(r'^\d{4}-\d{2}$', label=f'Mes de mensualidad {n}', widget=forms.TextInput(attrs={'type': 'month'}))

    def configuracion(self):
        d = self.cleaned_data
        return {'concepto_matricula': d['concepto_matricula'].pk, 'concepto_mensualidad': d['concepto_mensualidad'].pk,
                'emision': d['emision'].isoformat(), 'matricula': d['matricula'].isoformat(),
                'meses': [d[f'mes_{n}'] for n in range(1, 6)]}

    def clean(self):
        datos = super().clean()
        if not self.errors:
            validar(datos['ciclo'], self.configuracion())
        return datos


class ConceptoForm(forms.Form):
    nombre = forms.ChoiceField(choices=[('MATRICULA', 'Matrícula'), ('MENSUALIDAD', 'Mensualidad')])
    abonos = forms.ChoiceField(label='¿Se permiten abonos parciales?', choices=[('', 'Seleccione expresamente'), ('SI', 'Sí'), ('NO', 'No')])


class PagoForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    metodo = forms.ChoiceField(label='Método de pago', choices=[('EFECTIVO', 'Efectivo'), ('TRANSFERENCIA', 'Transferencia')])
    referencia = forms.CharField(max_length=100, required=False, label='Referencia del comprobante')

    def __init__(self, *args, filas, **kwargs):
        super().__init__(*args, **kwargs)
        self.obligaciones = []
        for fila in filas:
            o = fila['obligacion']
            if fila['anulada'] or (fila['saldo'] <= 0 and not (self.is_bound and f'importe_{o.pk}' in self.data)):
                continue
            self.obligaciones.append(o)
            self.fields[f'importe_{o.pk}'] = forms.DecimalField(required=False, max_digits=10, decimal_places=2,
                min_value=Decimal('.01'), label=f'{o.concepto.nombre} · {o.fecha_vencimiento:%d/%m/%Y}',
                help_text=f'Saldo financiero USD {fila["saldo"]:.2f}. ' + (f'Padrinazgo reservado USD {fila["reserva_padrinazgo"]:.2f}; a cargo del estudiante USD {max(fila["saldo"]-fila["reserva_padrinazgo"], Decimal("0")):.2f}. ' if fila.get('reserva_padrinazgo') else '') + ('Permite abonos.' if o.concepto.permite_abonos else 'Pago completo de la parte del estudiante obligatorio.'),
                widget=forms.NumberInput(attrs={'step': '.01', 'min': '.01'}))

    def aplicaciones(self):
        return [(o.pk, self.cleaned_data[f'importe_{o.pk}']) for o in self.obligaciones if self.cleaned_data.get(f'importe_{o.pk}') is not None]

    def clean(self):
        datos = super().clean()
        if not self.errors and not self.aplicaciones():
            raise forms.ValidationError('Indique un importe en al menos una obligación.')
        return datos
