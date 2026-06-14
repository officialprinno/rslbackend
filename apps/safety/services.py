"""Safety business logic."""

from datetime import timedelta

from django.db.models import Count, F
from django.utils import timezone

from apps.safety.models import (
    CorrectiveAction,
    InspectionChecklistItem,
    PPEItem,
    SafetyIncident,
    SafetyInspection,
    SafetyTraining,
    WorkPermit,
)

CHECKLIST_TEMPLATES = {
    "Factory Floor": {
        "FIRE SAFETY": [
            "Fire extinguishers accessible and charged",
            "Fire exits clear and marked",
            "No flammable materials near heat sources",
            "Fire alarm system functional",
            "Emergency evacuation route displayed",
        ],
        "MACHINERY SAFETY": [
            "Machine guards in place",
            "Emergency stop buttons functional",
            "Machinery properly maintained",
            "No unauthorized modifications",
            "Operators wearing correct PPE",
        ],
        "HOUSEKEEPING": [
            "Work areas clean and tidy",
            "No slip/trip hazards",
            "Waste properly disposed",
            "Tools stored correctly",
        ],
        "ELECTRICAL": [
            "No exposed wiring",
            "Electrical panels accessible",
            "No overloaded sockets",
            "Ground connections secure",
        ],
    },
    "Warehouse": {
        "GENERAL": [
            "Aisles clear and marked",
            "Racking secure and labelled",
            "Forklift paths clear",
            "PPE worn in warehouse",
        ],
    },
}

PERMIT_CHECKLISTS = {
    "HOT_WORK": [
        "Fire extinguisher on standby",
        "Fire watch assigned",
        "Combustibles removed (10m radius)",
        "Hot work area barricaded",
        "Welding screens in place",
    ],
    "CONFINED_SPACE": [
        "Atmospheric test completed",
        "Rescue equipment on standby",
        "Attendant assigned outside",
        "Communication established",
        "Ventilation provided",
    ],
    "ELECTRICAL": [
        "Lockout/Tagout applied",
        "Area barricaded",
        "Insulated tools available",
        "First aider on standby",
    ],
    "HEIGHT_WORK": [
        "Harness inspected",
        "Anchor points verified",
        "Area below barricaded",
        "Weather conditions checked",
        "Rescue plan in place",
    ],
}


