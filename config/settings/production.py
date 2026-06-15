"""Production settings."""

import os

from .base import *  # noqa: F401, F403

DEBUG = False

_railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
_hosts = env_list(  # noqa: F405
    "DJANGO_ALLOWED_HOSTS",
    "ALLOWED_HOSTS",
    default=_railway_domain or "localhost,127.0.0.1",
)
if _railway_domain and _railway_domain not in _hosts:
    _hosts.append(_railway_domain)
ALLOWED_HOSTS = _hosts

# Railway HTTPS proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

CSRF_TRUSTED_ORIGINS = env_list(  # noqa: F405
    "CSRF_TRUSTED_ORIGINS",
    default=(
        f"https://{_railway_domain}" if _railway_domain else "http://localhost:4200,http://127.0.0.1:4200"
    ),
)

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
}