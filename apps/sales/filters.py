"""django-filter classes for sales API."""

import django_filters
from django_filters import DateFromToRangeFilter

from apps.sales.models import (
    CreditNote,
    Customer,
    CustomerPayment,
    SalesInvoice,
    SalesOrder,
    SalesQuotation,
)


class CustomerFilter(django_filters.FilterSet):
    country = django_filters.CharFilter(field_name="country", lookup_expr="iexact")
    is_active = django_filters.BooleanFilter()
    payment_terms = django_filters.CharFilter()

    class Meta:
        model = Customer
        fields = ["country", "is_active", "payment_terms"]


class QuotationFilter(django_filters.FilterSet):
    customer = django_filters.NumberFilter(field_name="customer_id")
    status = django_filters.CharFilter()
    expired = django_filters.BooleanFilter(method="filter_expired")
    created_at = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_after = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = SalesQuotation
        fields = ["customer", "status"]

    def filter_expired(self, queryset, name, value):
        from django.utils import timezone

        today = timezone.now().date()
        if value:
            return queryset.filter(valid_until__lt=today)
        return queryset.filter(valid_until__gte=today)


class SalesOrderFilter(django_filters.FilterSet):
    customer = django_filters.NumberFilter(field_name="customer_id")
    status = django_filters.CharFilter()
    delivery_status = django_filters.CharFilter()
    payment_status = django_filters.CharFilter()
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    created_at = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_after = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = SalesOrder
        fields = ["customer", "status", "delivery_status", "payment_status"]

    def filter_overdue(self, queryset, name, value):
        from django.utils import timezone

        today = timezone.now().date()
        if value:
            return queryset.filter(delivery_date__lt=today).exclude(
                status=SalesOrder.STATUS_DELIVERED
            ).exclude(status=SalesOrder.STATUS_CANCELLED)
        return queryset


class InvoiceFilter(django_filters.FilterSet):
    customer = django_filters.NumberFilter(field_name="customer_id")
    status = django_filters.CharFilter()
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    invoice_date = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="invoice_date", lookup_expr="gte")
    date_after = django_filters.DateFilter(field_name="invoice_date", lookup_expr="lte")

    class Meta:
        model = SalesInvoice
        fields = ["customer", "status"]

    def filter_overdue(self, queryset, name, value):
        from django.utils import timezone

        today = timezone.now().date()
        if value:
            return queryset.filter(due_date__lt=today, status__in=[
                SalesInvoice.STATUS_SENT,
                SalesInvoice.STATUS_PARTIAL,
                SalesInvoice.STATUS_OVERDUE,
            ])
        return queryset


class PaymentFilter(django_filters.FilterSet):
    customer = django_filters.NumberFilter(field_name="customer_id")
    payment_method = django_filters.CharFilter()
    payment_date = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="payment_date", lookup_expr="gte")
    date_after = django_filters.DateFilter(field_name="payment_date", lookup_expr="lte")

    class Meta:
        model = CustomerPayment
        fields = ["customer", "payment_method"]


class CreditNoteFilter(django_filters.FilterSet):
    customer = django_filters.NumberFilter(field_name="customer_id")
    status = django_filters.CharFilter()
    invoice = django_filters.NumberFilter(field_name="invoice_id")

    class Meta:
        model = CreditNote
        fields = ["customer", "status", "invoice"]
