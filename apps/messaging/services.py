"""Messaging business logic."""

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.messaging.models import (
    AppNotification,
    Conversation,
    ConversationParticipant,
    Message,
    UserPresence,
)
from apps.users.models import Department, User


class MessagingService:
    SYSTEM_GROUPS = [
        ("Finance Team", "Finance"),
        ("Procurement Team", "Procurement"),
        ("Sales Team", "Sales"),
        ("Logistics Team", "Logistics"),
        ("Production Team", "Production"),
        ("Safety Team", "Safety"),
        ("HR & Admin Team", "HR & Admin"),
        ("All Staff", None),
        ("Management", None),
    ]

    MANAGEMENT_ROLES = (
        "General Manager",
        "HOD Finance",
        "HOD Procurement",
        "HOD Sales",
        "HOD Logistics",
        "Production Manager",
        "HR Officer",
    )

    @staticmethod
    def get_or_create_direct(user_a, user_b):
        if user_a.id == user_b.id:
            raise ValueError("Cannot message yourself")
        existing = (
            Conversation.objects.filter(
                conversation_type=Conversation.TYPE_DIRECT,
                participants__user=user_a,
            )
            .filter(participants__user=user_b)
            .annotate(pcount=Count("participants"))
            .filter(pcount=2)
            .first()
        )
        if existing:
            return existing
        with transaction.atomic():
            conv = Conversation.objects.create(
                conversation_type=Conversation.TYPE_DIRECT,
                created_by=user_a,
            )
            ConversationParticipant.objects.create(conversation=conv, user=user_a)
            ConversationParticipant.objects.create(conversation=conv, user=user_b)
        return conv

    @staticmethod
    def create_group(creator, name, member_ids):
        with transaction.atomic():
            conv = Conversation.objects.create(
                conversation_type=Conversation.TYPE_GROUP,
                name=name,
                created_by=creator,
            )
            member_ids = set(member_ids) | {creator.id}
            for uid in member_ids:
                ConversationParticipant.objects.create(
                    conversation=conv,
                    user_id=uid,
                    is_admin=(uid == creator.id),
                )
        return conv

    @staticmethod
    def unread_count(conversation, user):
        participant = conversation.participants.filter(user=user).first()
        if not participant:
            return 0
        qs = conversation.messages.filter(is_deleted=False).exclude(sender=user)
        if participant.last_read_at:
            qs = qs.filter(created_at__gt=participant.last_read_at)
        return qs.count()

    @staticmethod
    def mark_read(conversation, user):
        participant = conversation.participants.filter(user=user).first()
        if participant:
            participant.last_read_at = timezone.now()
            participant.save(update_fields=["last_read_at", "updated_at"])
        unread = conversation.messages.filter(is_deleted=False).exclude(sender=user)
        for msg in unread:
            readers = set(msg.read_by or [])
            if user.id not in readers:
                readers.add(user.id)
                msg.read_by = list(readers)
                msg.status = Message.STATUS_READ
                msg.save(update_fields=["read_by", "status", "updated_at"])

    @staticmethod
    def send_message(conversation, sender, body, **kwargs):
        create_kwargs = {
            "conversation": conversation,
            "sender": sender,
            "body": body,
            "message_type": kwargs.get("message_type", Message.TYPE_TEXT),
            "priority": kwargs.get("priority", Message.PRIORITY_NORMAL),
            "status": Message.STATUS_DELIVERED,
        }
        reply_to_id = kwargs.get("reply_to_id")
        if reply_to_id:
            create_kwargs["reply_to_id"] = reply_to_id
        msg = Message.objects.create(**create_kwargs)
        conversation.save(update_fields=["updated_at"])
        for p in conversation.participants.exclude(user=sender):
            AppNotification.objects.create(
                user=p.user,
                notification_type=AppNotification.TYPE_MESSAGE,
                title=f"New message from {sender.get_full_name()}",
                body=body[:120],
                icon="message",
                color="blue",
                reference_type="conversation",
                reference_id=conversation.id,
                navigate_to=f"/messaging?c={conversation.id}",
            )
        return msg

    @staticmethod
    def can_broadcast(user):
        if user.is_superuser:
            return True
        if not user.role:
            return False
        name = user.role.name
        if name in MessagingService.MANAGEMENT_ROLES or name == "Super Admin":
            return True
        return name.startswith("HOD ")

    @staticmethod
    @transaction.atomic
    def send_broadcast(sender, subject, body, recipients_type, priority, department_id=None, user_ids=None):
        if not MessagingService.can_broadcast(sender):
            raise PermissionError("Not authorized to send broadcasts")

        users = User.objects.filter(is_active=True)
        if recipients_type == "DEPARTMENT" and department_id:
            users = users.filter(department_id=department_id)
        elif recipients_type == "CUSTOM" and user_ids:
            users = users.filter(id__in=user_ids)
        # ALL — entire active staff (default queryset)

        conv = Conversation.objects.create(
            conversation_type=Conversation.TYPE_BROADCAST,
            name=subject,
            created_by=sender,
        )
        for u in users:
            ConversationParticipant.objects.create(conversation=conv, user=u)
        msg = Message.objects.create(
            conversation=conv,
            sender=sender,
            body=body,
            message_type=Message.TYPE_BROADCAST,
            priority=priority,
            status=Message.STATUS_DELIVERED,
        )
        for u in users.exclude(id=sender.id):
            AppNotification.objects.create(
                user=u,
                notification_type=AppNotification.TYPE_BROADCAST,
                title=f"[BROADCAST] {subject}",
                body=f"From {sender.get_full_name()}: {body[:100]}",
                icon="broadcast",
                color="orange",
                reference_type="conversation",
                reference_id=conv.id,
                navigate_to=f"/messaging?c={conv.id}",
            )
        return conv, msg

    @staticmethod
    def ensure_system_groups():
        for group_name, dept_name in MessagingService.SYSTEM_GROUPS:
            dept = None
            if dept_name:
                dept = Department.objects.filter(name=dept_name).first()
            conv, created = Conversation.objects.get_or_create(
                name=group_name,
                is_system_group=True,
                defaults={
                    "conversation_type": Conversation.TYPE_GROUP,
                    "department": dept,
                },
            )
            if group_name == "All Staff":
                users = User.objects.filter(is_active=True)
            elif group_name == "Management":
                users = User.objects.filter(is_active=True).filter(
                    Q(role__name__in=MessagingService.MANAGEMENT_ROLES)
                    | Q(is_superuser=True)
                )
            elif dept:
                users = User.objects.filter(is_active=True, department=dept)
            else:
                users = User.objects.none()
            for u in users:
                ConversationParticipant.objects.get_or_create(
                    conversation=conv, user=u
                )

    @staticmethod
    def set_online(user, online=True):
        presence, _ = UserPresence.objects.get_or_create(user=user)
        presence.is_online = online
        presence.last_seen = timezone.now()
        presence.save()
