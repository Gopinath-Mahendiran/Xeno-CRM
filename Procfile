web: gunicorn xeno_crm.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120
worker: celery -A xeno_crm worker --loglevel=info --concurrency 2
channel: python channel_service/app.py
