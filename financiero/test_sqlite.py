"""Adaptadores EXCLUSIVOS para SQLite aislado; SQL canónico sin reglas reescritas."""
import re
from pathlib import Path

from django.conf import settings


def registrar_solvencia(connection):
    if connection.vendor != 'sqlite':
        raise RuntimeError('Adaptador de pruebas exclusivamente SQLite.')
    fuente = (Path(settings.BASE_DIR) / 'database/scripts/15_funcion_solvencia_estudiante.sql').read_text()
    # Extrae literalmente las tres condiciones que devuelven FALSE en la función original.
    condiciones = re.findall(r'IF EXISTS \(\n(.*?)\n    \) THEN\s*RETURN FALSE;', fuente, re.S)
    if len(condiciones) != 3:
        raise RuntimeError('Cambió el SQL de solvencia: revise el adaptador de pruebas.')
    def solvente(estudiante, fecha):
        cursor = connection.connection.cursor()
        for condicion in condiciones:
            sql = condicion.replace('p_id_estudiante', ':estudiante').replace('p_fecha', ':fecha')
            if cursor.execute('SELECT EXISTS (' + sql + ')', {'estudiante': estudiante, 'fecha': fecha}).fetchone()[0]:
                return 0
        return 1
    connection.connection.create_function('estudiante_esta_solvente', 2, solvente)


def calendario_ficticio(ciclo):
    from .calendario import guardar
    from .models import ConceptoCobro
    matricula, _ = ConceptoCobro.objects.get_or_create(nombre='MATRICULA', defaults={'estado': 'ACTIVO', 'permite_abonos': False})
    mensualidad, _ = ConceptoCobro.objects.get_or_create(nombre='MENSUALIDAD', defaults={'estado': 'ACTIVO', 'permite_abonos': True})
    guardar(ciclo, {'emision': '2026-01-01', 'matricula': '2026-01-10',
        'meses': ['2026-02', '2026-03', '2026-04', '2026-05', '2026-06'],
        'concepto_matricula': matricula.pk, 'concepto_mensualidad': mensualidad.pk})
