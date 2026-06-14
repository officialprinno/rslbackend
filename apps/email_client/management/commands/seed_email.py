"""Seed email client with sample inbox data."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.email_client.models import EmailAccount, EmailAttachment, EmailLabel, EmailMessage
from apps.users.models import User

SAMPLE_EMAILS = [
    {
        "from_name": "John Mining Co.",
        "from_address": "accounts@johnmining.co.tz",
        "subject": "Invoice for Q3 2024",
        "body_text": "Please find attached our invoice for Q3 2024 services.",
        "folder": EmailMessage.FOLDER_INBOX,
        "has_attachments": True,
        "is_starred": True,
    },
    {
        "from_name": "Supplier ABC Ltd",
        "from_address": "sales@supplierabc.co.tz",
        "subject": "Quotation - Oct 2024",
        "body_text": "Dear Sir/Madam, please find our quotation attached.",
        "folder": EmailMessage.FOLDER_INBOX,
        "has_attachments": True,
    },
    {
        "from_name": "HR Department",
        "from_address": "hr@rocksolutions.co.tz",
        "subject": "Leave policy update",
        "body_text": "Please review the updated leave policy document.",
        "folder": EmailMessage.FOLDER_INBOX,
    },
]

DEFAULT_LABELS = [
    ("Clients", "blue"),
    ("Suppliers", "green"),
    ("Invoices", "yellow"),
    ("Urgent", "red"),
]


class Command(BaseCommand):
    help = "Seed email accounts, labels, and sample messages"

    @transaction.atomic
    def handle(self, *args, **options):
        user = User.objects.filter(is_active=True).first()
        if not user:
            self.stdout.write(self.style.WARNING("No users found"))
            return

        email_addr = f"{user.first_name.lower()}.{user.last_name.lower()}@rocksolutions.co.tz"
        account, _ = EmailAccount.objects.get_or_create(
            user=user,
            defaults={
                "email_address": email_addr,
                "display_name": user.get_full_name(),
                "username": email_addr,
                "last_synced": timezone.now(),
            },
        )

        labels = {}
        for name, color in DEFAULT_LABELS:
            lbl, _ = EmailLabel.objects.get_or_create(
                user=user, name=name, defaults={"color": color}
            )
            labels[name] = lbl

        now = timezone.now()
        for i, data in enumerate(SAMPLE_EMAILS):
            msg, created = EmailMessage.objects.get_or_create(
                email_account=account,
                subject=data["subject"],
                from_address=data["from_address"],
                defaults={
                    "message_id": f"seed-{i}-{now.timestamp()}",
                    "direction": EmailMessage.DIRECTION_IN,
                    "from_name": data["from_name"],
                    "to_addresses": [{"name": user.get_full_name(), "email": email_addr}],
                    "body_html": f"<p>{data['body_text']}</p>",
                    "body_text": data["body_text"],
                    "folder": data["folder"],
                    "has_attachments": data.get("has_attachments", False),
                    "is_starred": data.get("is_starred", False),
                    "is_read": i > 0,
                    "received_at": now - timedelta(hours=i * 5),
                    "thread_id": f"thread-{i}" if i < 2 else None,
                },
            )
            if created and data.get("has_attachments"):
                EmailAttachment.objects.create(
                    email=msg,
                    file_name="document.pdf",
                    file_path="/media/email/document.pdf",
                    file_size=245000,
                    file_type="pdf",
                    content_type="application/pdf",
                )
            if created and "Mining" in data["from_name"]:
                msg.labels.add(labels["Clients"])
            if created and "Supplier" in data["from_name"]:
                msg.labels.add(labels["Suppliers"])

        EmailMessage.objects.get_or_create(
            email_account=account,
            subject="Draft: Follow up with client",
            folder=EmailMessage.FOLDER_DRAFT,
            defaults={
                "message_id": f"draft-{now.timestamp()}",
                "direction": EmailMessage.DIRECTION_OUT,
                "from_address": email_addr,
                "from_name": user.get_full_name(),
                "to_addresses": [{"name": "Client", "email": "client@example.co.tz"}],
                "body_html": "<p>Dear client,</p>",
                "body_text": "Dear client,",
                "received_at": now,
            },
        )

        self.stdout.write(self.style.SUCCESS(f"Email seed complete for {email_addr}"))
