"""User app signals."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.models import User


@receiver(post_save, sender=User)
def ensure_superuser_staff(sender, instance, created, **kwargs):
    """Ensure superusers always have is_staff=True."""
    if instance.is_superuser and not instance.is_staff:
        User.objects.filter(pk=instance.pk).update(is_staff=True)
