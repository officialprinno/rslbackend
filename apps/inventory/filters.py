"""django-filter FilterSets for inventory list endpoints."""

import django_filters
from django.db.models import F

from apps.inventory.models import (
    DepartmentRequest,
    GoodsIssueNote,
    Item,
    ItemCategory,
    ItemSerialNumber,
    Stock,
    StockAdjustment,
    StockAlert,
    StockBatch,
    StockMovement,
    StockTake,
    StockTransfer,
)


class ItemCategoryFilter(django_filters.FilterSet):
    parent = django_filters.NumberFilter(field_name="parent_id")
    parent__isnull = django_filters.BooleanFilter(field_name="parent", lookup_expr="isnull")
    code = django_filters.CharFilter(field_name="code", lookup_expr="iexact")

    class Meta:
        model = ItemCategory
        fields = ["is_active", "parent", "code"]


class ItemFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(field_name="category_id")
    min_unit_cost = django_filters.NumberFilter(field_name="unit_cost", lookup_expr="gte")
    max_unit_cost = django_filters.NumberFilter(field_name="unit_cost", lookup_expr="lte")
    item_usage = django_filters.CharFilter(field_name="item_usage")
    internal_use = django_filters.BooleanFilter(method="filter_internal_use")
    without_production_product = django_filters.BooleanFilter(
        method="filter_without_production_product"
    )

    class Meta:
        model = Item
        fields = [
            "is_active",
            "item_type",
            "item_usage",
            "category",
            "has_serial_number",
            "has_batch_tracking",
            "has_expiry_date",
        ]

    def filter_internal_use(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(item_usage__in=[Item.USAGE_INTERNAL, Item.USAGE_BOTH])

    def filter_without_production_product(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(production_product__isnull=True)


class StockFilter(django_filters.FilterSet):
    item = django_filters.NumberFilter(field_name="item_id")
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")
    low_stock = django_filters.BooleanFilter(method="filter_low_stock")
    has_reserved = django_filters.BooleanFilter(method="filter_has_reserved")

    class Meta:
        model = Stock
        fields = ["item", "warehouse"]

    def filter_low_stock(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(quantity_on_hand__lte=F("item__reorder_level"))

    def filter_has_reserved(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(quantity_reserved__gt=0)


class StockMovementFilter(django_filters.FilterSet):
    item = django_filters.NumberFilter(field_name="item_id")
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")
    created_at = django_filters.DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="gte")
    date_after = django_filters.DateFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = StockMovement
        fields = ["movement_type", "reference_type", "item", "warehouse", "created_at"]


class StockAdjustmentFilter(django_filters.FilterSet):
    item = django_filters.NumberFilter(field_name="item_id")
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")

    class Meta:
        model = StockAdjustment
        fields = ["status", "adjustment_type", "item", "warehouse"]


class ItemSerialNumberFilter(django_filters.FilterSet):
    item = django_filters.NumberFilter(field_name="item_id")
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")

    class Meta:
        model = ItemSerialNumber
        fields = ["status", "item", "warehouse", "is_active"]


class StockAlertFilter(django_filters.FilterSet):
    item = django_filters.NumberFilter(field_name="item_id")
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")

    class Meta:
        model = StockAlert
        fields = ["alert_type", "is_read", "item", "warehouse"]


class StockBatchFilter(django_filters.FilterSet):
    item = django_filters.NumberFilter(field_name="item_id")
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")

    class Meta:
        model = StockBatch
        fields = ["item", "warehouse", "is_active"]


class StockTransferFilter(django_filters.FilterSet):
    source_warehouse = django_filters.NumberFilter(field_name="source_warehouse_id")
    destination_warehouse = django_filters.NumberFilter(field_name="destination_warehouse_id")

    class Meta:
        model = StockTransfer
        fields = ["status", "source_warehouse", "destination_warehouse"]


class DepartmentRequestFilter(django_filters.FilterSet):
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")
    requested_by = django_filters.NumberFilter(field_name="requested_by_id")
    priority = django_filters.CharFilter(field_name="priority")
    scope = django_filters.CharFilter(method="filter_scope")

    class Meta:
        model = DepartmentRequest
        fields = ["status", "department", "warehouse", "priority", "requested_by"]

    def filter_scope(self, queryset, name, value):
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return queryset.none()
        if value == "my":
            return queryset.filter(requested_by=user)
        if value == "pending_approval":
            return queryset.filter(
                status__in=[
                    DepartmentRequest.STATUS_SUBMITTED,
                    DepartmentRequest.STATUS_PENDING,
                ]
            )
        if value == "pending_issue":
            return queryset.filter(
                status__in=[
                    DepartmentRequest.STATUS_APPROVED,
                    DepartmentRequest.STATUS_PROCESSING,
                    DepartmentRequest.STATUS_PARTIALLY_ISSUED,
                ]
            )
        if value == "urgent":
            return queryset.filter(
                priority=DepartmentRequest.PRIORITY_URGENT,
                status__in=[
                    DepartmentRequest.STATUS_SUBMITTED,
                    DepartmentRequest.STATUS_PENDING,
                ],
            )
        return queryset


class GoodsIssueNoteFilter(django_filters.FilterSet):
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")
    issue_type = django_filters.CharFilter(field_name="issue_type")

    class Meta:
        model = GoodsIssueNote
        fields = ["status", "department", "warehouse", "issue_type"]


class StockTakeFilter(django_filters.FilterSet):
    warehouse = django_filters.NumberFilter(field_name="warehouse_id")

    class Meta:
        model = StockTake
        fields = ["status", "warehouse"]
