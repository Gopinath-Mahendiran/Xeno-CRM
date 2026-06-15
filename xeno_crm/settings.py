# xeno_crm/settings.py

from pathlib import Path
from dotenv import load_dotenv
import os
import logging

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-this-in-production')

DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Parse ALLOWED_HOSTS from comma-separated env var
_allowed = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]

# ─────────────────────────────────────────────────────────────────────────────
# Applications
# ─────────────────────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'django_celery_results',
    'rest_framework.authtoken',
    'crm',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',        # ← must be first
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # ← right after Security
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'xeno_crm.urls'

# ─────────────────────────────────────────────────────────────────────────────
# Templates — also point at the Vite SPA dist folder
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'static_frontend',   # Vite build output (index.html lives here)
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'xeno_crm.wsgi.application'

# ─────────────────────────────────────────────────────────────────────────────
# Database — SQLite (single-worker safe; swap for PostgreSQL in production)
# ─────────────────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv('DATABASE_URL', '')

if DATABASE_URL:
    # PostgreSQL via Railway / Render (install psycopg2-binary)
    import dj_database_url  # noqa: E402  (installed only when needed)
    DATABASES = {'default': dj_database_url.config(default=DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {'timeout': 60},
        }
    }

# ─────────────────────────────────────────────────────────────────────────────
# Password validation
# ─────────────────────────────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─────────────────────────────────────────────────────────────────────────────
# Internationalisation
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────────────────────────────────────
# Static files — WhiteNoise serves both Django admin and the React SPA
# ─────────────────────────────────────────────────────────────────────────────

STATIC_URL = '/assets/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Vite emits assets/ inside the dist folder — tell Django where to find them
STATICFILES_DIRS = [
    BASE_DIR / 'static_frontend' / 'assets',
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─────────────────────────────────────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────────────────────────────────────

if DEBUG:
    # Allow all origins in development
    CORS_ALLOW_ALL_ORIGINS = True
else:
    # In production, restrict to known origins
    _cors = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:8000')
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(',') if o.strip()]
    CORS_ALLOW_CREDENTIALS = True

# ─────────────────────────────────────────────────────────────────────────────
# Security headers (enforced only in production)
# ─────────────────────────────────────────────────────────────────────────────

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    # Uncomment when HTTPS is configured:
    # SECURE_SSL_REDIRECT = True
    # SESSION_COOKIE_SECURE = True
    # CSRF_COOKIE_SECURE = True
    # SECURE_HSTS_SECONDS = 31536000

# ─────────────────────────────────────────────────────────────────────────────
# REST Framework
# ─────────────────────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES':   ['rest_framework.parsers.JSONParser'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Redis
# ─────────────────────────────────────────────────────────────────────────────

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# ─────────────────────────────────────────────────────────────────────────────
# Celery
# ─────────────────────────────────────────────────────────────────────────────

CELERY_BROKER_URL         = REDIS_URL
CELERY_RESULT_BACKEND     = 'django-db'
CELERY_CACHE_BACKEND      = 'django-cache'
CELERY_ACCEPT_CONTENT     = ['json']
CELERY_TASK_SERIALIZER    = 'json'
CELERY_RESULT_SERIALIZER  = 'json'
CELERY_TIMEZONE           = 'Asia/Kolkata'

# ─────────────────────────────────────────────────────────────────────────────
# Cache (Redis)
# ─────────────────────────────────────────────────────────────────────────────

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# AI — Google Gemini (production) or local Ollama (development)
# ─────────────────────────────────────────────────────────────────────────────

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')

# USE_LOCAL_LLM: False → use Gemini, True → use Ollama/local
USE_LOCAL_LLM      = os.getenv('USE_LOCAL_LLM', 'False') == 'True'
LOCAL_LLM_PROVIDER = os.getenv('LOCAL_LLM_PROVIDER', 'ollama').lower()
LOCAL_LLM_MODEL    = os.getenv('LOCAL_LLM_MODEL', 'qwen3:8b')
LOCAL_LLM_API_BASE = os.getenv('LOCAL_LLM_API_BASE', 'http://localhost:11434')
LOCAL_LLM_API_KEY  = os.getenv('LOCAL_LLM_API_KEY', 'ollama')

# ─────────────────────────────────────────────────────────────────────────────
# Service URLs
# ─────────────────────────────────────────────────────────────────────────────

CHANNEL_SERVICE_URL = os.getenv('CHANNEL_SERVICE_URL', 'http://localhost:5001')
CRM_BASE_URL        = os.getenv('CRM_BASE_URL', 'http://localhost:8000')

# ─────────────────────────────────────────────────────────────────────────────
# Logging — stdout JSON in production, verbose console in debug
# ─────────────────────────────────────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'crm':    {'handlers': ['console'], 'level': 'INFO',    'propagate': False},
    },
}