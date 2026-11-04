"""Inspección de metadatos; no ejecuta DDL ni cambios de datos."""
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from core.models import Usuario


class Command(BaseCommand):
    help = "Verifica claves foráneas de usuario y enumera referencias heredadas a auth_user (solo lectura)."

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")

    def handle(self, *args, **options):
        connection = connections[options["database"]]
        expected = (Usuario._meta.db_table, Usuario._meta.pk.column)
        self.stdout.write(f"AUTH_USER_MODEL={settings.AUTH_USER_MODEL}; LogEntry.user={LogEntry._meta.get_field('user').remote_field.model._meta.label}")
        required = {
            "django_admin_log": "user_id",
            "usuario_groups": "usuario_id",
            "usuario_user_permissions": "usuario_id",
        }
        failures = []
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
            for table in tables:
                constraints = connection.introspection.get_constraints(cursor, table)
                relevant = []
                for name, constraint in constraints.items():
                    target = constraint.get("foreign_key")
                    if target:
                        columns = constraint.get("columns", [])
                        if target[0] == "auth_user":
                            self.stdout.write(f"HEREDADA: {table}.{','.join(columns)} -> auth_user.{target[1]} ({name})")
                        if table in required and columns == [required[table]]:
                            relevant.append(target)
                if table in required:
                    if relevant == [expected]:
                        self.stdout.write(f"OK: {table}.{required[table]} -> {expected[0]}.{expected[1]}")
                    else:
                        failures.append(f"{table}: referencia ausente, duplicada o incompatible")
            failures.extend(f"{table}: tabla ausente" for table in required if table not in tables)
        if failures:
            raise CommandError("; ".join(failures))
        self.stdout.write(self.style.SUCCESS("Referencias principales compatibles. Las referencias heredadas requieren revisión individual; no se modificó el esquema."))
