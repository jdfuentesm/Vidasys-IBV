"""Inicialización permitida exclusivamente para una base SQLite :memory: vacía."""
from django.apps import apps
from django.core.management import call_command
from django.db import connection
from .generador import verificar_memoria


def preparar_tablas():
    verificar_memoria()
    if connection.introspection.table_names():raise RuntimeError('El entorno debe estar vacío.')
    call_command('migrate',interactive=False,verbosity=0)
    verificar_memoria()
    with connection.schema_editor() as editor:
        for label in ('core','academico','financiero'):
            for model in apps.get_app_config(label).get_models():
                if not model._meta.managed:editor.create_model(model)
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE obligacion ADD COLUMN monto_final NUMERIC GENERATED ALWAYS AS (monto_original - monto_descuento) VIRTUAL')
    from financiero.test_sqlite import registrar_solvencia
    registrar_solvencia(connection)
