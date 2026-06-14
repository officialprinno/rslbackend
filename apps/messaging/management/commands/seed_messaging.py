"""Seed internal messaging conversations and messages."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.messaging.models import AppNotification, Conversation, Message
from apps.messaging.services import MessagingService
from apps.users.models import User


class Command(BaseCommand):
    help = "Seed messaging conversations, groups, and sample messages"

    @transaction.atomic
    def handle(self, *args, **options):
        MessagingService.ensure_system_groups()
        users = list(User.objects.filter(is_active=True).order_by("id")[:8])
        if len(users) < 2:
            self.stdout.write(self.style.WARNING("Need at least 2 users — run seed_fms first"))
            return

        u1, u2 = users[0], users[1]
        dm = MessagingService.get_or_create_direct(u1, u2)
        if not dm.messages.exists():
            MessagingService.send_message(dm, u1, "Please review the Q3 procurement report when you have a moment.")
            MessagingService.send_message(dm, u2, "Invoice approved ✓ — I'll send the updated figures shortly.")
            self.stdout.write(f"  DM: {u1.get_full_name()} <-> {u2.get_full_name()}")

        finance = Conversation.objects.filter(name="Finance Team", is_system_group=True).first()
        if finance and not finance.messages.exists():
            MessagingService.send_message(finance, u1, "Q3 report ready for review.")
            self.stdout.write("  Finance Team group message")

        all_staff = Conversation.objects.filter(name="All Staff", is_system_group=True).first()
        if all_staff and not all_staff.messages.filter(message_type=Message.TYPE_BROADCAST).exists():
            if MessagingService.can_broadcast(u1):
                MessagingService.send_broadcast(
                    u1,
                    "Safety Reminder",
                    "Remember to wear PPE in all production areas.",
                    "ALL",
                    Message.PRIORITY_HIGH,
                )
                self.stdout.write("  Broadcast: Safety Reminder")

        for user in users[:3]:
            AppNotification.objects.get_or_create(
                user=user,
                title="Welcome to RSL Messaging",
                defaults={
                    "notification_type": AppNotification.TYPE_SYSTEM,
                    "body": "Internal messaging is now available.",
                    "icon": "bell",
                    "color": "blue",
                    "navigate_to": "/messaging",
                },
            )

        self.stdout.write(self.style.SUCCESS("Messaging seed complete"))
