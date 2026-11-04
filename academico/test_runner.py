"""Crea tablas no administradas solo en SQLite efímero, sin tocar modelos ni migraciones."""
from django.apps import apps
from django.db import connection
from django.test.runner import DiscoverRunner


class IsolatedAcademicRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        if connection.vendor != "sqlite" or connection.settings_dict["NAME"] != ":memory:":
            raise RuntimeError("Este runner requiere SQLite en memoria; no admite PostgreSQL.")
        old_config = super().setup_databases(**kwargs)
        with connection.schema_editor() as editor:
            for label in ("core", "academico"):
                for model in apps.get_app_config(label).get_models():
                    if not model._meta.managed:
                        editor.create_model(model)
        return old_config
