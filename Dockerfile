FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt \
    && groupadd --gid 10001 vidasys \
    && useradd --uid 10001 --gid vidasys --no-create-home vidasys \
    && mkdir -p /data/calendarios /app/staticfiles \
    && chown -R vidasys:vidasys /data /app
COPY --chown=vidasys:vidasys . .
ENV DJANGO_SETTINGS_MODULE=config.settings_demo_pg
USER vidasys
EXPOSE 8000
CMD ["sh", "deploy/start.sh"]
