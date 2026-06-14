from django.contrib import admin

from apps.core.models import AuditLog, Currency


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "exchange_rate", "is_default", "is_active")
    list_filter = ("is_default", "is_active")
    search_fields = ("code", "name")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("module", "action", "user", "record_id", "ip_address", "created_at")
    list_filter = ("module", "action", "created_at")
    search_fields = ("module", "action", "record_id")
    readonly_fields = (
        "user",
        "module",
        "action",
        "record_id",
        "old_values",
        "new_values",
        "ip_address",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
