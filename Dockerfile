FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PORT=8080

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic no firma nada, pero carga los settings de produccion, que ahora
# exigen SECRET_KEY. Se usa una clave descartable solo para este paso: en
# runtime la variable sigue siendo obligatoria y no tiene default.
RUN SECRET_KEY=build-time-only-not-used python manage.py collectstatic --noinput

# La app no escribe en el sistema de archivos en runtime, asi que no necesita root.
RUN useradd --create-home --uid 10001 axis && chown -R axis:axis /app
USER axis

# --timeout 0 dejaba que un worker bloqueado en una API externa no se reciclara nunca.
CMD exec gunicorn config.wsgi:application --bind :$PORT --workers 2 --threads 8 --timeout 120 --graceful-timeout 30
