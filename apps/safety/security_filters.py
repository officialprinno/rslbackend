"""Security sub-department filters."""

import django_filters
from django.db.models import Q

from apps.safety.security_models import (
    AccessLog,
    InterLocationMovement,
    SecurityIncidentRecord,
    SecurityPersonnel,
    SecurityShift,
    VehicleLog,
    Visitor,
)


class VisitorFilter(django_filters.FilterSet):
    location = django_filters.NumberFilter(field_name="location_id")
    on_site = django_filters.BooleanFilter(method="filter_on_site")
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = Visitor
        fields = ["purpose", "status", "location"]

    def filter_on_site(self, qs, name, value):
        if value:
            return qs.filter(
                status__in=[Visitor.STATUS_SIGNED_IN, Visitor.STATUS_OVERSTAYING]
            )
        return qs


class VehicleLogFilter(django_filters.FilterSet):
    location = django_filters.NumberFilter(field_name="location_id")
    on_premises = django_filters.BooleanFilter(method="filter_on_premises")

    class Meta:
        model = VehicleLog
        fields = ["vehicle_type", "status", "location"]

    def filter_on_premises(self, qs, name, value):
        if value:
            return qs.filter(status=VehicleLog.STATUS_ON)
        return qs


class MovementFilter(django_filters.FilterSet):
    location = django_filters.NumberFilter(method="filter_location")
    in_transit = django_filters.BooleanFilter(method="filter_in_transit")

    class Meta:
        model = InterLocationMovement
        fields = ["movement_type", "status"]

    def filter_location(self, qs, name, value):
        return qs.filter(Q(from_location_id=value) | Q(to_location_id=value))

    def filter_in_transit(self, qs, name, value):
        if value:
            return qs.filter(
                status__in=[
                    InterLocationMovement.STATUS_TRANSIT,
                    InterLocationMovement.STATUS_OVERDUE,
                ]
            )
        return qs


class SecurityPersonnelFilter(django_filters.FilterSet):
    location = django_filters.NumberFilter(field_name="primary_location_id")

    class Meta:
        model = SecurityPersonnel
        fields = ["rank", "assignment_scope", "is_on_duty"]


class SecurityShiftFilter(django_filters.FilterSet):
    location = django_filters.NumberFilter(field_name="location_id")
    week_start = django_filters.DateFilter(field_name="date", lookup_expr="gte")

    class Meta:
        model = SecurityShift
        fields = ["shift_type", "status", "location"]


class AccessLogFilter(django_filters.FilterSet):
    location = django_filters.NumberFilter(field_name="location_id")
    violations_only = django_filters.BooleanFilter(method="filter_violations")

    class Meta:
        model = AccessLog
        fields = ["action", "person_type", "location"]

    def filter_violations(self, qs, name, value):
        if value:
            return qs.filter(
                action__in=[AccessLog.ACTION_DENIED, AccessLog.ACTION_FORCED]
            )
        return qs


class SecurityIncidentFilter(django_filters.FilterSet):
    location = django_filters.NumberFilter(field_name="location_id")

    class Meta:
        model = SecurityIncidentRecord
        fields = ["incident_type", "severity", "status", "location"]
