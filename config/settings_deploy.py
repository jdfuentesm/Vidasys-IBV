"""Configuración web tras un proxy HTTPS de confianza; sin secretos por defecto."""

import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .settings import *

DEBUG = False
if not os.environ.get("SECRET_KEY") or len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5:
    raise ImproperlyConfigured(
        "Defina una SECRET_KEY aleatoria de al menos 50 caracteres en el proveedor."
    )
render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
ALLOWED_HOSTS = Csv()(os.environ.get("ALLOWED_HOSTS", render_host))
if not ALLOWED_HOSTS or any("*" in host or "/" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "Defina ALLOWED_HOSTS con los dominios concretos del despliegue."
    )
CSRF_TRUSTED_ORIGINS = Csv()(
    os.environ.get(
        "CSRF_TRUSTED_ORIGINS", ("https://" + render_host) if render_host else ""
    )
)
if not CSRF_TRUSTED_ORIGINS or any(
    urlparse(url).scheme != "https"
    or not urlparse(url).netloc
    or urlparse(url).path
    or urlparse(url).query
    or urlparse(url).fragment
    or urlparse(url).username
    or "*" in url
    for url in CSRF_TRUSTED_ORIGINS
):
    raise ImproperlyConfigured(
        "CSRF_TRUSTED_ORIGINS debe incluir orígenes HTTPS explícitos."
    )
FINANCIERO_CALENDARIO_BACKEND = config(
    "FINANCIERO_CALENDARIO_BACKEND", default="postgresql"
)
FINANCIERO_CONFIG_DIR = Path(
    config("FINANCIERO_CONFIG_DIR", default=str(BASE_DIR / ".financiero-local"))
)
if (
    FINANCIERO_CALENDARIO_BACKEND == "archivo"
    and not FINANCIERO_CONFIG_DIR.is_absolute()
):
    raise ImproperlyConfigured(
        "FINANCIERO_CONFIG_DIR debe ser una ruta absoluta en almacenamiento persistente."
    )
sslmode = config("DB_SSLMODE", default="verify-full")
local_socket = str(DATABASES["default"]["HOST"]).startswith("/")
if sslmode != "verify-full" and not (local_socket and sslmode == "disable"):
    raise ImproperlyConfigured("PostgreSQL remoto requiere DB_SSLMODE=verify-full.")
if not local_socket and not DATABASES["default"]["PASSWORD"]:
    raise ImproperlyConfigured("Defina DB_PASSWORD para PostgreSQL remoto.")
DATABASES["default"]["OPTIONS"] = {"sslmode": sslmode, "connect_timeout": 10}
if not local_socket:
    DATABASES["default"]["OPTIONS"]["sslrootcert"] = config(
        "DB_SSLROOTCERT", default="/etc/ssl/certs/ca-certificates.crt"
    )
DATABASES["default"]["CONN_MAX_AGE"] = config("DB_CONN_MAX_AGE", default=60, cast=int)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# CURRENT_DATE en funciones/vistas debe coincidir con la fecha institucional.
DATABASES["default"]["TIME_ZONE"] = TIME_ZONE
STATIC_ROOT = Path(config("STATIC_ROOT", default=str(BASE_DIR / "staticfiles")))
STATIC_URL = "/static/"
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if config("TRUST_PROXY_HTTPS", default=False, cast=bool)
    else None
)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=3600, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# La demo no envía correo: los accesos se entregan/restablecen manualmente.
# Vacío explícito evita usar el backend de consola o simular un SMTP inexistente.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.dummy.EmailBackend",
    }
}