class SafetyService:
    @staticmethod
    def days_without_incident():
        last_reset = (
            SafetyIncident.objects.filter(
                is_active=True,
                incident_type__in=[
                    SafetyIncident.TYPE_ACCIDENT,
                    SafetyIncident.TYPE_DANGEROUS,
                ],
            )
            .exclude(status=SafetyIncident.STATUS_DRAFT)
            .order_by("-date_occurred")
            .first()
        )
        if not last_reset:
            return 365
        return (timezone.now().date() - last_reset.date_occurred.date()).days

    @staticmethod
    def safety_score():
        today = timezone.now().date()
        month_start = today.replace(day=1)

        inspections = SafetyInspection.objects.filter(
            scheduled_date__date__gte=month_start
        )
        total_insp = inspections.count()
        on_time = inspections.filter(
            status=SafetyInspection.STATUS_COMPLETED,
            scheduled_date__date__lte=today,
        ).count()
        inspection_score = (on_time / total_insp * 100) if total_insp else 100

        incidents = SafetyIncident.objects.filter(
            date_occurred__date__gte=month_start,
            status__in=[
                SafetyIncident.STATUS_OPEN,
                SafetyIncident.STATUS_INVESTIGATING,
            ],
        ).count()
        incident_score = max(0, 100 - incidents * 15)

        ppe_low = PPEItem.objects.filter(
            is_active=True, stock_on_hand__lte=F("reorder_level")
        ).count()
        ppe_score = max(0, 100 - ppe_low * 10)

        expired = WorkPermit.objects.filter(status=WorkPermit.STATUS_EXPIRED).count()
        permit_score = max(0, 100 - expired * 20)

        score = (
            inspection_score * 0.30
            + incident_score * 0.30
            + ppe_score * 0.20
            + permit_score * 0.20
        )
        return round(score, 1)

    @staticmethod
    def dashboard():
        today = timezone.now().date()
        month_start = today.replace(day=1)
        week_ahead = today + timedelta(days=7)

        open_incidents = SafetyIncident.objects.filter(
            status__in=[
                SafetyIncident.STATUS_OPEN,
                SafetyIncident.STATUS_INVESTIGATING,
            ],
            date_occurred__date__gte=month_start,
        ).count()

        pending_inspections = SafetyInspection.objects.filter(
            status__in=[
                SafetyInspection.STATUS_SCHEDULED,
                SafetyInspection.STATUS_IN_PROGRESS,
            ]
        ).count()

        active_permits = WorkPermit.objects.filter(
            status=WorkPermit.STATUS_ACTIVE
        ).count()

        ppe_low = PPEItem.objects.filter(
            is_active=True, stock_on_hand__lte=F("reorder_level")
        ).count()

        overdue_ca = CorrectiveAction.objects.filter(
            status__in=[
                CorrectiveAction.STATUS_OPEN,
                CorrectiveAction.STATUS_IN_PROGRESS,
            ],
            due_date__lt=today,
        ).count()

        chart = []
        for i in range(11, -1, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            accidents = SafetyIncident.objects.filter(
                date_occurred__month=m,
                date_occurred__year=y,
                incident_type__in=[
                    SafetyIncident.TYPE_ACCIDENT,
                    SafetyIncident.TYPE_DANGEROUS,
                ],
            ).count()
            near_miss = SafetyIncident.objects.filter(
                date_occurred__month=m,
                date_occurred__year=y,
                incident_type=SafetyIncident.TYPE_NEAR_MISS,
            ).count()
            chart.append({
                "month": f"{m:02d}/{y}",
                "accidents": accidents,
                "near_miss": near_miss,
            })

        recent = SafetyIncident.objects.filter(
            status__in=[
                SafetyIncident.STATUS_OPEN,
                SafetyIncident.STATUS_INVESTIGATING,
                SafetyIncident.STATUS_CLOSED,
            ]
        ).select_related("department", "reported_by", "injured_person")[:5]

        upcoming = SafetyInspection.objects.filter(
            scheduled_date__date__gte=today,
            scheduled_date__date__lte=week_ahead,
            status=SafetyInspection.STATUS_SCHEDULED,
        ).select_related("inspector")[:10]

        alerts = []
        for p in WorkPermit.objects.filter(
            status=WorkPermit.STATUS_EXPIRED, is_active=True
        )[:5]:
            alerts.append({
                "type": "EXPIRED_PERMIT",
                "severity": "HIGH",
                "message": f"Expired permit {p.permit_number}",
                "reference_id": p.id,
                "created_at": p.valid_until.isoformat(),
            })
        for insp in SafetyInspection.objects.filter(
            status=SafetyInspection.STATUS_SCHEDULED,
            scheduled_date__date__lt=today,
        )[:5]:
            alerts.append({
                "type": "OVERDUE_INSPECTION",
                "severity": "MEDIUM",
                "message": f"Overdue inspection {insp.inspection_number}",
                "reference_id": insp.id,
                "created_at": insp.scheduled_date.isoformat(),
            })
        for inc in SafetyIncident.objects.filter(
            severity=SafetyIncident.SEV_CRITICAL,
            status__in=[
                SafetyIncident.STATUS_OPEN,
                SafetyIncident.STATUS_INVESTIGATING,
            ],
        )[:5]:
            alerts.append({
                "type": "OPEN_CRITICAL",
                "severity": "CRITICAL",
                "message": f"Critical incident {inc.incident_number}",
                "reference_id": inc.id,
                "created_at": inc.date_occurred.isoformat(),
            })
        for ppe in PPEItem.objects.filter(
            is_active=True, stock_on_hand__lte=F("reorder_level")
        )[:5]:
            alerts.append({
                "type": "PPE_LOW",
                "severity": "MEDIUM",
                "message": f"Low stock: {ppe.name}",
                "reference_id": ppe.id,
                "created_at": today.isoformat(),
            })
        for t in SafetyTraining.objects.filter(
            status=SafetyTraining.STATUS_SCHEDULED,
            scheduled_date__date__lte=week_ahead,
        )[:5]:
            alerts.append({
                "type": "TRAINING_DUE",
                "severity": "LOW",
                "message": f"Training due: {t.training_name}",
                "reference_id": t.id,
                "created_at": t.scheduled_date.isoformat(),
            })

        return {
            "days_without_incident": SafetyService.days_without_incident(),
            "open_incidents": open_incidents,
            "pending_inspections": pending_inspections,
            "active_permits": active_permits,
            "ppe_low_stock": ppe_low,
            "overdue_corrective_actions": overdue_ca,
            "safety_score": SafetyService.safety_score(),
            "incidents_chart": chart,
            "recent_incidents": recent,
            "upcoming_inspections": upcoming,
            "alerts": alerts,
        }

    @staticmethod
    def build_checklist(area):
        template = CHECKLIST_TEMPLATES.get(
            area, CHECKLIST_TEMPLATES.get("Factory Floor", {})
        )
        items = []
        for section, lines in template.items():
            for line in lines:
                items.append({"section": section, "checklist_item": line})
        return items

    @staticmethod
    def build_permit_checklist(permit_type):
        lines = PERMIT_CHECKLISTS.get(permit_type, [])
        return [{"item": line, "checked": False} for line in lines]

    @staticmethod
    def complete_inspection(inspection):
        items = inspection.checklist_items.all()
        total = items.count()
        passed = items.filter(result=InspectionChecklistItem.RESULT_PASS).count()
        failed = items.filter(result=InspectionChecklistItem.RESULT_FAIL).count()

        if failed > 0:
            result = SafetyInspection.RESULT_FAIL
        elif items.filter(result__isnull=True).exists():
            result = SafetyInspection.RESULT_CONDITIONAL
        else:
            result = SafetyInspection.RESULT_PASS

        inspection.total_items = total
        inspection.passed_items = passed
        inspection.failed_items = failed
        inspection.overall_result = result
        inspection.status = SafetyInspection.STATUS_COMPLETED
        inspection.save()

        if failed > 0:
            for item in items.filter(result=InspectionChecklistItem.RESULT_FAIL):
                CorrectiveAction.objects.create(
                    inspection=inspection,
                    action=f"Fix failed inspection item: {item.checklist_item}",
                    due_date=timezone.now().date() + timedelta(days=7),
                    priority=CorrectiveAction.PRIORITY_HIGH,
                )
        return inspection

    @staticmethod
    def can_close_incident(incident):
        return (
            incident.corrective_actions.exclude(
                status=CorrectiveAction.STATUS_DONE
            ).count()
            == 0
        )

    @staticmethod
    def incident_report(date_from, date_to):
        qs = SafetyIncident.objects.filter(
            date_occurred__date__gte=date_from,
            date_occurred__date__lte=date_to,
        ).exclude(status=SafetyIncident.STATUS_DRAFT)
        return {
            "period_from": date_from.isoformat(),
            "period_to": date_to.isoformat(),
            "total": qs.count(),
            "by_type": list(qs.values("incident_type").annotate(count=Count("id"))),
            "by_severity": list(qs.values("severity").annotate(count=Count("id"))),
            "by_department": list(
                qs.values("department__name").annotate(count=Count("id"))
            ),
            "ltifr": 0,
        }
