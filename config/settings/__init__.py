"""
Django settings package — defaults to development configuration.

Override with DJANGO_SETTINGS_MODULE:
  - config.settings.development
  - config.settings.production
"""

from .development import *  # noqa: F401, F403
