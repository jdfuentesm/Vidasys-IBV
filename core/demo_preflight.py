"""Comprobación de esquema de demo. Únicamente consultas de catálogo y SELECT."""
from django.apps import apps
from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection


def verificar_esquema_demo():
    if settings.SETTINGS_MODULE != 'config.settings_demo_pg':
        raise CommandError('Use exclusivamente config.settings_demo_pg.')
    from academico.models import Asistencia, Calificacion, Estudiante, InscripcionCurso, Matricula
    from financiero.models import CalendarioFinanciero, DetallePago, Obligacion, Pago
    from core.models import Usuario
    with connection.cursor() as cursor:
        tablas=set(connection.introspection.table_names(cursor))
        esperadas={m._meta.db_table for m in apps.get_models(include_auto_created=True) if not m._meta.proxy}
        faltantes=esperadas-tablas
        if faltantes:
            raise CommandError('Faltan tablas de demostración: '+', '.join(sorted(faltantes))+'. No se crea ni modifica el esquema automáticamente.')
        catalogo={}
        for modelo,nombres in [(Usuario,('numero_usuario',)),(Usuario,('correo_acceso',)),
                (Estudiante,('usuario',)),(Matricula,('estudiante','ciclo')),
                (InscripcionCurso,('matricula','curso')),(Obligacion,('matricula','concepto','fecha_vencimiento')),
                (Pago,('numero_recibo',)),(DetallePago,('pago','obligacion')),
                (Calificacion,('inscripcion',)),(Asistencia,('inscripcion','sesion')),(CalendarioFinanciero,('ciclo',))]:
            columnas=[modelo._meta.get_field(n).column for n in nombres]
            if modelo not in catalogo:
                catalogo[modelo]=connection.introspection.get_constraints(cursor,modelo._meta.db_table)
            restricciones=catalogo[modelo]
            if not any((c['unique'] or c['primary_key']) and c['columns']==columnas for c in restricciones.values()):
                raise CommandError(f'Falta unicidad requerida: {modelo._meta.db_table} ({", ".join(columnas)}).')
        for modelo,nombres in [(Estudiante,('usuario',)),(Matricula,('estudiante','ciclo')),
                (InscripcionCurso,('matricula','curso')),(Obligacion,('matricula','concepto')),
                (Pago,('estudiante','usuario')),(DetallePago,('pago','obligacion')),
                (CalendarioFinanciero,('ciclo',))]:
            if modelo not in catalogo:
                catalogo[modelo]=connection.introspection.get_constraints(cursor,modelo._meta.db_table)
            for nombre in nombres:
                campo=modelo._meta.get_field(nombre)
                destino=(campo.remote_field.model._meta.db_table,campo.target_field.column)
                if not any(c['columns']==[campo.column] and c['foreign_key']==destino for c in catalogo[modelo].values()):
                    raise CommandError(f'Falta relación requerida: {modelo._meta.db_table}.{campo.column}.')
        for firma in ('estudiante_esta_solvente(bigint,date)','recalcular_estado_obligacion(bigint)'):
            cursor.execute('SELECT to_regprocedure(%s)',[firma])
            if cursor.fetchone()[0] is None:raise CommandError('Falta función: '+firma)
        for vista in ('vw_estado_cuenta_estudiante','vw_resumen_cuenta_estudiante','vw_acceso_portal_estudiante'):
            cursor.execute('SELECT to_regclass(%s)',[vista])
            if cursor.fetchone()[0] is None:raise CommandError('Falta vista: '+vista)
        cursor.execute("SELECT pg_get_serial_sequence('pago','id_pago')")
        if cursor.fetchone()[0] is None:raise CommandError('Falta secuencia del recibo en pago.id_pago.')
        cursor.execute("SELECT attgenerated FROM pg_attribute WHERE attrelid='obligacion'::regclass AND attname='monto_final'")
        registro=cursor.fetchone()
        if not registro or registro[0]!='s':raise CommandError('Falta monto_final calculado STORED.')
        cursor.execute("SELECT format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='calendario_financiero'::regclass AND attname='datos'")
        if cursor.fetchone()[0]!='jsonb':raise CommandError('Calendario financiero requiere datos JSONB.')
