"""Internal messaging models."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Conversation(BaseModel):
    TYPE_DIRECT = "DIRECT"
    TYPE_GROUP = "GROUP"
    TYPE_BROADCAST = "BROADCAST"
    TYPE_CHOICES = [
        (TYPE_DIRECT, "Direct"),
        (TYPE_GROUP, "Group"),
        (TYPE_BROADCAST, "Broadcast"),
    ]

    conversation_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    name = models.CharField(max_length=255, blank=True, null=True)
    avatar = models.CharField(max_length=500, blank=True, null=True)
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messaging_groups",
    )
    is_system_group = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations_created",
    )

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name or f"{self.conversation_type} #{self.pk}"


class ConversationParticipant(BaseModel):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_memberships",
    )
    is_admin = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("conversation", "user")]


class Message(BaseModel):
    TYPE_TEXT = "TEXT"
    TYPE_FILE = "FILE"
    TYPE_IMAGE = "IMAGE"
    TYPE_SYSTEM = "SYSTEM"
    TYPE_BROADCAST = "BROADCAST"
    TYPE_CHOICES = [
        (TYPE_TEXT, "Text"),
        (TYPE_FILE, "File"),
        (TYPE_IMAGE, "Image"),
        (TYPE_SYSTEM, "System"),
        (TYPE_BROADCAST, "Broadcast"),
    ]

    PRIORITY_NORMAL = "NORMAL"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_URGENT = "URGENT"
    PRIORITY_CHOICES = [
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    STATUS_SENT = "SENT"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_READ = "READ"
    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_READ, "Read"),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages_sent",
    )
    body = models.TextField(blank=True)
    message_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_TEXT)
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL
    )
    reply_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies"
    )
    read_by = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SENT)
    is_deleted = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]


class MessageAttachment(BaseModel):
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="attachments"
    )
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.PositiveIntegerField(default=0)
    file_type = models.CharField(max_length=100, blank=True)
    thumbnail_url = models.CharField(max_length=500, blank=True, null=True)


class UserPresence(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="presence",
    )
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(auto_now=True)


class AppNotification(BaseModel):
    TYPE_MESSAGE = "MESSAGE"
    TYPE_BROADCAST = "BROADCAST"
    TYPE_APPROVAL = "APPROVAL"
    TYPE_ALERT = "ALERT"
    TYPE_SYSTEM = "SYSTEM"
    TYPE_CHOICES = [
        (TYPE_MESSAGE, "Message"),
        (TYPE_BROADCAST, "Broadcast"),
        (TYPE_APPROVAL, "Approval"),
        (TYPE_ALERT, "Alert"),
        (TYPE_SYSTEM, "System"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="app_notifications",
    )
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, default="bell")
    color = models.CharField(max_length=30, blank=True, default="blue")
    reference_type = models.CharField(max_length=50, blank=True, null=True)
    reference_id = models.PositiveIntegerField(null=True, blank=True)
    navigate_to = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
