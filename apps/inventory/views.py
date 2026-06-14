"""
Inventory API viewsets for Rock Solutions FMS.
"""

from decimal import Decimal

from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import HasModulePermission
from apps.core.responses import api_error, api_response
from apps.inventory.filters import (
    ItemCategoryFilter,
    ItemFilter,
    ItemSerialNumberFilter,
    StockAdjustmentFilter,
    StockAlertFilter,
    StockFilter,
    StockMovementFilter,
)
from apps.inventory.mixins import InventoryViewSetMixin
from apps.inventory.models import (
    Item,
    ItemCategory,
    ItemSerialNumber,
    Stock,
    StockAdjustment,
    StockAlert,
    StockMovement,
    Warehouse,
)
from apps.inventory.serializers import (
    ItemCategorySerializer,
    ItemSerializer,
    ItemSerialNumberSerializer,
    StockAdjustmentApproveSerializer,
    StockAdjustmentSerializer,
    StockAlertSerializer,
    StockMovementSerializer,
    StockSerializer,
    StockSummarySerializer,
    WarehouseSerializer,
)


class ItemCategoryViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    """CRUD for hierarchical item categories."""

    queryset = ItemCategory.objects.select_related("parent").all()
    serializer_class = ItemCategorySerializer
    filterset_class = ItemCategoryFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]

    def get_create_message(self):
        return "Item category created"

    def get_update_message(self):
        return "Item category updated"

    def get_destroy_message(self):
        return "Item category deactivated"


class ItemViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    """CRUD for inventory items."""

    queryset = Item.objects.select_related("category", "currency").all()
    serializer_class = ItemSerializer
    filterset_class = ItemFilter
    search_fields = ["code", "name", "description"]
    ordering_fields = ["code", "name", "unit_cost", "created_at"]

    def get_create_message(self):
        return "Item created"

    def get_update_message(self):
        return "Item updated"

    def get_destroy_message(self):
        return "Item deactivated"


class WarehouseViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    """CRUD for warehouses."""

    queryset = Warehouse.objects.select_related("manager").all()
    serializer_class = WarehouseSerializer
    filterset_fields = ["is_active", "manager"]
    search_fields = ["name", "location"]
    ordering_fields = ["name", "created_at"]

    def get_create_message(self):
        return "Warehouse created"

    def get_update_message(self):
        return "Warehouse updated"

    def get_destroy_message(self):
        return "Warehouse deactivated"


