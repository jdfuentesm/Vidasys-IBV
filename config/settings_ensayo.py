"""Solo comandos de ensayo: no configura ni migra ninguna base."""
import os
from django.core.exceptions import ImproperlyConfigured
from config.settings import *  # noqa: F403

if os.environ.get("DB_NAME") != "gestion_ibv_ensayo":
    raise ImproperlyConfigured("DB_NAME debe ser exactamente gestion_ibv_ensayo.")
if set(DATABASES) != {"default"} or DATABASES["default"]["NAME"] != "gestion_ibv_ensayo":  # noqa: F405
    raise ImproperlyConfigured("Solo se admite la conexión default a gestion_ibv_ensayo.")
if globals().get("DATABASE_ROUTERS"):
    raise ImproperlyConfigured("No se admiten routers en el ensayo.")
ENSAYO_ACTIVO = True
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
DATABASES["default"]["OPTIONS"] = {**DATABASES["default"].get("OPTIONS", {}), "options": "-c search_path=pg_catalog,public -c lock_timeout=5s -c statement_timeout=60s"}  # noqa: F405
from core.ensayo_seguro import instalar_guardia  # noqa: E402
instalar_guardia()
