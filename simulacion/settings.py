"""Configuración autónoma: no importa config.settings ni lee .env/credenciales."""
from pathlib import Path
import atexit
import secrets
import shutil
import tempfile
BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=secrets.token_urlsafe(48)
DEBUG=True
ALLOWED_HOSTS=['127.0.0.1','localhost','testserver']
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes',
    'django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles',
    'core','academico','financiero','reportes']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'core.middleware_acceso.CambioPasswordObligatorioMiddleware','django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='config.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],
    'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
AUTH_USER_MODEL='core.Usuario'
LOGIN_URL='/login/'
LOGIN_REDIRECT_URL='/'
LOGOUT_REDIRECT_URL='/login/'
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.'+n} for n in (
    'UserAttributeSimilarityValidator','MinimumLengthValidator','CommonPasswordValidator','NumericPasswordValidator')]
PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher']
LANGUAGE_CODE='es-sv'
TIME_ZONE='America/El_Salvador'
USE_I18N=True
USE_TZ=True
STATIC_URL='/static/'
STATICFILES_DIRS=[BASE_DIR/'static']
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
TEST_RUNNER='academico.test_runner.IsolatedAcademicRunner'
FINANCIERO_CALENDARIO_BACKEND='archivo'
FINANCIERO_CONFIG_DIR=tempfile.mkdtemp(prefix='vidasys-simulacion-')
atexit.register(shutil.rmtree,FINANCIERO_CONFIG_DIR,ignore_errors=True)
MAILERS={'default':{'BACKEND':'django.core.mail.backends.locmem.EmailBackend'}}
