"""Serializers for the Safety module."""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.safety.models import (
    CorrectiveAction,
    IncidentWitness,
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
from apps.safety.services import SafetyService
from apps.safety.utils import (
    generate_incident_number,
    generate_inspection_number,
    generate_permit_number,
    generate_ppe_request_number,
)


class WitnessSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentWitness
        fields = ["id", "name", "is_employee", "employee", "contact", "statement"]


class CorrectiveActionSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()

    class Meta:
        model = CorrectiveAction
        fields = [
            "id", "incident_id", "action", "assigned_to", "assigned_to_name",
            "due_date", "priority", "status", "completed_at",
        ]

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            return obj.assigned_to.get_full_name() or obj.assigned_to.username
        return None


class ChecklistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionChecklistItem
        fields = [
            "id", "inspection_id", "section", "checklist_item",
            "result", "remarks", "photo_url",
        ]


class IncidentListSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    injured_person_name = serializers.SerializerMethodField()
    reported_by_name = serializers.SerializerMethodField()
    days_open = serializers.IntegerField(read_only=True)

    class Meta:
        model = SafetyIncident
        fields = [
            "id", "incident_number", "incident_type", "severity", "date_occurred",
            "location", "department_id", "department_name", "description",
            "injured_person_id", "injured_person_name", "reported_by_name",
            "status", "days_open", "created_at",
        ]

    def get_injured_person_name(self, obj):
        return obj.injured_person.full_name if obj.injured_person else None

    def get_reported_by_name(self, obj):
        return obj.reported_by.get_full_name() or obj.reported_by.username


class IncidentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    injured_person_name = serializers.SerializerMethodField()
    reported_by_name = serializers.SerializerMethodField()
    closed_by_name = serializers.SerializerMethodField()
    investigator_name = serializers.SerializerMethodField()
    days_open = serializers.IntegerField(read_only=True)
    witnesses = WitnessSerializer(many=True, required=False)
    corrective_actions = CorrectiveActionSerializer(many=True, read_only=True)

    class Meta:
        model = SafetyIncident
        fields = [
            "id", "incident_number", "incident_type", "severity", "date_occurred",
            "location", "department", "department_name", "description",
            "immediate_actions", "anyone_injured", "injured_person",
            "injured_person_name", "injury_description", "body_parts",
            "medical_treatment_required", "hospitalized", "first_aid_given",
            "first_aid_provider", "photos", "documents", "cctv_reference",
            "immediate_cause", "contributing_factors", "root_cause",
            "root_cause_categories", "why_analysis", "investigation_findings",
            "investigator", "investigator_name", "investigated_at",
            "lessons_learned", "prevention_measures", "status", "days_open",
            "reported_by", "reported_by_name", "closed_by", "closed_by_name",
            "closed_at", "witnesses", "corrective_actions", "created_at",
        ]
        read_only_fields = ["incident_number", "reported_by"]

    def get_injured_person_name(self, obj):
        return obj.injured_person.full_name if obj.injured_person else None

    def get_reported_by_name(self, obj):
        return obj.reported_by.get_full_name() or obj.reported_by.username

    def get_closed_by_name(self, obj):
        if obj.closed_by:
            return obj.closed_by.get_full_name() or obj.closed_by.username
        return None

    def get_investigator_name(self, obj):
        if obj.investigator:
            return obj.investigator.get_full_name() or obj.investigator.username
        return None

    @transaction.atomic
    def create(self, validated_data):
        witnesses_data = validated_data.pop("witnesses", [])
        validated_data["incident_number"] = generate_incident_number()
        validated_data["reported_by"] = self.context["request"].user
        incident = SafetyIncident.objects.create(**validated_data)
        for w in witnesses_data:
            IncidentWitness.objects.create(incident=incident, **w)
        return incident

    @transaction.atomic
    def update(self, instance, validated_data):
        witnesses_data = validated_data.pop("witnesses", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if witnesses_data is not None:
            instance.witnesses.all().delete()
            for w in witnesses_data:
                IncidentWitness.objects.create(incident=instance, **w)
        return instance


class InspectionListSerializer(serializers.ModelSerializer):
    inspector_name = serializers.SerializerMethodField()

    class Meta:
        model = SafetyInspection
        fields = [
            "id", "inspection_number", "inspection_type", "area",
            "scheduled_date", "inspector_id", "inspector_name",
            "overall_result", "total_items", "passed_items", "failed_items",
            "status", "next_inspection", "created_at",
        ]

    def get_inspector_name(self, obj):
        return obj.inspector.get_full_name() or obj.inspector.username


class InspectionSerializer(serializers.ModelSerializer):
    inspector_name = serializers.SerializerMethodField()
    checklist_items = ChecklistItemSerializer(many=True, read_only=True)

    class Meta:
        model = SafetyInspection
        fields = [
            "id", "inspection_number", "inspection_type", "area",
            "scheduled_date", "inspector", "inspector_name",
            "overall_result", "total_items", "passed_items", "failed_items",
            "next_inspection", "status", "notes", "checklist_items", "created_at",
        ]
        read_only_fields = ["inspection_number"]

    def get_inspector_name(self, obj):
        return obj.inspector.get_full_name() or obj.inspector.username

    @transaction.atomic
    def create(self, validated_data):
        validated_data["inspection_number"] = generate_inspection_number()
        inspection = SafetyInspection.objects.create(**validated_data)
        for item in SafetyService.build_checklist(inspection.area):
            InspectionChecklistItem.objects.create(inspection=inspection, **item)
        inspection.total_items = inspection.checklist_items.count()
        inspection.save()
        return inspection


class PPEItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PPEItem
        fields = [
            "id", "ppe_type", "name", "safety_standard", "inventory_item",
            "total_issued", "stock_on_hand", "reorder_level", "is_active",
        ]


class PPEIssuanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(
        source="employee.department.name", read_only=True
    )
    ppe_type = serializers.CharField(source="ppe_item.ppe_type", read_only=True)
    ppe_name = serializers.CharField(source="ppe_item.name", read_only=True)
    issued_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PPEIssuance
        fields = [
            "id", "employee", "employee_name", "department_name",
            "ppe_item", "ppe_type", "ppe_name", "quantity", "issue_date",
            "expected_return", "actual_return", "condition_issued",
            "condition_returned", "issued_by", "issued_by_name", "notes",
        ]
        read_only_fields = ["issued_by"]

    def get_issued_by_name(self, obj):
        if obj.issued_by:
            return obj.issued_by.get_full_name() or obj.issued_by.username
        return None


class NewPPEItemSerializer(serializers.Serializer):
    ppe_type = serializers.ChoiceField(choices=PPEItem.TYPE_CHOICES)
    name = serializers.CharField(max_length=150)
    safety_standard = serializers.CharField(max_length=100, required=False, allow_blank=True)


class PPERequestSerializer(serializers.ModelSerializer):
    new_ppe_item = NewPPEItemSerializer(write_only=True, required=False)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(
        source="employee.department.name", read_only=True
    )
    ppe_type = serializers.CharField(source="ppe_item.ppe_type", read_only=True)
    ppe_name = serializers.CharField(source="ppe_item.name", read_only=True)
    stock_on_hand = serializers.IntegerField(
        source="ppe_item.stock_on_hand", read_only=True
    )
    requested_by_name = serializers.SerializerMethodField()
    store_reviewed_by_name = serializers.SerializerMethodField()
    pr_number = serializers.CharField(
        source="purchase_requisition.pr_number", read_only=True, allow_null=True
    )
    workflow_step = serializers.SerializerMethodField()

    class Meta:
        model = PPERequest
        fields = [
            "id", "request_number", "employee", "employee_name", "department_name",
            "ppe_item", "new_ppe_item", "ppe_type", "ppe_name", "stock_on_hand", "quantity",
            "priority", "reason", "status", "requested_by", "requested_by_name",
            "submitted_at", "store_reviewed_by", "store_reviewed_by_name",
            "store_reviewed_at", "store_notes", "stock_available",
            "purchase_requisition", "pr_number", "procurement_notes",
            "stock_received_at", "ready_at", "issuance", "issued_at",
            "cancelled_at", "cancellation_reason", "requested_new_item",
            "workflow_step", "created_at",
        ]
        read_only_fields = [
            "request_number", "status", "requested_by", "submitted_at",
            "store_reviewed_by", "store_reviewed_at", "stock_available",
            "purchase_requisition", "procurement_notes", "stock_received_at",
            "ready_at", "issuance", "issued_at", "cancelled_at", "requested_new_item",
        ]
        extra_kwargs = {"ppe_item": {"required": False, "allow_null": True}}

    def get_requested_by_name(self, obj):
        if obj.requested_by:
            return obj.requested_by.get_full_name() or obj.requested_by.username
        return None

    def get_store_reviewed_by_name(self, obj):
        if obj.store_reviewed_by:
            return (
                obj.store_reviewed_by.get_full_name()
                or obj.store_reviewed_by.username
            )
        return None

    def get_workflow_step(self, obj):
        return PPERequestService.workflow_index(obj.status, obj.stock_available)

    def validate(self, attrs):
        ppe_item = attrs.get("ppe_item")
        new_ppe_item = attrs.get("new_ppe_item")
        if not ppe_item and not new_ppe_item:
            raise serializers.ValidationError(
                "Select an existing PPE item or provide details for a new item."
            )
        if ppe_item and new_ppe_item:
            raise serializers.ValidationError(
                "Provide either ppe_item or new_ppe_item, not both."
            )
        return attrs

    def create(self, validated_data):
        new_ppe_data = validated_data.pop("new_ppe_item", None)
        requested_new_item = False
        if new_ppe_data:
            ppe_item = PPEItem.objects.create(
                ppe_type=new_ppe_data["ppe_type"],
                name=new_ppe_data["name"],
                safety_standard=new_ppe_data.get("safety_standard", ""),
                stock_on_hand=0,
                reorder_level=10,
            )
            validated_data["ppe_item"] = ppe_item
            requested_new_item = True
        validated_data["request_number"] = generate_ppe_request_number()
        validated_data["requested_by"] = self.context["request"].user
        validated_data["requested_new_item"] = requested_new_item
        return PPERequest.objects.create(**validated_data)


class PPERoleRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = PPERoleRequirement
        fields = ["id", "job_title", "required_ppe_types", "is_active"]


class WorkPermitListSerializer(serializers.ModelSerializer):
    issued_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkPermit
        fields = [
            "id", "permit_number", "permit_type", "work_description", "location",
            "valid_from", "valid_until", "issued_by_name", "approved_by_name",
            "risk_level", "status", "created_at",
        ]

    def get_issued_by_name(self, obj):
        return obj.issued_by.get_full_name() or obj.issued_by.username

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return None


class WorkPermitSerializer(serializers.ModelSerializer):
    issued_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = WorkPermit
        fields = [
            "id", "permit_number", "permit_type", "work_description", "location",
            "department", "department_name", "workers", "equipment_tools",
            "valid_from", "valid_until", "hazards", "risk_level",
            "control_measures", "safety_checklist", "extension_count",
            "issued_by", "issued_by_name", "approved_by", "approved_by_name",
            "approved_at", "status", "rejection_reason", "created_at",
        ]
        read_only_fields = ["permit_number", "issued_by", "extension_count"]

    def get_issued_by_name(self, obj):
        return obj.issued_by.get_full_name() or obj.issued_by.username

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return None

    def create(self, validated_data):
        validated_data["permit_number"] = generate_permit_number()
        validated_data["issued_by"] = self.context["request"].user
        permit_type = validated_data.get("permit_type", "GENERAL")
        if not validated_data.get("safety_checklist"):
            validated_data["safety_checklist"] = SafetyService.build_permit_checklist(
                permit_type
            )
        return WorkPermit.objects.create(**validated_data)


class TrainingAttendeeSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    department_name = serializers.CharField(
        source="employee.department.name", read_only=True
    )

    class Meta:
        model = TrainingAttendee
        fields = [
            "id", "training_id", "employee", "employee_name", "department_name",
            "attended", "certificate_issued", "certificate_expiry", "notes",
        ]


class TrainingListSerializer(serializers.ModelSerializer):
    attendees_count = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()

    class Meta:
        model = SafetyTraining
        fields = [
            "id", "training_name", "training_type", "trainer", "scheduled_date",
            "duration_hours", "location", "max_attendees", "attendees_count",
            "completion_rate", "status", "created_at",
        ]

    def get_attendees_count(self, obj):
        return obj.attendees.count()

    def get_completion_rate(self, obj):
        total = obj.attendees.count()
        if not total:
            return 0
        attended = obj.attendees.filter(attended=True).count()
        return round(attended / total * 100, 1)


class TrainingSerializer(serializers.ModelSerializer):
    attendees = TrainingAttendeeSerializer(many=True, read_only=True)
    attendees_count = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()

    class Meta:
        model = SafetyTraining
        fields = [
            "id", "training_name", "training_type", "description", "trainer",
            "scheduled_date", "duration_hours", "location", "max_attendees",
            "attendees_count", "completion_rate", "status", "materials_notes",
            "attendees", "created_at",
        ]
        read_only_fields = ["created_by"]

    def get_attendees_count(self, obj):
        return obj.attendees.count()

    def get_completion_rate(self, obj):
        total = obj.attendees.count()
        if not total:
            return 0
        attended = obj.attendees.filter(attended=True).count()
        return round(attended / total * 100, 1)

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return SafetyTraining.objects.create(**validated_data)


class SafetyDashboardSerializer(serializers.Serializer):
    days_without_incident = serializers.IntegerField()
    open_incidents = serializers.IntegerField()
    pending_inspections = serializers.IntegerField()
    active_permits = serializers.IntegerField()
    ppe_low_stock = serializers.IntegerField()
    overdue_corrective_actions = serializers.IntegerField()
    safety_score = serializers.FloatField()
    incidents_chart = serializers.ListField()
    recent_incidents = IncidentListSerializer(many=True)
    upcoming_inspections = InspectionListSerializer(many=True)
    alerts = serializers.ListField()
