"""Messaging API viewsets."""

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import api_error, api_response
from apps.messaging.mixins import MessagingViewSetMixin
from apps.messaging.models import AppNotification, Conversation, Message, MessageAttachment
from apps.messaging.serializers import (
    AppNotificationSerializer,
    BroadcastSerializer,
    ConversationSerializer,
    CreateDirectSerializer,
    CreateGroupSerializer,
    MessageSerializer,
    SendMessageSerializer,
)
from apps.messaging.services import MessagingService
from apps.users.models import User


class ConversationViewSet(MessagingViewSetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        user = self.request.user
        return (
            Conversation.objects.filter(participants__user=user, is_active=True)
            .prefetch_related("participants__user", "messages")
            .distinct()
            .order_by("-updated_at")
        )

    @action(detail=False, methods=["post"], url_path="direct")
    def create_direct(self, request):
        ser = CreateDirectSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            other = User.objects.get(pk=ser.validated_data["user_id"])
            conv = MessagingService.get_or_create_direct(request.user, other)
        except User.DoesNotExist:
            return api_error(message="User not found", status=404)
        except ValueError as e:
            return api_error(message=str(e))
        return api_response(
            data=ConversationSerializer(conv, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="group")
    def create_group(self, request):
        ser = CreateGroupSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        conv = MessagingService.create_group(
            request.user,
            ser.validated_data["name"],
            ser.validated_data["member_ids"],
        )
        return api_response(
            data=ConversationSerializer(conv, context={"request": request}).data,
            message="Group created",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        conv = self.get_object()
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 50))
        qs = conv.messages.filter(is_deleted=False).order_by("-created_at")
        total = qs.count()
        start = (page - 1) * page_size
        items = list(qs[start : start + page_size])
        items.reverse()
        return api_response(
            data={
                "count": total,
                "page": page,
                "page_size": page_size,
                "results": MessageSerializer(items, many=True).data,
            }
        )

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        conv = self.get_object()
        ser = SendMessageSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        msg = MessagingService.send_message(
            conv,
            request.user,
            ser.validated_data.get("body", ""),
            message_type=ser.validated_data.get("message_type", Message.TYPE_TEXT),
            priority=ser.validated_data.get("priority", Message.PRIORITY_NORMAL),
            reply_to_id=ser.validated_data.get("reply_to_id"),
        )
        from apps.messaging.consumers import broadcast_message_event

        broadcast_message_event(conv.id, MessageSerializer(msg).data)
        return api_response(data=MessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        conv = self.get_object()
        MessagingService.mark_read(conv, request.user)
        return api_response(message="Marked as read")

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser, JSONParser])
    def upload(self, request, pk=None):
        conv = self.get_object()
        uploaded = request.FILES.get("file")
        if not uploaded:
            return api_error(message="No file uploaded")
        if uploaded.size > 10 * 1024 * 1024:
            return api_error(message="Max file size 10MB")
        msg_type = Message.TYPE_IMAGE if uploaded.content_type.startswith("image/") else Message.TYPE_FILE
        msg = MessagingService.send_message(
            conv, request.user, uploaded.name, message_type=msg_type
        )
        path = f"messaging/{conv.id}/{uploaded.name}"
        from django.core.files.storage import default_storage

        saved = default_storage.save(path, uploaded)
        MessageAttachment.objects.create(
            message=msg,
            file_name=uploaded.name,
            file_path=default_storage.url(saved),
            file_size=uploaded.size,
            file_type=uploaded.content_type or "",
        )
        from apps.messaging.consumers import broadcast_message_event

        broadcast_message_event(conv.id, MessageSerializer(msg).data)
        return api_response(data=MessageSerializer(msg).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"messages/(?P<message_id>[^/.]+)")
    def delete_message(self, request, pk=None, message_id=None):
        conv = self.get_object()
        try:
            msg = conv.messages.get(pk=message_id)
        except Message.DoesNotExist:
            return api_error(message="Message not found", status=404)
        if msg.sender_id != request.user.id and not request.user.is_superuser:
            return api_error(message="Cannot delete this message", status=403)
        msg.is_deleted = True
        msg.save(update_fields=["is_deleted", "updated_at"])
        return api_response(message="Message deleted")


class BroadcastViewSet(MessagingViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def create(self, request):
        ser = BroadcastSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            conv, msg = MessagingService.send_broadcast(
                request.user,
                ser.validated_data["subject"],
                ser.validated_data["body"],
                ser.validated_data["recipients_type"],
                ser.validated_data["priority"],
                ser.validated_data.get("department_id"),
                ser.validated_data.get("user_ids"),
            )
        except PermissionError as e:
            return api_error(message=str(e), status=403)
        return api_response(
            data={
                "conversation": ConversationSerializer(conv, context={"request": request}).data,
                "message": MessageSerializer(msg).data,
            },
            message="Broadcast sent",
            status=status.HTTP_201_CREATED,
        )


class NotificationViewSet(MessagingViewSetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = AppNotificationSerializer

    def get_queryset(self):
        qs = AppNotification.objects.filter(user=self.request.user, is_active=True)
        if self.request.query_params.get("unread_only") == "true":
            qs = qs.filter(is_read=False)
        return qs

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        messages = AppNotification.objects.filter(
            user=request.user, is_read=False, notification_type=AppNotification.TYPE_MESSAGE
        ).count()
        total = AppNotification.objects.filter(user=request.user, is_read=False).count()
        conv_unread = 0
        for conv in Conversation.objects.filter(participants__user=request.user):
            conv_unread += MessagingService.unread_count(conv, request.user)
        return api_response(
            data={"messages": conv_unread, "notifications": total, "total": conv_unread + total}
        )

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        n = self.get_object()
        n.is_read = True
        n.save(update_fields=["is_read", "updated_at"])
        return api_response(data=AppNotificationSerializer(n).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        AppNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return api_response(message="All notifications marked read")
