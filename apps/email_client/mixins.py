"""Email ViewSet mixin."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import HasModulePermission
from apps.core.responses import api_error, api_response


class EmailViewSetMixin:
    module_name = "email"
    permission_classes = [IsAuthenticated, HasModulePermission]

    def get_permissions(self):
        self.required_action = "read"
        if self.action in ("create", "send", "setup", "sync", "test_connection", "compose"):
            self.required_action = "create"
        elif self.action in ("update", "partial_update", "mark_read", "mark_unread", "star", "bulk"):
            self.required_action = "update"
        elif self.action == "destroy":
            self.required_action = "delete"
        if self.action in ("list", "retrieve", "unread_count", "account"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), HasModulePermission()]

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
            data=serializer.data,
            message="Created",
            status=status.HTTP_201_CREATED,
        )
