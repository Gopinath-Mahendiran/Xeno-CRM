# xeno_crm/__init__.py
# Make Celery app available at package import time
from .celery import app as celery_app

__all__ = ("celery_app",)
