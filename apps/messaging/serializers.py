"""Messaging serializers."""

from rest_framework import serializers

from apps.messaging.models import (
    AppNotification,
    Conversation,
    ConversationParticipant,
    Message,
    MessageAttachment,
    UserPresence,
)
from apps.messaging.services import MessagingService


class ParticipantSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    role_name = serializers.CharField(source="user.role_name", read_only=True)
    department_name = serializers.CharField(source="user.department_name", read_only=True)
    is_online = serializers.SerializerMethodField()

    class Meta:
        model = ConversationParticipant
        fields = [
            "user_id", "full_name", "role_name", "department_name",
            "is_admin", "is_muted", "is_online",
        ]

    def get_is_online(self, obj):
        try:
            return obj.user.presence.is_online
        except UserPresence.DoesNotExist:
            return False


class MessageAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageAttachment
        fields = ["id", "file_name", "file_path", "file_size", "file_type", "thumbnail_url"]


class MessageSerializer(serializers.ModelSerializer):
    conversation_id = serializers.IntegerField(source="conversation.id", read_only=True)
    sender_id = serializers.IntegerField(source="sender.id", read_only=True, allow_null=True)
    sender_name = serializers.SerializerMethodField()
    sender_avatar = serializers.SerializerMethodField()
    reply_to_preview = serializers.SerializerMethodField()
    attachments = MessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            "id", "conversation_id", "sender_id", "sender_name", "sender_avatar",
            "body", "message_type", "priority", "reply_to_id", "reply_to_preview",
            "attachments", "read_by", "status", "created_at", "is_deleted", "is_starred",
        ]
        read_only_fields = ["sender_id", "status", "read_by"]

    def get_sender_name(self, obj):
        return obj.sender.get_full_name() if obj.sender else "System"

    def get_sender_avatar(self, obj):
        if obj.sender and obj.sender.profile_photo:
            return obj.sender.profile_photo.url
        return None

    def get_reply_to_preview(self, obj):
        if obj.reply_to_id and obj.reply_to:
            return obj.reply_to.body[:100]
        return None


class ConversationSerializer(serializers.ModelSerializer):
    participants = ParticipantSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id", "type", "name", "avatar", "participants",
            "last_message", "unread_count", "is_muted", "created_at",
        ]

    type = serializers.CharField(source="conversation_type", read_only=True)
    is_muted = serializers.SerializerMethodField()

    def get_last_message(self, obj):
        msg = obj.messages.filter(is_deleted=False).order_by("-created_at").first()
        return MessageSerializer(msg).data if msg else None

    def get_unread_count(self, obj):
        user = self.context["request"].user
        return MessagingService.unread_count(obj, user)

    def get_is_muted(self, obj):
        user = self.context["request"].user
        p = obj.participants.filter(user=user).first()
        return p.is_muted if p else False


class SendMessageSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True)
    message_type = serializers.ChoiceField(
        choices=Message.TYPE_CHOICES, default=Message.TYPE_TEXT
    )
    priority = serializers.ChoiceField(
        choices=Message.PRIORITY_CHOICES, default=Message.PRIORITY_NORMAL
    )
    reply_to_id = serializers.IntegerField(required=False, allow_null=True)


class CreateGroupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    member_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class CreateDirectSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()


class BroadcastSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField()
    recipients_type = serializers.ChoiceField(
        choices=[("ALL", "All Staff"), ("DEPARTMENT", "Department"), ("CUSTOM", "Custom")]
    )
    department_id = serializers.IntegerField(required=False, allow_null=True)
    user_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_null=True
    )
    priority = serializers.ChoiceField(
        choices=Message.PRIORITY_CHOICES, default=Message.PRIORITY_NORMAL
    )


class AppNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppNotification
        fields = [
            "id", "type", "title", "body", "icon", "color",
            "reference_type", "reference_id", "navigate_to", "is_read", "created_at",
        ]

    type = serializers.CharField(source="notification_type", read_only=True)
