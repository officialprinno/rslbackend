"""Email client API."""

from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import api_error, api_response
from apps.email_client.mixins import EmailViewSetMixin
from apps.email_client.models import EmailAccount, EmailLabel, EmailMessage
from apps.email_client.serializers import (
    ComposeEmailSerializer,
    EmailAccountSerializer,
    EmailAccountSetupSerializer,
    EmailLabelSerializer,
    EmailMessageSerializer,
    LabelCreateSerializer,
)
from apps.email_client.services import EmailService


class EmailAccountViewSet(EmailViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def account(self, request):
        acc = EmailAccount.objects.filter(user=request.user).first()
        if not acc:
            return api_response(data=None)
        return api_response(data=EmailAccountSerializer(acc).data)

    @action(detail=False, methods=["post"], url_path="setup")
    def setup(self, request):
        acc = EmailAccount.objects.filter(user=request.user).first()
        ser = EmailAccountSetupSerializer(
            instance=acc, data=request.data, context={"request": request}
        )
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        acc = ser.save()
        return api_response(data=EmailAccountSerializer(acc).data, message="Account saved")

    @action(detail=False, methods=["post"], url_path="test-connection")
    def test_connection(self, request):
        result = EmailService.test_connection(request.data)
        if result["success"]:
            return api_response(data=result, message="Connection successful")
        return api_response(data=result, message="Connection failed", success=False)

    @action(detail=False, methods=["post"])
    def sync(self, request):
        acc = EmailAccount.objects.filter(user=request.user).first()
        if not acc:
            return api_error(message="No email account configured", status=404)
        result = EmailService.sync_account(acc)
        return api_response(data=result, message="Sync complete")


class EmailMessageViewSet(EmailViewSetMixin, viewsets.ModelViewSet):
    serializer_class = EmailMessageSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = EmailMessage.objects.filter(
            email_account__user=user, is_deleted=False
        ).prefetch_related("labels", "attachments")
        folder = self.request.query_params.get("folder")
        if folder:
            qs = qs.filter(folder=folder.upper())
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(is_read=False)
        if self.request.query_params.get("starred") == "true":
            qs = qs.filter(is_starred=True)
        if self.request.query_params.get("has_attachment") == "true":
            qs = qs.filter(has_attachments=True)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(subject__icontains=search)
                | Q(from_name__icontains=search)
                | Q(from_address__icontains=search)
                | Q(body_text__icontains=search)
            )
        label_id = self.request.query_params.get("label")
        if label_id:
            qs = qs.filter(labels__id=label_id)
        sort = self.request.query_params.get("sort", "date")
        if sort == "from":
            qs = qs.order_by("from_name", "-received_at")
        elif sort == "subject":
            qs = qs.order_by("subject", "-received_at")
        else:
            qs = qs.order_by("-received_at")
        return qs

    def destroy(self, request, *args, **kwargs):
        email = self.get_object()
        email.is_deleted = True
        email.folder = EmailMessage.FOLDER_TRASH
        email.save(update_fields=["is_deleted", "folder", "updated_at"])
        return api_response(message="Moved to trash")

    @action(detail=False, methods=["post"])
    def send(self, request):
        acc = EmailAccount.objects.filter(user=request.user).first()
        if not acc:
            return api_error(message="Configure email account first", status=400)
        ser = ComposeEmailSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        if ser.validated_data.get("scheduled_at"):
            email = EmailMessage.objects.create(
                email_account=acc,
                message_id=f"draft-{timezone_now()}",
                direction=EmailMessage.DIRECTION_OUT,
                from_address=acc.email_address,
                from_name=acc.display_name or "",
                to_addresses=ser.validated_data["to"],
                cc_addresses=ser.validated_data.get("cc", []),
                bcc_addresses=ser.validated_data.get("bcc", []),
                subject=ser.validated_data["subject"],
                body_html=ser.validated_data["body_html"],
                body_text=ser.validated_data.get("body_text", ""),
                folder=EmailMessage.FOLDER_DRAFT,
                received_at=timezone_now(),
            )
            return api_response(data=EmailMessageSerializer(email).data, message="Scheduled/Draft saved")
        email = EmailService.send_email(acc, ser.validated_data)
        return api_response(
            data=EmailMessageSerializer(email).data,
            message="Email sent",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        email = self.get_object()
        email.is_read = True
        email.save(update_fields=["is_read", "updated_at"])
        return api_response(data=EmailMessageSerializer(email).data)

    @action(detail=True, methods=["post"], url_path="mark-unread")
    def mark_unread(self, request, pk=None):
        email = self.get_object()
        email.is_read = False
        email.save(update_fields=["is_read", "updated_at"])
        return api_response(data=EmailMessageSerializer(email).data)

    @action(detail=True, methods=["post"])
    def star(self, request, pk=None):
        email = self.get_object()
        email.is_starred = True
        email.save(update_fields=["is_starred", "updated_at"])
        return api_response(data=EmailMessageSerializer(email).data)

    @action(detail=True, methods=["post"], url_path="unstar")
    def unstar(self, request, pk=None):
        email = self.get_object()
        email.is_starred = False
        email.save(update_fields=["is_starred", "updated_at"])
        return api_response(data=EmailMessageSerializer(email).data)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        folder = request.data.get("folder", "").upper()
        if folder not in dict(EmailMessage.FOLDER_CHOICES):
            return api_error(message="Invalid folder")
        email = self.get_object()
        email.folder = folder
        email.save(update_fields=["folder", "updated_at"])
        return api_response(data=EmailMessageSerializer(email).data)

    @action(detail=True, methods=["post"], url_path="apply-label")
    def apply_label(self, request, pk=None):
        label_id = request.data.get("label_id")
        email = self.get_object()
        label = EmailLabel.objects.filter(user=request.user, pk=label_id).first()
        if not label:
            return api_error(message="Label not found", status=404)
        email.labels.add(label)
        return api_response(data=EmailMessageSerializer(email).data)

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request):
        ids = request.data.get("ids", [])
        action_name = request.data.get("action")
        emails = EmailMessage.objects.filter(
            pk__in=ids, email_account__user=request.user
        )
        if action_name == "mark_read":
            emails.update(is_read=True)
        elif action_name == "mark_unread":
            emails.update(is_read=False)
        elif action_name == "star":
            emails.update(is_starred=True)
        elif action_name == "delete":
            emails.update(is_deleted=True, folder=EmailMessage.FOLDER_TRASH)
        elif action_name == "move":
            folder = request.data.get("folder", "").upper()
            emails.update(folder=folder)
        elif action_name == "apply_label":
            label_id = request.data.get("label_id")
            label = EmailLabel.objects.filter(user=request.user, pk=label_id).first()
            if label:
                for e in emails:
                    e.labels.add(label)
        return api_response(message=f"Bulk {action_name} complete")

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        inbox = EmailMessage.objects.filter(
            email_account__user=request.user,
            folder=EmailMessage.FOLDER_INBOX,
            is_read=False,
            is_deleted=False,
        ).count()
        total = EmailMessage.objects.filter(
            email_account__user=request.user, is_read=False, is_deleted=False
        ).count()
        return api_response(data={"inbox": inbox, "total": total})


class EmailLabelViewSet(EmailViewSetMixin, viewsets.ModelViewSet):
    serializer_class = EmailLabelSerializer

    def get_queryset(self):
        return EmailLabel.objects.filter(user=self.request.user, is_active=True)

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return LabelCreateSerializer
        return EmailLabelSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return api_response(data=response.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_create(serializer)
        return api_response(
            data=EmailLabelSerializer(serializer.instance).data,
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        label = self.get_object()
        label.is_active = False
        label.save(update_fields=["is_active", "updated_at"])
        return api_response(message="Label deleted")


def timezone_now():
    from django.utils import timezone

    return timezone.now()
