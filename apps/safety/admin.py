from django.contrib import admin

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


@admin.register(SafetyIncident)
class SafetyIncidentAdmin(admin.ModelAdmin):
    list_display = ["incident_number", "incident_type", "severity", "status", "date_occurred"]
    search_fields = ["incident_number", "description"]
    list_filter = ["incident_type", "severity", "status"]


@admin.register(SafetyInspection)
class SafetyInspectionAdmin(admin.ModelAdmin):
    list_display = ["inspection_number", "area", "inspection_type", "status", "overall_result"]
    list_filter = ["status", "inspection_type"]


@admin.register(PPERequest)
class PPERequestAdmin(admin.ModelAdmin):
    list_display = ["request_number", "employee", "ppe_item", "quantity", "status"]
    list_filter = ["status", "priority"]
    search_fields = ["request_number"]


@admin.register(PPEItem)
class PPEItemAdmin(admin.ModelAdmin):
    list_display = ["name", "ppe_type", "stock_on_hand", "reorder_level"]


@admin.register(WorkPermit)
class WorkPermitAdmin(admin.ModelAdmin):
    list_display = ["permit_number", "permit_type", "status", "valid_from", "valid_until"]
    list_filter = ["permit_type", "status"]


@admin.register(SafetyTraining)
class SafetyTrainingAdmin(admin.ModelAdmin):
    list_display = ["training_name", "training_type", "scheduled_date", "status"]
