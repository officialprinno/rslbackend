"""Development settings — local runs only."""

from .base import *  # noqa: F401, F403

DEBUG = env_bool("DEBUG", "DJANGO_DEBUG", default=True)  # noqa: F405

if not SECRET_KEY:  # noqa: F405
    SECRET_KEY = "django-insecure-dev-only-not-for-production"  # noqa: F405

if not ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]  # noqa: F405

if not CORS_ALLOWED_ORIGINS:  # noqa: F405
    CORS_ALLOWED_ORIGINS = [  # noqa: F405
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]

CSRF_TRUSTED_ORIGINS = env_list(  # noqa: F405
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:4200,http://127.0.0.1:4200",
)

# WhiteNoise: serve static from app directories in dev without collectstatic.
WHITENOISE_USE_FINDERS = True
