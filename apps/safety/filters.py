"""Filters for Safety module."""

import django_filters

from apps.safety.models import (
    PPEIssuance,
    PPERequest,
    SafetyIncident,
    SafetyInspection,
    SafetyTraining,
    WorkPermit,
)


class SafetyIncidentFilter(django_filters.FilterSet):
    incident_type = django_filters.CharFilter()
    severity = django_filters.CharFilter()
    status = django_filters.CharFilter()
    location = django_filters.CharFilter(lookup_expr="icontains")
    date_from = django_filters.DateFilter(field_name="date_occurred", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="date_occurred", lookup_expr="date__lte")
    department = django_filters.NumberFilter(field_name="department_id")

    class Meta:
        model = SafetyIncident
        fields = ["incident_type", "severity", "status", "location", "department"]


class SafetyInspectionFilter(django_filters.FilterSet):
    inspection_type = django_filters.CharFilter()
    area = django_filters.CharFilter(lookup_expr="icontains")
    status = django_filters.CharFilter()
    inspector = django_filters.NumberFilter(field_name="inspector_id")
    date_from = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="date__lte")

    class Meta:
        model = SafetyInspection
        fields = ["inspection_type", "area", "status", "inspector"]


class WorkPermitFilter(django_filters.FilterSet):
    permit_type = django_filters.CharFilter()
    status = django_filters.CharFilter()
    location = django_filters.CharFilter(lookup_expr="icontains")
    active_only = django_filters.BooleanFilter(method="filter_active")
    date_from = django_filters.DateFilter(field_name="valid_from", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="valid_until", lookup_expr="date__lte")

    class Meta:
        model = WorkPermit
        fields = ["permit_type", "status", "location"]

    def filter_active(self, queryset, name, value):
        if value:
            return queryset.filter(status=WorkPermit.STATUS_ACTIVE)
        return queryset


class PPERequestFilter(django_filters.FilterSet):
    ppe_type = django_filters.CharFilter(field_name="ppe_item__ppe_type")
    department = django_filters.NumberFilter(field_name="employee__department_id")
    status = django_filters.CharFilter()
    priority = django_filters.CharFilter()
    pending_store = django_filters.BooleanFilter(method="filter_pending_store")
    my_requests = django_filters.BooleanFilter(method="filter_my_requests")

    class Meta:
        model = PPERequest
        fields = ["status", "priority", "ppe_item"]

    def filter_pending_store(self, queryset, name, value):
        if value:
            return queryset.filter(status=PPERequest.STATUS_PENDING_STORE)
        return queryset

    def filter_my_requests(self, queryset, name, value):
        if value and self.request and self.request.user.is_authenticated:
            return queryset.filter(requested_by=self.request.user)
        return queryset


class PPEIssuanceFilter(django_filters.FilterSet):
    ppe_type = django_filters.CharFilter(field_name="ppe_item__ppe_type")
    department = django_filters.NumberFilter(field_name="employee__department_id")
    date_from = django_filters.DateFilter(field_name="issue_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="issue_date", lookup_expr="lte")

    class Meta:
        model = PPEIssuance
        fields = ["ppe_type", "department"]


class SafetyTrainingFilter(django_filters.FilterSet):
    training_type = django_filters.CharFilter()
    status = django_filters.CharFilter()
    date_from = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="date__lte")

    class Meta:
        model = SafetyTraining
        fields = ["training_type", "status"]
