"""Shared ViewSet behaviour for sales API endpoints."""

from apps.core.drf_backends import FMSDjangoFilterBackend, FMSOrderingFilter, FMSSearchFilter
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import HasModulePermission
from apps.core.responses import api_error, api_response


class SalesViewSetMixin:
    """Standard FMS response envelope and RBAC for sales viewsets."""

    module_name = "sales"
    filter_backends = [FMSDjangoFilterBackend, FMSSearchFilter, FMSOrderingFilter]

    def get_required_action(self):
        if self.action in ("approve", "apply"):
            return "approve"
        if self.action in (
            "create",
            "send",
            "convert",
            "duplicate",
            "confirm",
            "cancel",
            "issue",
            "record",
            "submit",
            "verify_stock",
            "create_procurement",
            "send_to_logistics",
            "delivery_cost",
            "send_quotation",
            "accept_quotation",
            "reject_quotation",
            "generate_invoice",
            "submit_payment",
            "verify_payment",
            "set_delivery_method",
            "assign_vehicle",
            "assign_third_party",
            "dispatch_order",
            "confirm_pickup",
            "confirm_delivery",
            "logistics_confirm",
            "close",
        ):
            return "create"
        if self.action in ("update", "partial_update"):
            return "update"
        if self.action == "destroy":
            return "delete"
        return "read"

    def get_permissions(self):
        self.required_action = self.get_required_action()
        if self.action in ("list", "retrieve", "statement"):
            return [IsAuthenticated()]
        if self.action in ("approve", "apply"):
            return [IsAuthenticated(), HasModulePermission()]
        return [IsAuthenticated(), HasModulePermission()]

    def perform_destroy(self, instance):
        if hasattr(instance, "is_active"):
            instance.is_active = False
            instance.save()
        else:
            instance.delete()

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
            message=self.get_create_message(),
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        self.perform_update(serializer)
        return api_response(data=serializer.data, message=self.get_update_message())

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_response(message=self.get_destroy_message())

    def get_create_message(self):
        return "Record created"

    def get_update_message(self):
        return "Record updated"

    def get_destroy_message(self):
        return "Record deactivated"
