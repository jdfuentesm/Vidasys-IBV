"""Presentación de formularios existentes: no agrega ni valida campos."""
from django import template
from django import forms

register = template.Library()
GRUPOS = {
    'estudiante': [('Identificación', ('codigo_estudiante', 'nombres', 'apellidos', 'fecha_nacimiento')),
        ('Contacto', ('telefono', 'correo', 'direccion')), ('Registro institucional', ('fecha_ingreso', 'estado'))],
    'matricula': [('Estudiante y ciclo', ('estudiante', 'ciclo')),
        ('Datos de matrícula', ('numero_matricula', 'fecha_matricula', 'observaciones'))],
    'beca': [('Estudiante y ciclo', ('matricula',)), ('Apoyo solicitado', ('porcentaje', 'conceptos', 'alcance')),
        ('Motivo de la solicitud', ('justificacion',))],
    'operacion': [('Concepto y destinatario', ('categoria', 'concepto', 'origen', 'beneficiario')),
        ('Importe y pago', ('monto', 'metodo', 'referencia', 'fecha', 'fondo', 'contado')),
        ('Motivo y respaldo', ('justificacion', 'motivo', 'observaciones', 'archivo'))],
    'convenio': [('Obligaciones que desea incluir', ('obligaciones',)), ('Motivo', ('motivo',))],
    'abono': [('Método de pago', ('metodo', 'referencia'))],
}


@register.simple_tag
def secciones_operativas(form, tipo='operacion'):
    usados = set()
    resultado = []
    for titulo, nombres in GRUPOS.get(tipo, []):
        campos = [form[n] for n in nombres if n in form.fields and not form[n].is_hidden]
        if campos:
            resultado.append({'titulo': titulo, 'campos': campos})
            usados.update(nombres)
    if tipo == 'abono':
        for titulo, prefijo in [('Abonos por cuota', 'cuota_'), ('Desglose entre obligaciones originales', 'obligacion_')]:
            campos = [f for f in form.visible_fields() if f.name.startswith(prefijo)]
            if campos:
                resultado.append({'titulo': titulo, 'campos': campos})
                usados.update(f.name for f in campos)
    resto = [f for f in form.visible_fields() if f.name not in usados]
    if resto:
        resultado.append({'titulo': 'Datos de la operación', 'campos': resto})
    return resultado


@register.filter
def campo_operativo(campo):
    attrs = {}
    if isinstance(campo.field, forms.DecimalField):
        attrs['inputmode'] = 'decimal'
    if campo.name.startswith('importe_'):
        attrs['aria-label'] = f'Importe a cobrar (USD) · {campo.label}'
    if campo.name == 'telefono':
        attrs.update(inputmode='tel', autocomplete='tel')
    if campo.name in ('nombres', 'apellidos', 'correo'):
        attrs['autocomplete'] = {'nombres': 'given-name', 'apellidos': 'family-name', 'correo': 'email'}[campo.name]
    return campo.as_widget(attrs=attrs)
