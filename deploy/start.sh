#!/bin/sh
set -eu
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings_demo_pg}"
python manage.py check
python manage.py verificar_demo_pg
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --config deploy/gunicorn.conf.py