class StockViewSet(InventoryViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only stock levels.

    Quantities are updated only via stock movements or approved adjustments.
    """

    queryset = Stock.objects.select_related("item", "warehouse").all()
    serializer_class = StockSerializer
    filterset_class = StockFilter
    search_fields = ["item__code", "item__name", "warehouse__name"]
    ordering_fields = ["quantity_on_hand", "quantity_available", "last_updated"]

    def get_permissions(self):
        if self.action in ("reserve", "release"):
            self.required_action = "update"
            return [IsAuthenticated(), HasModulePermission()]
        self.required_action = "read"
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Aggregate stock KPIs for the dashboard."""
        queryset = self.filter_queryset(self.get_queryset())
        total_items = queryset.values("item_id").distinct().count()
        low_stock_count = queryset.filter(
            quantity_available__gt=0,
            quantity_available__lte=F("item__reorder_level"),
        ).count()
        out_of_stock_count = queryset.filter(quantity_available__lte=0).count()
        total_stock_value = queryset.aggregate(
            total=Coalesce(
                Sum(F("quantity_on_hand") * F("item__unit_cost")),
                Decimal("0"),
            )
        )["total"]

        data = {
            "total_items": total_items,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            "total_stock_value": total_stock_value,
        }
        serializer = StockSummarySerializer(data)
        return api_response(data=serializer.data)

    @action(detail=True, methods=["post"])
    def reserve(self, request, pk=None):
        """Reserve available stock for an order or department request."""
        stock = self.get_object()
        quantity = Decimal(str(request.data.get("quantity", "0")))
        notes = request.data.get("notes", "")
        try:
            from apps.core.audit import log_audit
            from apps.inventory.services import StockService

            before = {
                "reserved": str(stock.quantity_reserved),
                "available": str(stock.quantity_available),
            }
            updated = StockService.reserve_stock(
                item=stock.item,
                warehouse=stock.warehouse,
                quantity=quantity,
            )
            log_audit(
                user=request.user,
                module="inventory",
                action="reserve_stock",
                record_id=stock.id,
                old_values=before,
                new_values={
                    "reserved": str(updated.quantity_reserved),
                    "available": str(updated.quantity_available),
                    "quantity": str(quantity),
                    "notes": notes,
                },
                department_context="Procurement",
            )
        except Exception as exc:
            return api_error(message=str(exc))
        return api_response(
            data=StockSerializer(updated).data,
            message="Stock reserved",
        )

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        """Release previously reserved stock."""
        stock = self.get_object()
        quantity = Decimal(str(request.data.get("quantity", "0")))
        notes = request.data.get("notes", "")
        try:
            from apps.core.audit import log_audit
            from apps.inventory.services import StockService

            before = {
                "reserved": str(stock.quantity_reserved),
                "available": str(stock.quantity_available),
            }
            updated = StockService.release_reservation(
                item=stock.item,
                warehouse=stock.warehouse,
                quantity=quantity,
            )
            log_audit(
                user=request.user,
                module="inventory",
                action="release_reservation",
                record_id=stock.id,
                old_values=before,
                new_values={
                    "reserved": str(updated.quantity_reserved),
                    "available": str(updated.quantity_available),
                    "quantity": str(quantity),
                    "notes": notes,
                },
                department_context="Procurement",
            )
        except Exception as exc:
            return api_error(message=str(exc))
        return api_response(
            data=StockSerializer(updated).data,
            message="Reservation released",
        )


class StockMovementViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    """Create and list stock movements (immutable audit log)."""

    queryset = StockMovement.objects.select_related(
        "item", "warehouse", "created_by"
    ).all()
    serializer_class = StockMovementSerializer
    filterset_class = StockMovementFilter
    search_fields = ["item__code", "serial_number", "reference_id", "notes"]
    ordering_fields = ["created_at", "quantity"]

    http_method_names = ["get", "post", "head", "options"]

    def get_create_message(self):
        return "Stock movement recorded"


class StockAdjustmentViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    """Create and manage stock adjustment requests."""

    queryset = StockAdjustment.objects.select_related(
        "item",
        "warehouse",
        "requested_by",
        "approved_by",
    ).all()
    serializer_class = StockAdjustmentSerializer
    filterset_class = StockAdjustmentFilter
    search_fields = ["item__code", "reason"]
    ordering_fields = ["created_at", "status"]

    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_create_message(self):
        return "Stock adjustment submitted"

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != StockAdjustment.STATUS_PENDING:
            return api_error(message="Only pending adjustments can be edited.")
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve a pending adjustment and apply it to stock."""
        adjustment = self.get_object()
        serializer = StockAdjustmentApproveSerializer(
            data={},
            context={"request": request},
        )
        try:
            serializer.is_valid(raise_exception=True)
            adjustment = serializer.save(adjustment=adjustment, user=request.user)
        except DRFValidationError as exc:
            return api_error(errors=exc.detail)
        return api_response(
            data=StockAdjustmentSerializer(adjustment).data,
            message="Stock adjustment approved and applied",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Reject a pending stock adjustment."""
        adjustment = self.get_object()
        if adjustment.status != StockAdjustment.STATUS_PENDING:
            return api_error(message="Only pending adjustments can be rejected.")
        adjustment.status = StockAdjustment.STATUS_REJECTED
        adjustment.approved_by = request.user
        adjustment.approved_at = timezone.now()
        adjustment.save(
            update_fields=["status", "approved_by", "approved_at", "updated_at"]
        )
        return api_response(
            data=StockAdjustmentSerializer(adjustment).data,
            message="Stock adjustment rejected",
        )


class ItemSerialNumberViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    """CRUD for item serial numbers."""

    queryset = ItemSerialNumber.objects.select_related(
        "item", "warehouse", "sold_to"
    ).all()
    serializer_class = ItemSerialNumberSerializer
    filterset_class = ItemSerialNumberFilter
    search_fields = ["serial_number", "item__code"]
    ordering_fields = ["serial_number", "created_at"]

    def get_create_message(self):
        return "Serial number registered"

    def get_update_message(self):
        return "Serial number updated"

    def get_destroy_message(self):
        return "Serial number deactivated"


class StockAlertViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    """List and manage automated stock alerts."""

    queryset = StockAlert.objects.select_related("item", "warehouse").all()
    serializer_class = StockAlertSerializer
    filterset_class = StockAlertFilter
    search_fields = ["message", "item__code", "item__name"]
    ordering_fields = ["created_at", "alert_type"]

    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_permissions(self):
        self.required_action = "read"
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        return api_error(
            message="Stock alerts are generated automatically by the system.",
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        return api_error(
            message="Stock alerts cannot be deleted.",
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        allowed = {"is_read"}
        if set(request.data.keys()) - allowed:
            return api_error(message="Only is_read can be updated on stock alerts.")
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        serializer.save()
        return api_response(data=serializer.data, message="Alert updated")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Mark a single alert as read."""
        alert = self.get_object()
        alert.is_read = True
        alert.save(update_fields=["is_read"])
        return api_response(
            data=StockAlertSerializer(alert).data,
            message="Alert marked as read",
        )

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request, pk=None):
        """Mark all unread alerts as read."""
        updated = StockAlert.objects.filter(is_read=False).update(is_read=True)
        return api_response(
            data={"marked_read": updated},
            message=f"{updated} alert(s) marked as read",
        )
