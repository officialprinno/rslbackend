"""Email client serializers."""

from rest_framework import serializers

from apps.email_client.models import EmailAccount, EmailAttachment, EmailLabel, EmailMessage


class EmailLabelSerializer(serializers.ModelSerializer):
    emails_count = serializers.SerializerMethodField()

    class Meta:
        model = EmailLabel
        fields = ["id", "user_id", "name", "color", "emails_count"]

    def get_emails_count(self, obj):
        return obj.emails.filter(is_deleted=False).count()


class EmailAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailAttachment
        fields = ["id", "email_id", "file_name", "file_path", "file_size", "file_type", "content_type"]


class EmailMessageSerializer(serializers.ModelSerializer):
    attachments = EmailAttachmentSerializer(many=True, read_only=True)
    labels = EmailLabelSerializer(many=True, read_only=True)

    class Meta:
        model = EmailMessage
        fields = [
            "id", "email_account_id", "message_id", "direction",
            "from_address", "from_name", "to_addresses", "cc_addresses", "bcc_addresses",
            "subject", "body_html", "body_text", "is_read", "is_starred", "is_deleted",
            "folder", "thread_id", "thread_count", "labels", "attachments",
            "has_attachments", "received_at", "created_at",
            "linked_customer_id", "linked_supplier_id",
        ]
        read_only_fields = ["message_id", "direction"]

    thread_count = serializers.SerializerMethodField()

    def get_thread_count(self, obj):
        if not obj.thread_id:
            return 1
        return EmailMessage.objects.filter(thread_id=obj.thread_id, is_deleted=False).count()


class EmailAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailAccount
        fields = [
            "id", "user_id", "email_address", "display_name",
            "imap_host", "imap_port", "imap_use_ssl",
            "smtp_host", "smtp_port", "smtp_use_tls",
            "username", "sync_frequency", "sync_days", "max_per_sync",
            "is_active", "last_synced", "created_at",
        ]
        read_only_fields = ["user_id", "last_synced"]


class EmailAccountSetupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = EmailAccount
        fields = [
            "email_address", "display_name",
            "imap_host", "imap_port", "imap_use_ssl",
            "smtp_host", "smtp_port", "smtp_use_tls",
            "username", "password",
            "sync_frequency", "sync_days", "max_per_sync",
        ]

    def create(self, validated_data):
        password = validated_data.pop("password", "")
        validated_data["password_encrypted"] = password
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.password_encrypted = password
        return super().update(instance, validated_data)


class ComposeEmailSerializer(serializers.Serializer):
    to = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    cc = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    bcc = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    subject = serializers.CharField(max_length=500)
    body_html = serializers.CharField()
    body_text = serializers.CharField(required=False, allow_blank=True, default="")
    reply_to_id = serializers.IntegerField(required=False, allow_null=True)
    forward_of_id = serializers.IntegerField(required=False, allow_null=True)
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)


class LabelCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailLabel
        fields = ["name", "color"]
