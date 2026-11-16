"""Configuración explícita por ciclo, sin DDL ni campos ajenos al esquema."""
import json
import os
import tempfile
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from academico.models import CicloAcademico
from .models import ConceptoCobro


def ruta(ciclo):
    return Path(getattr(settings, 'FINANCIERO_CONFIG_DIR', settings.BASE_DIR / '.financiero-local')) / f'ciclo-{ciclo.pk}.json'


def validar(ciclo, datos):
    try:
        emision = date.fromisoformat(datos['emision'])
        matricula = date.fromisoformat(datos['matricula'])
        meses = [date.fromisoformat(f'{mes}-10') for mes in datos['meses']]
        conceptos = [ConceptoCobro.objects.get(pk=datos[k]) for k in ('concepto_matricula', 'concepto_mensualidad')]
    except (ValueError, TypeError, KeyError, ConceptoCobro.DoesNotExist) as error:
        raise ValidationError('Complete las fechas y conceptos del calendario financiero.') from error
    if len(meses) != 5 or len(set(meses)) != 5 or meses != sorted(meses):
        raise ValidationError('Indique cinco meses diferentes, en orden cronológico.')
    if any(not ciclo.fecha_inicio <= fecha <= ciclo.fecha_fin for fecha in [emision, matricula, *meses]):
        raise ValidationError('La emisión y todos los vencimientos deben quedar dentro de las fechas del ciclo.')
    if any(fecha < emision for fecha in [matricula, *meses]):
        raise ValidationError('Ningún vencimiento puede ser anterior a la emisión.')
    nombres = [c.nombre.upper().replace('Í', 'I').strip() for c in conceptos]
    if nombres != ['MATRICULA', 'MENSUALIDAD'] or any(c.estado not in ('ACTIVO', 'ACTIVA') for c in conceptos):
        raise ValidationError('Seleccione conceptos activos de MATRÍCULA y MENSUALIDAD, respectivamente.')
    return emision, matricula, meses, conceptos


def leer(ciclo):
    try:
        datos = json.loads(ruta(ciclo).read_text())
    except (FileNotFoundError, ValueError) as error:
        raise ValidationError('Configure el calendario financiero de este ciclo antes de matricular.') from error
    if datos.get('periodo') != [str(ciclo.fecha_inicio), str(ciclo.fecha_fin)]:
        raise ValidationError('Las fechas del ciclo cambiaron. Revise su calendario financiero.')
    validar(ciclo, datos)
    return datos


def guardar(ciclo, datos):
    # Mismo orden de bloqueo que matrícula: serializa configuración y altas.
    with transaction.atomic():
        ciclo = CicloAcademico.objects.select_for_update().get(pk=ciclo.pk)
        validar(ciclo, datos)
        from academico.models import Matricula
        if ruta(ciclo).exists() and Matricula.objects.filter(ciclo=ciclo).exists():
            raise ValidationError('El ciclo ya tiene matrículas. Su calendario no se puede reemplazar desde esta pantalla.')
        datos = dict(datos, periodo=[str(ciclo.fecha_inicio), str(ciclo.fecha_fin)])
        destino = ruta(ciclo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=destino.parent, delete=False) as archivo:
                temporal = archivo.name
                json.dump(datos, archivo)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, destino)
        finally:
            if temporal and os.path.exists(temporal):
                os.unlink(temporal)
