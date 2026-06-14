"""External email client models."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class EmailAccount(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_account",
    )
    email_address = models.EmailField()
    display_name = models.CharField(max_length=150, blank=True)
    imap_host = models.CharField(max_length=255, default="mail.rocksolutions.co.tz")
    imap_port = models.PositiveIntegerField(default=993)
    imap_use_ssl = models.BooleanField(default=True)
    smtp_host = models.CharField(max_length=255, default="mail.rocksolutions.co.tz")
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_use_tls = models.BooleanField(default=True)
    username = models.CharField(max_length=255, blank=True)
    password_encrypted = models.TextField(blank=True)
    sync_frequency = models.PositiveIntegerField(default=5)
    sync_days = models.PositiveIntegerField(default=30)
    max_per_sync = models.PositiveIntegerField(default=50)
    last_synced = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["email_address"]


class EmailLabel(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_labels",
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, default="blue")

    class Meta:
        unique_together = [("user", "name")]
        ordering = ["name"]


class EmailMessage(BaseModel):
    FOLDER_INBOX = "INBOX"
    FOLDER_SENT = "SENT"
    FOLDER_DRAFT = "DRAFT"
    FOLDER_TRASH = "TRASH"
    FOLDER_SPAM = "SPAM"
    FOLDER_CHOICES = [
        (FOLDER_INBOX, "Inbox"),
        (FOLDER_SENT, "Sent"),
        (FOLDER_DRAFT, "Draft"),
        (FOLDER_TRASH, "Trash"),
        (FOLDER_SPAM, "Spam"),
    ]

    DIRECTION_IN = "INBOUND"
    DIRECTION_OUT = "OUTBOUND"
    DIRECTION_CHOICES = [
        (DIRECTION_IN, "Inbound"),
        (DIRECTION_OUT, "Outbound"),
    ]

    email_account = models.ForeignKey(
        EmailAccount, on_delete=models.CASCADE, related_name="messages"
    )
    message_id = models.CharField(max_length=255, blank=True)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    from_address = models.EmailField()
    from_name = models.CharField(max_length=255, blank=True)
    to_addresses = models.JSONField(default=list)
    cc_addresses = models.JSONField(default=list, blank=True)
    bcc_addresses = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body_html = models.TextField(blank=True)
    body_text = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    folder = models.CharField(max_length=20, choices=FOLDER_CHOICES, default=FOLDER_INBOX)
    thread_id = models.CharField(max_length=255, blank=True, null=True)
    has_attachments = models.BooleanField(default=False)
    received_at = models.DateTimeField()
    labels = models.ManyToManyField(EmailLabel, blank=True, related_name="emails")
    linked_customer_id = models.PositiveIntegerField(null=True, blank=True)
    linked_supplier_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]


class EmailAttachment(BaseModel):
    email = models.ForeignKey(
        EmailMessage, on_delete=models.CASCADE, related_name="attachments"
    )
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    file_type = models.CharField(max_length=100, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
