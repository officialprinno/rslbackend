"""
Base settings for Rock Solutions FMS.
Shared by development and production — override secrets and DEBUG per environment.
"""

from datetime import timedelta
from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load backend/.env for local runs (Railway injects env vars directly).
load_dotenv(BASE_DIR / ".env")


def env(key: str, *fallbacks: str, default: str | None = None) -> str | None:
    """Read the first non-empty environment variable from key/fallbacks."""
    for name in (key, *fallbacks):
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return default


def env_bool(key: str, *fallbacks: str, default: bool = False) -> bool:
    value = env(key, *fallbacks)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def env_list(key: str, *fallbacks: str, default: str = "") -> list[str]:
    raw = env(key, *fallbacks, default=default) or default
    return [item.strip() for item in raw.split(",") if item.strip()]


# SECRET_KEY is set in development.py / production.py (never hardcoded here).
SECRET_KEY = env("SECRET_KEY", "DJANGO_SECRET_KEY")

DEBUG = env_bool("DEBUG", "DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "ALLOWED_HOSTS")

INSTALLED_APPS = [
    "daphne",
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "channels",
    # Project apps
    "apps.core",
    "apps.users",
    "apps.inventory",
    "apps.procurement",
    "apps.sales",
    "apps.logistics",
    "apps.production",
    "apps.finance",
    "apps.hr",
    "apps.safety",
    "apps.messaging",
    "apps.email_client",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = env("DATABASE_URL")
if not DATABASE_URL:
    raise ImproperlyConfigured(
        "DATABASE_URL is required. Set it in backend/.env locally or in Railway variables."
    )

import dj_database_url  # noqa: E402

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        ssl_require=True,
    ),
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Dar_es_Salaam"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS — set via environment (no hardcoded production domains).
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "apps.core.drf_backends.FMSDjangoFilterBackend",
        "apps.core.drf_backends.FMSSearchFilter",
        "apps.core.drf_backends.FMSOrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
}

# SimpleJWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# FMS business defaults
DEFAULT_CURRENCY_CODE = "TZS"
VAT_RATE = 0.18
NSSF_EMPLOYER_RATE = 0.10
NSSF_EMPLOYEE_RATE = 0.10

# Optional frontend URL for admin links (Jazzmin).
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:4200")

# Django Channels (in-memory layer for dev; use Redis in production if needed)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# Jazzmin admin theme (must load after INSTALLED_APPS is defined)
from .jazzminsetting import JAZZMIN_SETTINGS, JAZZMIN_UI_TWEAKS  # noqa: E402, F401
