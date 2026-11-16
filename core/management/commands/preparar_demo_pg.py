"""Construye solo una base demo VACÍA. Nunca importa datos ni aplica migraciones reales."""
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Crear el esquema sintético en una base demo vacía (no migrate).'

    def add_arguments(self, parser):
        parser.add_argument('--confirmar', action='store_true')

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != 'config.settings_demo_pg' or not options['confirmar']:
            raise CommandError('Requiere settings_demo_pg y --confirmar. Lea docs/despliegue/preparacion_postgresql.md.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            if cursor.fetchone()[0] not in ('vidasys_demo_test', 'vidasys_demo'):
                raise CommandError('Base no autorizada.')
            cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S')")
            if cursor.fetchone()[0]:
                raise CommandError('La base ya contiene objetos. No se modifica ni se reinicializa.')
        # Todos los DDL pertenecen a esta única transacción. No se copian registros reales.
        with transaction.atomic():
            with connection.schema_editor() as editor:
                for model in apps.get_models():
                    if not model._meta.proxy:
                        editor.create_model(model)
            with connection.cursor() as cursor:
                cursor.execute('ALTER TABLE obligacion ADD COLUMN monto_final NUMERIC(10,2) GENERATED ALWAYS AS (monto_original - monto_descuento) STORED')
                raiz = Path(settings.BASE_DIR) / 'database/scripts'
                for archivo in ('15_funcion_solvencia_estudiante.sql', '16_vw_acceso_portal_estudiante.sql',
                        '17_vista_estado_cuenta_estudiante.sql', '14_vw_resumen_cuenta_estudiante.sql', 'demo_recalcular_estado.sql'):
                    cursor.execute((raiz / archivo).read_text())
        self.stdout.write(self.style.SUCCESS('Esquema sintético demo creado. No se cargaron datos reales ni se utilizó gestion_ibv.'))
