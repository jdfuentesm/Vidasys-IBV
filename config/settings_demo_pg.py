"""Base demo explícita, nunca gestion_ibv ni la configuración .env de desarrollo."""
import os
import sys
from django.core.exceptions import ImproperlyConfigured

if os.environ.get('VIDASYS_DEMO') != '1' or os.environ.get('DB_NAME') not in ('vidasys_demo_test', 'vidasys_demo'):
    raise ImproperlyConfigured('La demo requiere VIDASYS_DEMO=1 y DB_NAME=vidasys_demo_test o vidasys_demo.')
if any(nombre not in os.environ for nombre in ('DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'SECRET_KEY')):
    raise ImproperlyConfigured('La demo requiere variables de conexión y SECRET_KEY explícitas en el proceso.')
if any(arg in ('migrate','flush','test') for arg in sys.argv[1:]):
    raise ImproperlyConfigured('No use migrate/flush/test con la configuración de demo. Inicialice solo una base nueva y vacía.')
from .settings_deploy import *  # noqa: F403,E402

if FINANCIERO_CALENDARIO_BACKEND != 'postgresql':
    raise ImproperlyConfigured('La demo web requiere calendario persistente en PostgreSQL.')

DATABASES['default']['TEST'] = {'NAME': 'vidasys_demo_test_runner_no_usar'}
# No usar el runner normal: la comprobación de integración actúa en la base demo explícita.
from django.db.backends.signals import connection_created


def verificar_destino(sender, connection, **kwargs):
    if connection.vendor != 'postgresql' or connection.alias != 'default' or connection.settings_dict['NAME'] != os.environ['DB_NAME']:
        raise ImproperlyConfigured('Destino no autorizado para la demo.')
    with connection.connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, EXISTS(SELECT 1 FROM pg_database WHERE datname=%s) FROM pg_roles WHERE rolname=current_user", ['gestion_ibv'])
        nombre, superuser, createdb, createrole, replication, bypassrls, base_real = cursor.fetchone()
        if nombre != os.environ['DB_NAME'] or superuser or createdb or createrole or replication or bypassrls or base_real:
            connection.close()
            raise ImproperlyConfigured('La demo requiere clúster sin gestion_ibv y un rol limitado sin privilegios administrativos.')

connection_created.connect(verificar_destino, weak=False, dispatch_uid='vidasys-demo-destino')
