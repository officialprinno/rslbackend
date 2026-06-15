"""
ASGI config — HTTP + WebSocket (Django Channels).
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django_asgi_app = get_asgi_application()

from apps.messaging.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
