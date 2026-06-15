"""Production settings for Railway + Neon PostgreSQL."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403

DEBUG = False

if not SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("SECRET_KEY environment variable is required in production.")

_railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()

_hosts = list(ALLOWED_HOSTS)  # noqa: F405
if not _hosts:
    if _railway_domain:
        _hosts = [".up.railway.app", _railway_domain]
    else:
        raise ImproperlyConfigured(
            "Set DJANGO_ALLOWED_HOSTS or deploy on Railway (RAILWAY_PUBLIC_DOMAIN)."
        )
elif _railway_domain and _railway_domain not in _hosts and ".up.railway.app" not in _hosts:
    _hosts.append(_railway_domain)
ALLOWED_HOSTS = _hosts  # noqa: F405

# Railway terminates TLS at the edge — trust the proxy headers.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

_csrf_origins = list(env_list("CSRF_TRUSTED_ORIGINS"))  # noqa: F405
if _railway_domain:
    _railway_origin = f"https://{_railway_domain}"
    if _railway_origin not in _csrf_origins:
        _csrf_origins.append(_railway_origin)
if not _csrf_origins:
    raise ImproperlyConfigured(
        "CSRF_TRUSTED_ORIGINS is required in production "
        "(e.g. https://your-app.up.railway.app)."
    )
CSRF_TRUSTED_ORIGINS = _csrf_origins  # noqa: F405

if not CORS_ALLOWED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured(
        "CORS_ALLOWED_ORIGINS is required in production (e.g. https://your-frontend.com)."
    )

# Production security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=False)  # noqa: F405

# WhiteNoise compressed static files (run collectstatic on release).
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "stream": "ext://sys.stderr",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "gunicorn.error": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "gunicorn.access": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
