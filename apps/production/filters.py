"""django-filter classes for production API."""

import django_filters
from django_filters import DateFromToRangeFilter

from apps.production.models import (
    BillOfMaterials,
    Machine,
    MachineUsage,
    OutputRecord,
    Product,
    WorkOrder,
)


class ProductFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Product
        fields = ["is_active"]


class BOMFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name="product_id")
    status = django_filters.CharFilter()

    class Meta:
        model = BillOfMaterials
        fields = ["product", "status"]


class WorkOrderFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name="product_id")
    status = django_filters.CharFilter()
    shift = django_filters.CharFilter()
    operator = django_filters.NumberFilter(field_name="operator_id")
    assigned_to_me = django_filters.BooleanFilter(method="filter_assigned_to_me")
    execution_workflow = django_filters.BooleanFilter()
    planned_start = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="planned_start", lookup_expr="date__gte")
    date_after = django_filters.DateFilter(field_name="planned_start", lookup_expr="date__lte")

    class Meta:
        model = WorkOrder
        fields = ["product", "status", "shift", "operator", "execution_workflow"]

    def filter_assigned_to_me(self, queryset, name, value):
        if not value:
            return queryset
        user = getattr(self.request, "user", None)
        if user and user.is_authenticated:
            return queryset.filter(operator=user)
        return queryset.none()


class OutputRecordFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name="work_order__product_id")
    shift = django_filters.CharFilter()
    operator = django_filters.NumberFilter(field_name="operator_id")
    date = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_after = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = OutputRecord
        fields = ["shift", "operator"]


class MachineFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    machine_type = django_filters.CharFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Machine
        fields = ["status", "machine_type", "is_active"]


class MachineUsageFilter(django_filters.FilterSet):
    machine = django_filters.NumberFilter(field_name="machine_id")
    work_order = django_filters.NumberFilter(field_name="work_order_id")
    operator = django_filters.NumberFilter(field_name="operator_id")
    start_time = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="start_time", lookup_expr="date__gte")
    date_after = django_filters.DateFilter(field_name="start_time", lookup_expr="date__lte")

    class Meta:
        model = MachineUsage
        fields = ["machine", "work_order", "operator"]
