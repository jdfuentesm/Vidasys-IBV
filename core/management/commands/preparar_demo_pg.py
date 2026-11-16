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
        parser.add_argument('--base-esperada', default='vidasys_demo', choices=('vidasys_demo',))
        parser.add_argument('--usuario-esperado', default='vidasys_demo_limitado', choices=('vidasys_demo_limitado',))

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != 'config.settings_demo_pg' or not options['confirmar']:
            raise CommandError('Requiere settings_demo_pg y --confirmar. Lea docs/despliegue/preparacion_postgresql.md.')
        base = options['base_esperada']
        usuario = options['usuario_esperado']
        if (base, usuario) != ('vidasys_demo', 'vidasys_demo_limitado'):
            raise CommandError('Base no autorizada.')
        if connection.settings_dict['NAME'] != base or connection.settings_dict['USER'] != usuario:
            raise CommandError('La configuración no coincide con la base y el usuario esperados.')
        # Todas las comprobaciones y el DDL usan una única conexión y transacción.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL search_path TO public")
                cursor.execute('SELECT current_database(), current_user')
                if cursor.fetchone() != (base, usuario):
                    raise CommandError('La conexión no coincide con la identidad esperada.')
                cursor.execute('SELECT pg_advisory_xact_lock(824617203)')
                cursor.execute("SELECT has_schema_privilege(current_user, 'public', 'USAGE'), has_schema_privilege(current_user, 'public', 'CREATE'), has_language_privilege(current_user, 'plpgsql', 'USAGE')")
                if not all(cursor.fetchone()):
                    raise CommandError('Se requiere USAGE y CREATE en public y USAGE en plpgsql.')
                cursor.execute("""
                    SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                                  WHERE n.nspname='public')
                        OR EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                                  WHERE n.nspname='public')
                        OR EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
                                  WHERE n.nspname='public')
                """)
                if cursor.fetchone()[0]:
                    raise CommandError('public ya contiene objetos. No se modifica ni se reinicializa.')
            with connection.schema_editor() as editor:
                for model in apps.get_models():
                    if not model._meta.proxy:
                        editor.create_model(model)
            with connection.cursor() as cursor:
                cursor.execute('ALTER TABLE obligacion ADD COLUMN monto_final NUMERIC(10,2) GENERATED ALWAYS AS (monto_original - monto_descuento) STORED')
                raiz = Path(settings.BASE_DIR) / 'database/scripts'
                for archivo in ('demo_restricciones.sql', '15_funcion_solvencia_estudiante.sql', '16_vw_acceso_portal_estudiante.sql',
                        '17_vista_estado_cuenta_estudiante.sql', '14_vw_resumen_cuenta_estudiante.sql', 'demo_recalcular_estado.sql'):
                    cursor.execute((raiz / archivo).read_text())
        self.stdout.write(self.style.SUCCESS('Esquema sintético demo creado. No se cargaron datos reales ni se utilizó gestion_ibv.'))
