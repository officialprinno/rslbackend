"""Safety API viewsets."""

from datetime import datetime

from django.db.models import Count
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import HasModulePermission
from apps.core.responses import api_error, api_response
from apps.safety.filters import (
    PPEIssuanceFilter,
    PPERequestFilter,
    SafetyIncidentFilter,
    SafetyInspectionFilter,
    SafetyTrainingFilter,
    WorkPermitFilter,
)
from apps.safety.mixins import SafetyViewSetMixin
from apps.safety.models import (
    CorrectiveAction,
    InspectionChecklistItem,
    PPEIssuance,
    PPEItem,
    PPERequest,
    PPERoleRequirement,
    SafetyIncident,
    SafetyInspection,
    SafetyTraining,
    TrainingAttendee,
    WorkPermit,
)
from apps.safety.ppe_request_service import PPERequestService
from apps.safety.serializers import (
    ChecklistItemSerializer,
    CorrectiveActionSerializer,
    IncidentListSerializer,
    IncidentSerializer,
    InspectionListSerializer,
    InspectionSerializer,
    PPEIssuanceSerializer,
    PPEItemSerializer,
    PPERequestSerializer,
    PPERoleRequirementSerializer,
    SafetyDashboardSerializer,
    TrainingAttendeeSerializer,
    TrainingListSerializer,
    TrainingSerializer,
    WorkPermitListSerializer,
    WorkPermitSerializer,
)
from apps.safety.services import SafetyService


