"""
WSGI config for config project.
"""

import os

from django.core.wsgi import get_wsgi_application

if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_wsgi_application()
