import uuid
from django import forms


class AperturaForm(forms.Form):
    clave = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    fondo = forms.DecimalField(label='Fondo inicial de efectivo (USD)', max_digits=12, decimal_places=2, min_value=0)
    observaciones = forms.CharField(required=False, max_length=4000, widget=forms.Textarea)


class CierreForm(forms.Form):
    contado = forms.DecimalField(label='Efectivo físico contado (USD)', max_digits=12, decimal_places=2, min_value=0)
    observaciones = forms.CharField(label='Observaciones del arqueo', required=False, max_length=4000, widget=forms.Textarea)
    revision = forms.CharField(required=False, widget=forms.HiddenInput)


class AnulacionForm(forms.Form):
    clave = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    motivo = forms.CharField(label='Motivo obligatorio de la anulación', max_length=4000, widget=forms.Textarea)


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(label='Decisión', choices=[('APROBADA', 'Aprobar anulación'), ('RECHAZADA', 'Rechazar solicitud')])
    observaciones = forms.CharField(label='Observaciones (obligatorias al rechazar)', required=False, max_length=4000, widget=forms.Textarea)
    revision = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean(self):
        d = super().clean()
        if d.get('decision') == 'RECHAZADA' and not d.get('observaciones'):
            self.add_error('observaciones', 'Explique el rechazo.')
        return d


class FechasForm(forms.Form):
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        d = super().clean()
        if d.get('desde') and d.get('hasta') and d['desde'] > d['hasta']:
            raise forms.ValidationError('La fecha inicial no puede ser posterior a la final.')
        return d
