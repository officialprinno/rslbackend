"""Core serializers."""

from rest_framework import serializers

from apps.core.models import AuditLog, Currency


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = [
            "id",
            "code",
            "name",
            "exchange_rate",
            "is_default",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user",
            "user_name",
            "module",
            "action",
            "record_id",
            "old_values",
            "new_values",
            "ip_address",
            "created_at",
        ]

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None
