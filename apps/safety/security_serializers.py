"""Security sub-department serializers."""

from rest_framework import serializers

from apps.safety.security_models import (
    AccessLog,
    AccessZone,
    InterLocationMovement,
    SecurityIncidentRecord,
    SecurityLocation,
    SecurityPersonnel,
    SecurityShift,
    SecurityShiftOfficer,
    VehicleLog,
    Visitor,
)
from apps.safety.security_service import SecurityService


class SecurityLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityLocation
        fields = [
            "id", "name", "address", "description", "color", "icon", "is_active",
        ]


class VisitorSerializer(serializers.ModelSerializer):
    host_employee_name = serializers.CharField(
        source="host_employee.full_name", read_only=True
    )
    department_name = serializers.CharField(
        source="department.name", read_only=True, default=""
    )
    location_name = serializers.CharField(source="location.name", read_only=True)
    registered_by_name = serializers.CharField(
        source="registered_by.get_full_name", read_only=True
    )

    class Meta:
        model = Visitor
        fields = [
            "id", "visitor_number", "full_name", "id_type", "id_number", "phone",
            "company", "photo_url", "email", "purpose", "host_employee",
            "host_employee_name", "department", "department_name", "location",
            "location_name", "expected_time_in", "expected_time_out",
            "actual_time_in", "actual_time_out", "badge_number",
            "vehicle_registration", "items_brought", "status", "denial_reason",
            "notes", "pre_approved", "registered_by_name", "created_at",
        ]
        read_only_fields = ["visitor_number", "status", "badge_number"]


class VehicleLogSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    security_officer_name = serializers.CharField(
        source="security_officer.get_full_name", read_only=True
    )

    class Meta:
        model = VehicleLog
        fields = [
            "id", "log_number", "registration_number", "vehicle_type", "make",
            "color", "driver_name", "driver_id_number", "company", "purpose",
            "occupants_count", "cargo_description", "location", "location_name",
            "time_in", "time_out", "expected_time_out", "status", "flag_reason",
            "security_officer_name", "created_at",
        ]
        read_only_fields = ["log_number", "status"]


class SecurityPersonnelSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(
        source="employee.employee_number", read_only=True
    )
    full_name = serializers.CharField(source="employee.full_name", read_only=True)
    photo_url = serializers.SerializerMethodField()
    primary_location_name = serializers.CharField(
        source="primary_location.name", read_only=True, default=""
    )

    class Meta:
        model = SecurityPersonnel
        fields = [
            "id", "employee", "employee_number", "full_name", "photo_url", "rank",
            "primary_location", "primary_location_name", "assignment_scope",
            "post_station", "certification_number", "certification_expiry",
            "is_on_duty",
        ]

    def get_photo_url(self, obj):
        return obj.employee.profile_photo or None


class ShiftOfficerSerializer(serializers.ModelSerializer):
    officer_name = serializers.CharField(source="officer.get_full_name", read_only=True)
    rank = serializers.SerializerMethodField()

    class Meta:
        model = SecurityShiftOfficer
        fields = ["officer_id", "officer_name", "rank", "post_station"]

    officer_id = serializers.IntegerField(source="officer.id", read_only=True)

    def get_rank(self, obj):
        profile = SecurityPersonnel.objects.filter(
            employee__user=obj.officer
        ).first()
        return profile.rank if profile else "GUARD"


class SecurityShiftSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    officers = ShiftOfficerSerializer(many=True, read_only=True)
    officers_count = serializers.SerializerMethodField()
    minimum_required = serializers.SerializerMethodField()
    is_understaffed = serializers.SerializerMethodField()

    class Meta:
        model = SecurityShift
        fields = [
            "id", "date", "shift_type", "location", "location_name", "officers",
            "officers_count", "minimum_required", "is_understaffed", "status",
            "special_instructions", "incidents_count", "handover_submitted",
            "handover_notes", "created_at",
        ]

    def get_officers_count(self, obj):
        return obj.officers.count()

    def get_minimum_required(self, obj):
        return SecurityService.shift_minimum(obj.location.name, obj.shift_type)

    def get_is_understaffed(self, obj):
        return self.get_officers_count(obj) < self.get_minimum_required(obj)


class AccessZoneSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    events_today = serializers.SerializerMethodField()
    current_occupants = serializers.SerializerMethodField()

    class Meta:
        model = AccessZone
        fields = [
            "id", "location", "location_name", "name", "access_level",
            "description", "events_today", "current_occupants", "is_active",
        ]

    def get_events_today(self, obj):
        from django.utils import timezone

        return AccessLog.objects.filter(
            zone=obj, created_at__date=timezone.now().date()
        ).count()

    def get_current_occupants(self, obj):
        return 0


class AccessLogSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source="zone.name", read_only=True, default="")
    location_name = serializers.CharField(source="location.name", read_only=True)
    security_officer_name = serializers.CharField(
        source="security_officer.get_full_name", read_only=True
    )

    class Meta:
        model = AccessLog
        fields = [
            "id", "zone", "zone_name", "location", "location_name", "person_name",
            "person_type", "employee_user", "action", "method",
            "security_officer_name", "notes", "created_at",
        ]


class SecurityIncidentSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    reported_by_name = serializers.CharField(
        source="reported_by.get_full_name", read_only=True
    )
    closed_by_name = serializers.CharField(
        source="closed_by.get_full_name", read_only=True, default=""
    )
    days_open = serializers.SerializerMethodField()

    class Meta:
        model = SecurityIncidentRecord
        fields = [
            "id", "incident_number", "incident_type", "severity", "date_occurred",
            "location", "location_name", "specific_area", "description",
            "persons_involved", "immediate_actions", "police_report_number",
            "evidence_photos", "investigation_notes", "status", "days_open",
            "reported_by_name", "closed_by_name", "closed_at", "created_at",
        ]
        read_only_fields = ["incident_number", "status"]

    def get_days_open(self, obj):
        from django.utils import timezone

        end = obj.closed_at or timezone.now()
        return max(0, (end - obj.date_occurred).days)


class MovementSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.full_name", read_only=True, default=""
    )
    vehicle_registration = serializers.CharField(
        source="vehicle_log.registration_number", read_only=True, default=""
    )
    from_location_name = serializers.CharField(
        source="from_location.name", read_only=True
    )
    to_location_name = serializers.CharField(source="to_location.name", read_only=True)
    logged_by_name = serializers.CharField(
        source="logged_by.get_full_name", read_only=True
    )
    arrived_confirmed_by_name = serializers.CharField(
        source="arrived_confirmed_by.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = InterLocationMovement
        fields = [
            "id", "movement_number", "movement_type", "type", "employee", "employee_name",
            "vehicle_log", "vehicle_registration", "from_location",
            "from_location_name", "to_location", "to_location_name",
            "departure_time", "expected_arrival", "actual_arrival",
            "travel_time_minutes", "status", "purpose", "passengers", "notes",
            "logged_by_name", "arrived_confirmed_by_name", "created_at",
        ]
        read_only_fields = ["movement_number", "status", "travel_time_minutes", "type"]

    type = serializers.CharField(source="movement_type", read_only=True)


class SecurityDashboardSerializer(serializers.Serializer):
    location_filter = serializers.IntegerField(allow_null=True)
    visitors_on_site = serializers.IntegerField()
    visitors_main = serializers.IntegerField()
    visitors_stein = serializers.IntegerField()
    vehicles_on_premises = serializers.IntegerField()
    vehicles_main = serializers.IntegerField()
    vehicles_stein = serializers.IntegerField()
    officers_on_duty = serializers.IntegerField()
    officers_main = serializers.IntegerField()
    officers_stein = serializers.IntegerField()
    incidents_today = serializers.IntegerField()
    incidents_main = serializers.IntegerField()
    incidents_stein = serializers.IntegerField()
    in_transit_count = serializers.IntegerField()
    access_violations_month = serializers.IntegerField()
    live_activity = serializers.ListField()
    in_transit = MovementSerializer(many=True)
    shift_status = serializers.ListField()
    alerts = serializers.ListField()
