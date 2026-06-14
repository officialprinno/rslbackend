"""django-filter classes for procurement API."""

import django_filters
from django_filters import DateFromToRangeFilter

from apps.procurement.models import (
    GoodsReceivedNote,
    PurchaseOrder,
    PurchaseRequisition,
    RequestForQuotation,
    Supplier,
    SupplierInvoice,
    SupplierQuotation,
)


class SupplierFilter(django_filters.FilterSet):
    country = django_filters.CharFilter(field_name="country", lookup_expr="iexact")
    rating = django_filters.NumberFilter(field_name="rating")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Supplier
        fields = ["country", "rating", "is_active", "payment_terms"]


class PurchaseRequisitionFilter(django_filters.FilterSet):
    department = django_filters.NumberFilter(field_name="department_id")
    priority = django_filters.CharFilter()
    status = django_filters.CharFilter()
    created_at = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_after = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = PurchaseRequisition
        fields = ["department", "priority", "status"]


class RFQFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    requisition = django_filters.NumberFilter(field_name="requisition_id")

    class Meta:
        model = RequestForQuotation
        fields = ["status", "requisition"]


class QuotationFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    rfq = django_filters.NumberFilter(field_name="rfq_id")
    supplier = django_filters.NumberFilter(field_name="supplier_id")

    class Meta:
        model = SupplierQuotation
        fields = ["status", "rfq", "supplier"]


class PurchaseOrderFilter(django_filters.FilterSet):
    supplier = django_filters.NumberFilter(field_name="supplier_id")
    status = django_filters.CharFilter()
    order_date = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="order_date", lookup_expr="gte")
    date_after = django_filters.DateFilter(field_name="order_date", lookup_expr="lte")

    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "status"]


class GRNFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    purchase_order = django_filters.NumberFilter(field_name="purchase_order_id")

    class Meta:
        model = GoodsReceivedNote
        fields = ["status", "purchase_order"]


class SupplierInvoiceFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    supplier = django_filters.NumberFilter(field_name="supplier_id")
    three_way_matched = django_filters.BooleanFilter()

    class Meta:
        model = SupplierInvoice
        fields = ["status", "supplier", "three_way_matched"]
