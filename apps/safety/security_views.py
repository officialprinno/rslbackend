"""Security sub-department API viewsets."""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import api_error, api_response
from apps.safety.mixins import SafetyViewSetMixin
from apps.safety.security_filters import (
    AccessLogFilter,
    MovementFilter,
    SecurityIncidentFilter,
    SecurityPersonnelFilter,
    SecurityShiftFilter,
    VehicleLogFilter,
    VisitorFilter,
)
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
from apps.safety.security_serializers import (
    AccessLogSerializer,
    AccessZoneSerializer,
    MovementSerializer,
    SecurityDashboardSerializer,
    SecurityIncidentSerializer,
    SecurityLocationSerializer,
    SecurityPersonnelSerializer,
    SecurityShiftSerializer,
    VehicleLogSerializer,
    VisitorSerializer,
)
from apps.safety.security_service import SecurityService
from apps.safety.utils import (
    generate_movement_number,
    generate_security_incident_number,
    generate_vehicle_log_number,
    generate_visitor_number,
)


class SecurityLocationViewSet(SafetyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SecurityLocation.objects.filter(is_active=True)
    serializer_class = SecurityLocationSerializer

    def get_permissions(self):
        return [IsAuthenticated()]


class SecurityDashboardViewSet(SafetyViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        location_id = request.query_params.get("location")
        loc = int(location_id) if location_id else None
        data = SecurityService.dashboard(loc)
        data["in_transit"] = MovementSerializer(data["in_transit"], many=True).data
        return api_response(data=SecurityDashboardSerializer(data).data)

    @action(detail=False, methods=["get"])
    def activity(self, request):
        loc = request.query_params.get("location")
        location_id = int(loc) if loc else None
        return api_response(
            data=SecurityService._live_activity(location_id)
        )


class VisitorViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = Visitor.objects.select_related(
        "location", "host_employee", "department", "registered_by"
    ).filter(is_active=True)
    serializer_class = VisitorSerializer
    filterset_class = VisitorFilter
    search_fields = ["full_name", "id_number", "company", "visitor_number", "badge_number"]

    def get_queryset(self):
        qs = super().get_queryset()
        scope = SecurityService.user_security_scope(self.request.user)
        if scope:
            qs = qs.filter(location_id=scope)
        return qs

    def perform_create(self, serializer):
        serializer.save(
            visitor_number=generate_visitor_number(),
            registered_by=self.request.user,
            status=Visitor.STATUS_PENDING,
        )

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return api_response(message="Visitor record removed")

    @action(detail=True, methods=["post"], url_path="sign-in")
    def sign_in(self, request, pk=None):
        visitor = self.get_object()
        SecurityService.sign_in_visitor(visitor, request.user)
        return api_response(data=VisitorSerializer(visitor).data)

    @action(detail=True, methods=["post"], url_path="sign-out")
    def sign_out(self, request, pk=None):
        visitor = self.get_object()
        items = request.data.get("items_brought")
        SecurityService.sign_out_visitor(visitor, request.user, items)
        return api_response(data=VisitorSerializer(visitor).data)

    @action(detail=True, methods=["post"])
    def deny(self, request, pk=None):
        visitor = self.get_object()
        visitor.status = Visitor.STATUS_DENIED
        visitor.denial_reason = request.data.get("reason", "")
        visitor.save()
        return api_response(data=VisitorSerializer(visitor).data)


class VehicleLogViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = VehicleLog.objects.select_related("location", "security_officer").filter(
        is_active=True
    )
    serializer_class = VehicleLogSerializer
    filterset_class = VehicleLogFilter
    search_fields = ["registration_number", "driver_name", "company", "log_number"]

    def get_queryset(self):
        qs = super().get_queryset()
        scope = SecurityService.user_security_scope(self.request.user)
        if scope:
            qs = qs.filter(location_id=scope)
        return qs

    def perform_create(self, serializer):
        serializer.save(
            log_number=generate_vehicle_log_number(),
            security_officer=self.request.user,
            status=VehicleLog.STATUS_ON,
        )

    @action(detail=True, methods=["post"], url_path="log-exit")
    def log_exit(self, request, pk=None):
        log = self.get_object()
        log.time_out = timezone.now()
        log.status = VehicleLog.STATUS_EXITED
        log.save()
        return api_response(data=VehicleLogSerializer(log).data)

    @action(detail=True, methods=["post"])
    def flag(self, request, pk=None):
        log = self.get_object()
        log.status = VehicleLog.STATUS_FLAGGED
        log.flag_reason = request.data.get("reason", "")
        log.save()
        return api_response(data=VehicleLogSerializer(log).data)


class InterLocationMovementViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = InterLocationMovement.objects.select_related(
        "from_location", "to_location", "employee", "vehicle_log", "logged_by"
    ).filter(is_active=True)
    serializer_class = MovementSerializer
    filterset_class = MovementFilter
    search_fields = ["movement_number", "purpose"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        data = serializer.validated_data
        movement = InterLocationMovement.objects.create(
            movement_number=generate_movement_number(),
            movement_type=data["movement_type"],
            employee=data.get("employee"),
            vehicle_log=data.get("vehicle_log"),
            from_location=data["from_location"],
            to_location=data["to_location"],
            departure_time=data["departure_time"],
            expected_arrival=data["expected_arrival"],
            purpose=data["purpose"],
            passengers=data.get("passengers", []),
            notes=data.get("notes", ""),
            logged_by=request.user,
            status=InterLocationMovement.STATUS_TRANSIT,
        )
        return api_response(
            data=MovementSerializer(movement).data,
            status=status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        pass

    @action(detail=True, methods=["post"], url_path="mark-arrived")
    def mark_arrived(self, request, pk=None):
        movement = self.get_object()
        SecurityService.mark_movement_arrived(movement, request.user)
        return api_response(data=MovementSerializer(movement).data)

    @action(detail=False, methods=["get"], url_path="in-transit")
    def in_transit(self, request):
        qs = self.get_queryset().filter(
            status__in=[
                InterLocationMovement.STATUS_TRANSIT,
                InterLocationMovement.STATUS_OVERDUE,
            ]
        )
        return api_response(data=MovementSerializer(qs, many=True).data)


class SecurityPersonnelViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = SecurityPersonnel.objects.select_related(
        "employee", "primary_location"
    ).filter(is_active=True)
    serializer_class = SecurityPersonnelSerializer
    filterset_class = SecurityPersonnelFilter
    search_fields = ["employee__first_name", "employee__last_name"]

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.is_active = False
        obj.save(update_fields=["is_active", "updated_at"])
        return api_response(message="Personnel record removed")


class SecurityShiftViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = SecurityShift.objects.select_related("location").prefetch_related(
        "officers__officer"
    ).filter(is_active=True)
    serializer_class = SecurityShiftSerializer
    filterset_class = SecurityShiftFilter

    @action(detail=True, methods=["post"], url_path="submit-handover")
    def submit_handover(self, request, pk=None):
        shift = self.get_object()
        shift.handover_submitted = True
        shift.handover_notes = request.data.get("handover_notes", "")
        shift.outgoing_officer = request.user
        shift.incoming_officer_id = request.data.get("incoming_officer_id")
        shift.status = SecurityShift.STATUS_COMPLETED
        shift.save()
        return api_response(data=SecurityShiftSerializer(shift).data)

    @action(detail=False, methods=["get"], url_path="weekly-schedule")
    def weekly_schedule(self, request):
        location_id = request.query_params.get("location")
        week_start = request.query_params.get("week_start")
        qs = self.get_queryset()
        if location_id:
            qs = qs.filter(location_id=location_id)
        if week_start:
            qs = qs.filter(date__gte=week_start)
        return api_response(data=SecurityShiftSerializer(qs[:21], many=True).data)


class AccessZoneViewSet(SafetyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AccessZone.objects.select_related("location").filter(is_active=True)
    serializer_class = AccessZoneSerializer
    filterset_fields = ["location"]

    def get_permissions(self):
        return [IsAuthenticated()]


class AccessLogViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = AccessLog.objects.select_related(
        "zone", "location", "security_officer"
    ).filter(is_active=True)
    serializer_class = AccessLogSerializer
    filterset_class = AccessLogFilter
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(security_officer=self.request.user)

    @action(detail=False, methods=["get"], url_path="violations")
    def violations(self, request):
        qs = self.get_queryset().filter(
            action__in=[AccessLog.ACTION_DENIED, AccessLog.ACTION_FORCED]
        )
        return api_response(data=AccessLogSerializer(qs[:50], many=True).data)


class SecurityIncidentViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = SecurityIncidentRecord.objects.select_related(
        "location", "reported_by", "closed_by"
    ).filter(is_active=True)
    serializer_class = SecurityIncidentSerializer
    filterset_class = SecurityIncidentFilter
    search_fields = ["incident_number", "description"]

    def perform_create(self, serializer):
        serializer.save(
            incident_number=generate_security_incident_number(),
            reported_by=self.request.user,
            status=SecurityIncidentRecord.STATUS_OPEN,
        )

    @action(detail=True, methods=["post"])
    def investigate(self, request, pk=None):
        inc = self.get_object()
        inc.status = SecurityIncidentRecord.STATUS_INVESTIGATING
        inc.investigation_notes = request.data.get("investigation_notes", "")
        inc.save()
        return api_response(data=SecurityIncidentSerializer(inc).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        inc = self.get_object()
        inc.status = SecurityIncidentRecord.STATUS_CLOSED
        inc.closed_by = request.user
        inc.closed_at = timezone.now()
        inc.investigation_notes = request.data.get(
            "investigation_notes", inc.investigation_notes
        )
        inc.save()
        return api_response(data=SecurityIncidentSerializer(inc).data)