class SafetyDashboardViewSet(SafetyViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        data = SafetyService.dashboard()
        serializer = SafetyDashboardSerializer(
            {
                **data,
                "recent_incidents": data["recent_incidents"],
                "upcoming_inspections": data["upcoming_inspections"],
            }
        )
        return api_response(data=serializer.data)

    @action(detail=False, methods=["get"])
    def score(self, request):
        return api_response(data={"safety_score": SafetyService.safety_score()})


class SafetyIncidentViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = SafetyIncident.objects.select_related(
        "department", "reported_by", "injured_person", "investigator", "closed_by"
    ).prefetch_related("witnesses", "corrective_actions")
    filterset_class = SafetyIncidentFilter
    search_fields = ["incident_number", "description", "location"]
    ordering_fields = ["date_occurred", "incident_number", "created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return IncidentListSerializer
        return IncidentSerializer

    def get_create_message(self):
        return "Incident reported"

    def get_update_message(self):
        return "Incident updated"

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        incident = self.get_object()
        if incident.status != SafetyIncident.STATUS_DRAFT:
            return api_error(message="Incident already submitted")
        incident.status = SafetyIncident.STATUS_OPEN
        incident.save()
        return api_response(
            data=IncidentSerializer(incident).data,
            message="Incident submitted to Safety Officer",
        )

    @action(detail=True, methods=["post"], url_path="start-investigation")
    def start_investigation(self, request, pk=None):
        incident = self.get_object()
        incident.status = SafetyIncident.STATUS_INVESTIGATING
        incident.investigator = request.user
        incident.investigated_at = timezone.now()
        incident.save()
        return api_response(
            data=IncidentSerializer(incident).data,
            message="Investigation started",
        )

    @action(detail=True, methods=["post"], url_path="corrective-actions")
    def add_corrective_action(self, request, pk=None):
        incident = self.get_object()
        data = {**request.data, "incident_id": incident.id}
        serializer = CorrectiveActionSerializer(data=data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        action_obj = serializer.save(incident=incident)
        return api_response(
            data=CorrectiveActionSerializer(action_obj).data,
            message="Corrective action added",
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["patch"],
        url_path=r"corrective-actions/(?P<action_id>[^/.]+)",
    )
    def update_corrective_action(self, request, pk=None, action_id=None):
        incident = self.get_object()
        try:
            action_obj = incident.corrective_actions.get(pk=action_id)
        except CorrectiveAction.DoesNotExist:
            return api_error(message="Corrective action not found", status=404)
        serializer = CorrectiveActionSerializer(
            action_obj, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        if request.data.get("status") == CorrectiveAction.STATUS_DONE:
            action_obj.completed_at = timezone.now()
            action_obj.save()
        serializer.save()
        return api_response(data=serializer.data, message="Corrective action updated")

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        incident = self.get_object()
        if not SafetyService.can_close_incident(incident):
            return api_error(
                message="All corrective actions must be completed before closing"
            )
        lessons = request.data.get("lessons_learned", "")
        if not lessons:
            return api_error(message="Lessons learned is required")
        incident.lessons_learned = lessons
        incident.prevention_measures = request.data.get("prevention_measures", "")
        incident.status = SafetyIncident.STATUS_CLOSED
        incident.closed_by = request.user
        incident.closed_at = timezone.now()
        incident.save()
        return api_response(
            data=IncidentSerializer(incident).data,
            message="Incident closed",
        )


class SafetyInspectionViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = SafetyInspection.objects.select_related("inspector").prefetch_related(
        "checklist_items"
    )
    filterset_class = SafetyInspectionFilter
    search_fields = ["inspection_number", "area"]
    ordering_fields = ["scheduled_date", "inspection_number"]

    def get_serializer_class(self):
        if self.action == "list":
            return InspectionListSerializer
        return InspectionSerializer

    def get_create_message(self):
        return "Inspection scheduled"

    @action(detail=False, methods=["get"], url_path="checklist-template")
    def checklist_template(self, request):
        area = request.query_params.get("area", "Factory Floor")
        return api_response(data=SafetyService.build_checklist(area))

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        inspection = self.get_object()
        inspection.status = SafetyInspection.STATUS_IN_PROGRESS
        inspection.save()
        return api_response(data=InspectionSerializer(inspection).data)

    @action(detail=True, methods=["patch"], url_path="checklist-items/(?P<item_id>[^/.]+)")
    def update_checklist_item(self, request, pk=None, item_id=None):
        inspection = self.get_object()
        try:
            item = inspection.checklist_items.get(pk=item_id)
        except InspectionChecklistItem.DoesNotExist:
            return api_error(message="Checklist item not found", status=404)
        serializer = ChecklistItemSerializer(item, data=request.data, partial=True)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        serializer.save()
        if inspection.status == SafetyInspection.STATUS_SCHEDULED:
            inspection.status = SafetyInspection.STATUS_IN_PROGRESS
            inspection.save()
        return api_response(data=serializer.data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        inspection = self.get_object()
        notes = request.data.get("notes", "")
        if notes:
            inspection.notes = notes
        inspection = SafetyService.complete_inspection(inspection)
        return api_response(
            data=InspectionSerializer(inspection).data,
            message="Inspection completed",
        )


def _user_has_role(user, role_names):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if user.role and user.role.name in role_names:
        return True
    return False


class PPERequestViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    """PPE request workflow: Safety Officer → Store → Procurement → Issue."""

    queryset = PPERequest.objects.select_related(
        "employee",
        "employee__department",
        "ppe_item",
        "requested_by",
        "store_reviewed_by",
        "purchase_requisition",
        "issuance",
    )
    serializer_class = PPERequestSerializer
    filterset_class = PPERequestFilter
    search_fields = [
        "request_number",
        "employee__first_name",
        "employee__last_name",
        "ppe_item__name",
    ]
    ordering_fields = ["created_at", "status", "priority"]

    STOREKEEPER_ROLES = ("Storekeeper",)
    PROCUREMENT_ROLES = ("Coordinator", "HOD Procurement")
    SAFETY_ROLES = ("Safety Officer",)

    def get_permissions(self):
        if self.action in ("list", "retrieve", "workflow"):
            return [IsAuthenticated()]
        if self.action in ("store_review", "mark_stock_received", "confirm_ready"):
            return [IsAuthenticated()]
        if self.action in ("create", "submit", "issue", "cancel"):
            return [IsAuthenticated(), HasModulePermission()]
        return super().get_permissions()

    def get_required_action(self):
        if self.action in ("store_review", "mark_stock_received", "confirm_ready", "issue"):
            return "update"
        if self.action in ("submit",):
            return "create"
        return super().get_required_action()

    def get_create_message(self):
        return "PPE request created"

    @action(detail=False, methods=["get"])
    def workflow(self, request):
        return api_response(
            data={
                "steps": [
                    {"key": k, "label": label}
                    for k, label in PPERequestService.WORKFLOW_STEPS
                ]
            }
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        req = self.get_object()
        try:
            PPERequestService.submit(req, request.user)
        except ValueError as exc:
            return api_error(message=str(exc))
        req.refresh_from_db()
        return api_response(
            data=PPERequestSerializer(req).data,
            message="PPE request submitted to Store Keeper",
        )

    @action(detail=True, methods=["post"], url_path="store-review")
    def store_review(self, request, pk=None):
        if not _user_has_role(request.user, self.STOREKEEPER_ROLES + ("Super Admin",)):
            return api_error(message="Only Store Keeper can review stock availability")
        req = self.get_object()
        stock_available = request.data.get("stock_available")
        if stock_available is None:
            return api_error(message="stock_available (true/false) is required")
        notes = request.data.get("notes", "")
        try:
            PPERequestService.store_review(
                req, request.user, bool(stock_available), notes
            )
        except ValueError as exc:
            return api_error(message=str(exc))
        req.refresh_from_db()
        msg = (
            "Stock confirmed — ready for issuance"
            if req.stock_available
            else f"Sent to Procurement ({req.purchase_requisition.pr_number if req.purchase_requisition else 'PR'})"
        )
        return api_response(data=PPERequestSerializer(req).data, message=msg)

    @action(detail=True, methods=["post"], url_path="mark-stock-received")
    def mark_stock_received(self, request, pk=None):
        if not _user_has_role(request.user, self.STOREKEEPER_ROLES + ("Super Admin",)):
            return api_error(message="Only Store Keeper can receive stock")
        req = self.get_object()
        try:
            PPERequestService.mark_stock_received(
                req,
                request.user,
                request.data.get("quantity_received"),
                request.data.get("notes", ""),
            )
        except ValueError as exc:
            return api_error(message=str(exc))
        req.refresh_from_db()
        return api_response(
            data=PPERequestSerializer(req).data,
            message="Stock received at store",
        )

    @action(detail=True, methods=["post"], url_path="confirm-ready")
    def confirm_ready(self, request, pk=None):
        if not _user_has_role(
            request.user, self.STOREKEEPER_ROLES + self.SAFETY_ROLES + ("Super Admin",)
        ):
            return api_error(message="Not authorized to confirm readiness")
        req = self.get_object()
        try:
            PPERequestService.confirm_ready(req, request.user)
        except ValueError as exc:
            return api_error(message=str(exc))
        req.refresh_from_db()
        return api_response(
            data=PPERequestSerializer(req).data,
            message="PPE ready for issuance — Safety Officer notified",
        )

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        req = self.get_object()
        try:
            _, issuance = PPERequestService.issue(
                req,
                request.user,
                request.data.get("condition_issued", PPEIssuance.COND_NEW),
                request.data.get("notes", ""),
            )
        except ValueError as exc:
            return api_error(message=str(exc))
        req.refresh_from_db()
        return api_response(
            data={
                "request": PPERequestSerializer(req).data,
                "issuance": PPEIssuanceSerializer(issuance).data,
            },
            message="PPE issued successfully",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        req = self.get_object()
        try:
            PPERequestService.cancel(
                req, request.user, request.data.get("reason", "")
            )
        except ValueError as exc:
            return api_error(message=str(exc))
        req.refresh_from_db()
        return api_response(
            data=PPERequestSerializer(req).data,
            message="PPE request cancelled",
        )


class PPEItemViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = PPEItem.objects.filter(is_active=True)
    serializer_class = PPEItemSerializer
    search_fields = ["name", "ppe_type"]
    ordering_fields = ["ppe_type", "name"]

    def get_create_message(self):
        return "PPE item created"


class PPEIssuanceViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = PPEIssuance.objects.select_related(
        "employee", "employee__department", "ppe_item", "issued_by"
    )
    serializer_class = PPEIssuanceSerializer
    filterset_class = PPEIssuanceFilter
    search_fields = ["employee__first_name", "employee__last_name"]
    ordering_fields = ["issue_date"]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        return self._issue_ppe(request)

    @action(detail=False, methods=["post"])
    def issue(self, request):
        return self._issue_ppe(request)

    def _issue_ppe(self, request):
        ppe_item_id = request.data.get("ppe_item")
        quantity = int(request.data.get("quantity", 1))
        try:
            ppe_item = PPEItem.objects.get(pk=ppe_item_id)
        except PPEItem.DoesNotExist:
            return api_error(message="PPE item not found")
        if ppe_item.stock_on_hand < quantity:
            return api_error(message="Insufficient stock")
        serializer = PPEIssuanceSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        issuance = serializer.save(issued_by=request.user)
        ppe_item.stock_on_hand -= quantity
        ppe_item.total_issued += quantity
        ppe_item.save()
        return api_response(
            data=PPEIssuanceSerializer(issuance).data,
            message="PPE issued",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def return_ppe(self, request, pk=None):
        issuance = self.get_object()
        if issuance.actual_return:
            return api_error(message="PPE already returned")
        condition = request.data.get("condition_returned")
        if condition in ("DAMAGED", "LOST") and not request.data.get("notes"):
            return api_error(message="Notes required for damaged/lost PPE")
        issuance.condition_returned = condition
        issuance.actual_return = request.data.get(
            "actual_return", timezone.now().date()
        )
        issuance.notes = request.data.get("notes", issuance.notes)
        issuance.save()
        if condition == "GOOD":
            issuance.ppe_item.stock_on_hand += issuance.quantity
            issuance.ppe_item.save()
        return api_response(
            data=PPEIssuanceSerializer(issuance).data,
            message="PPE returned",
        )


class PPERoleRequirementViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = PPERoleRequirement.objects.filter(is_active=True)
    serializer_class = PPERoleRequirementSerializer
    search_fields = ["job_title"]


class WorkPermitViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = WorkPermit.objects.select_related(
        "department", "issued_by", "approved_by"
    )
    filterset_class = WorkPermitFilter
    search_fields = ["permit_number", "work_description", "location"]
    ordering_fields = ["valid_from", "permit_number"]

    def get_serializer_class(self):
        if self.action == "list":
            return WorkPermitListSerializer
        return WorkPermitSerializer

    def get_create_message(self):
        return "Work permit created"

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        permit = self.get_object()
        permit.status = WorkPermit.STATUS_PENDING
        permit.save()
        return api_response(
            data=WorkPermitSerializer(permit).data,
            message="Permit submitted for approval",
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        permit = self.get_object()
        if permit.issued_by_id == request.user.id:
            return api_error(message="Cannot approve your own permit")
        permit.status = WorkPermit.STATUS_APPROVED
        permit.approved_by = request.user
        permit.approved_at = timezone.now()
        now = timezone.now()
        if permit.valid_from <= now <= permit.valid_until:
            permit.status = WorkPermit.STATUS_ACTIVE
        permit.save()
        return api_response(
            data=WorkPermitSerializer(permit).data,
            message="Permit approved",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        permit = self.get_object()
        reason = request.data.get("reason", "")
        permit.status = WorkPermit.STATUS_CANCELLED
        permit.rejection_reason = reason
        permit.save()
        return api_response(
            data=WorkPermitSerializer(permit).data,
            message="Permit rejected",
        )

    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        permit = self.get_object()
        if permit.extension_count >= 2:
            return api_error(message="Maximum extensions (2) reached")
        new_until = request.data.get("valid_until")
        if not new_until:
            return api_error(message="valid_until required")
        permit.valid_until = new_until
        permit.extension_count += 1
        permit.status = WorkPermit.STATUS_ACTIVE
        permit.save()
        return api_response(
            data=WorkPermitSerializer(permit).data,
            message="Permit extended",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        permit = self.get_object()
        permit.status = WorkPermit.STATUS_CANCELLED
        permit.save()
        return api_response(
            data=WorkPermitSerializer(permit).data,
            message="Permit cancelled",
        )


class SafetyTrainingViewSet(SafetyViewSetMixin, viewsets.ModelViewSet):
    queryset = SafetyTraining.objects.prefetch_related("attendees__employee")
    filterset_class = SafetyTrainingFilter
    search_fields = ["training_name", "trainer"]
    ordering_fields = ["scheduled_date"]

    def get_serializer_class(self):
        if self.action == "list":
            return TrainingListSerializer
        return TrainingSerializer

    def get_create_message(self):
        return "Training scheduled"

    @action(detail=True, methods=["post"], url_path="mark-attendance")
    def mark_attendance(self, request, pk=None):
        training = self.get_object()
        records = request.data.get("attendees", [])
        updated = []
        for rec in records:
            attendee, _ = TrainingAttendee.objects.update_or_create(
                training=training,
                employee_id=rec["employee"],
                defaults={
                    "attended": rec.get("attended", False),
                    "certificate_issued": rec.get("certificate_issued", False),
                    "certificate_expiry": rec.get("certificate_expiry"),
                    "notes": rec.get("notes", ""),
                },
            )
            updated.append(attendee)
        training.status = SafetyTraining.STATUS_COMPLETED
        training.save()
        return api_response(
            data=TrainingAttendeeSerializer(updated, many=True).data,
            message="Attendance saved",
        )

    @action(detail=True, methods=["post"], url_path="issue-certificate")
    def issue_certificate(self, request, pk=None):
        training = self.get_object()
        employee_id = request.data.get("employee_id")
        try:
            attendee = training.attendees.get(employee_id=employee_id)
        except TrainingAttendee.DoesNotExist:
            return api_error(message="Attendee not found")
        attendee.certificate_issued = True
        expiry = request.data.get("certificate_expiry")
        if expiry:
            attendee.certificate_expiry = expiry
        attendee.save()
        return api_response(
            data=TrainingAttendeeSerializer(attendee).data,
            message="Certificate issued",
        )


class SafetyReportViewSet(SafetyViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="incidents")
    def incident_report(self, request):
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if not date_from or not date_to:
            return api_error(message="date_from and date_to required")
        data = SafetyService.incident_report(
            datetime.strptime(date_from, "%Y-%m-%d").date(),
            datetime.strptime(date_to, "%Y-%m-%d").date(),
        )
        return api_response(data=data)

    @action(detail=False, methods=["get"], url_path="inspections")
    def inspection_report(self, request):
        qs = SafetyInspection.objects.filter(
            status=SafetyInspection.STATUS_COMPLETED
        )
        by_area = list(qs.values("area").annotate(
            pass_count=Count("id"),
        ))
        return api_response(data={"by_area": by_area, "total": qs.count()})

    @action(detail=False, methods=["get"], url_path="monthly-hse")
    def monthly_hse(self, request):
        month = int(request.query_params.get("month", timezone.now().month))
        year = int(request.query_params.get("year", timezone.now().year))
        dashboard = SafetyService.dashboard()
        return api_response(
            data={
                "month": month,
                "year": year,
                "safety_score": dashboard["safety_score"],
                "days_without_incident": dashboard["days_without_incident"],
                "open_incidents": dashboard["open_incidents"],
                "pending_inspections": dashboard["pending_inspections"],
                "active_permits": dashboard["active_permits"],
            }
        )
