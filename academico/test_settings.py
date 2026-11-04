"""Configuración exclusiva para pruebas aisladas; nunca utiliza PostgreSQL."""
import os

os.environ.setdefault("SECRET_KEY", "test-only-not-for-deployment")
from config.settings import *  # noqa: F403,E402

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
TEST_RUNNER = "academico.test_runner.IsolatedAcademicRunner"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
