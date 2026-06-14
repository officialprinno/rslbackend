"""
Core models shared across Rock Solutions FMS.
"""

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    """Abstract base with timestamps and soft-delete flag."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class Currency(BaseModel):
    """Supported currencies with exchange rate against TZS (base)."""

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=100)
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=1,
        help_text="Rate against TZS (1 unit of this currency = X TZS)",
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "currencies"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        if self.is_default:
            Currency.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """Immutable audit trail for all significant system actions."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    module = models.CharField(max_length=50)
    action = models.CharField(max_length=50)
    record_id = models.CharField(max_length=100, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["module", "action"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.module}.{self.action} by {self.user_id} at {self.created_at}"
