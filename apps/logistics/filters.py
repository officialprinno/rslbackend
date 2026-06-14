"""django-filter classes for logistics API."""

import django_filters
from django_filters import DateFromToRangeFilter

from apps.logistics.models import (
    DeliveryNote,
    DeliveryOrder,
    Driver,
    FuelRecord,
    Vehicle,
    VehicleMaintenance,
)


class VehicleFilter(django_filters.FilterSet):
    vehicle_type = django_filters.CharFilter()
    status = django_filters.CharFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Vehicle
        fields = ["vehicle_type", "status", "is_active"]


class DriverFilter(django_filters.FilterSet):
    license_class = django_filters.CharFilter()
    is_available = django_filters.BooleanFilter()

    class Meta:
        model = Driver
        fields = ["license_class", "is_available"]


class DeliveryOrderFilter(django_filters.FilterSet):
    customer = django_filters.NumberFilter(field_name="customer_id")
    driver = django_filters.NumberFilter(field_name="driver_id")
    vehicle = django_filters.NumberFilter(field_name="vehicle_id")
    status = django_filters.CharFilter()
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    scheduled_date = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="date__gte")
    date_after = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="date__lte")

    class Meta:
        model = DeliveryOrder
        fields = ["customer", "driver", "vehicle", "status"]

    def filter_overdue(self, queryset, name, value):
        from django.utils import timezone

        now = timezone.now()
        if value:
            return queryset.filter(
                scheduled_date__lt=now,
                status__in=[DeliveryOrder.STATUS_SCHEDULED, DeliveryOrder.STATUS_IN_TRANSIT],
            )
        return queryset


class DeliveryNoteFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    created_at = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_after = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = DeliveryNote
        fields = ["status"]


class MaintenanceFilter(django_filters.FilterSet):
    vehicle = django_filters.NumberFilter(field_name="vehicle_id")
    maintenance_type = django_filters.CharFilter()
    status = django_filters.CharFilter()
    upcoming = django_filters.BooleanFilter(method="filter_upcoming")
    service_date = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="service_date", lookup_expr="gte")
    date_after = django_filters.DateFilter(field_name="service_date", lookup_expr="lte")

    class Meta:
        model = VehicleMaintenance
        fields = ["vehicle", "maintenance_type", "status"]

    def filter_upcoming(self, queryset, name, value):
        from datetime import timedelta

        from django.utils import timezone

        if value:
            end = timezone.now().date() + timedelta(days=7)
            return queryset.filter(
                service_date__lte=end,
                status=VehicleMaintenance.STATUS_SCHEDULED,
            )
        return queryset


class FuelRecordFilter(django_filters.FilterSet):
    vehicle = django_filters.NumberFilter(field_name="vehicle_id")
    driver = django_filters.NumberFilter(field_name="driver_id")
    date = DateFromToRangeFilter()
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_after = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = FuelRecord
        fields = ["vehicle", "driver"]
