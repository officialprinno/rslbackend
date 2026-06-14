"""
Seed Safety module data.

Prerequisites: seed_fms, seed_hr
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.hr.models import Employee
from apps.safety.models import (
    PPEItem,
    PPERequest,
    PPERoleRequirement,
    SafetyIncident,
    SafetyInspection,
    SafetyTraining,
    TrainingAttendee,
    WorkPermit,
)
from apps.safety.services import SafetyService
from apps.safety.utils import (
    generate_incident_number,
    generate_inspection_number,
    generate_permit_number,
    generate_ppe_request_number,
)
from apps.users.models import Department, User

PPE_ITEMS = [
    ("HELMET", "Safety Helmet — Mining Grade", "EN 397", 45, 10),
    ("GLOVES", "Cut-Resistant Gloves", "EN 388", 80, 15),
    ("SAFETY_BOOTS", "Steel Toe Boots", "EN ISO 20345", 35, 10),
    ("VEST", "High-Vis Safety Vest", "EN ISO 20471", 60, 20),
    ("GOGGLES", "Safety Goggles", "EN 166", 50, 10),
    ("EAR_PROTECTION", "Ear Plugs — Disposable", "EN 352", 200, 50),
    ("HARNESS", "Fall Arrest Harness", "EN 361", 12, 5),
    ("RESPIRATOR", "Dust Respirator FFP2", "EN 149", 100, 25),
]

PPE_REQUIREMENTS = [
    ("Machine Operator", ["HELMET", "GOGGLES", "GLOVES", "SAFETY_BOOTS", "VEST"]),
    ("Storekeeper", ["SAFETY_BOOTS", "VEST", "GLOVES"]),
    ("Logistics Officer", ["SAFETY_BOOTS", "VEST"]),
    ("Sales Officer", ["SAFETY_BOOTS"]),
]


class Command(BaseCommand):
    help = "Seed safety incidents, inspections, PPE, permits, and training"

    @transaction.atomic
    def handle(self, *args, **options):
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR("No admin user. Run seed_fms."))
            return

        employees = list(Employee.objects.filter(is_active=True)[:5])
        if not employees:
            self.stdout.write(self.style.ERROR("No employees. Run seed_hr."))
            return

        dept = Department.objects.first()

        for ppe_type, name, standard, stock, reorder in PPE_ITEMS:
            PPEItem.objects.get_or_create(
                ppe_type=ppe_type,
                name=name,
                defaults={
                    "safety_standard": standard,
                    "stock_on_hand": stock,
                    "reorder_level": reorder,
                    "total_issued": 0,
                },
            )

        for title, types in PPE_REQUIREMENTS:
            PPERoleRequirement.objects.get_or_create(
                job_title=title,
                defaults={"required_ppe_types": types},
            )

        now = timezone.now()

        if not SafetyIncident.objects.exists():
            SafetyIncident.objects.create(
                incident_number=generate_incident_number(),
                incident_type=SafetyIncident.TYPE_NEAR_MISS,
                severity=SafetyIncident.SEV_MEDIUM,
                date_occurred=now - timedelta(days=45),
                location="Factory Floor",
                department=dept,
                description="Operator nearly caught hand in conveyor belt during maintenance. "
                "Machine was not locked out. Immediate stop applied.",
                immediate_actions="Machine isolated and LOTO applied. Area cordoned off.",
                anyone_injured=False,
                status=SafetyIncident.STATUS_CLOSED,
                reported_by=admin,
                lessons_learned="Always apply LOTO before maintenance.",
                closed_by=admin,
                closed_at=now - timedelta(days=30),
            )
            SafetyIncident.objects.create(
                incident_number=generate_incident_number(),
                incident_type=SafetyIncident.TYPE_NEAR_MISS,
                severity=SafetyIncident.SEV_LOW,
                date_occurred=now - timedelta(days=5),
                location="Warehouse",
                department=dept,
                description="Forklift operator reversed without checking mirrors. "
                "No collision occurred but pedestrian was in blind spot.",
                immediate_actions="Operator retrained on reversing procedure.",
                anyone_injured=False,
                status=SafetyIncident.STATUS_INVESTIGATING,
                reported_by=admin,
                investigator=admin,
                investigated_at=now - timedelta(days=3),
            )

        if not SafetyInspection.objects.exists():
            insp = SafetyInspection.objects.create(
                inspection_number=generate_inspection_number(),
                inspection_type=SafetyInspection.TYPE_WEEKLY,
                area="Factory Floor",
                scheduled_date=now + timedelta(days=2),
                inspector=admin,
                status=SafetyInspection.STATUS_SCHEDULED,
            )
            for item in SafetyService.build_checklist("Factory Floor"):
                from apps.safety.models import InspectionChecklistItem

                InspectionChecklistItem.objects.create(inspection=insp, **item)
            insp.total_items = insp.checklist_items.count()
            insp.save()

            past = SafetyInspection.objects.create(
                inspection_number=generate_inspection_number(),
                inspection_type=SafetyInspection.TYPE_DAILY,
                area="Warehouse",
                scheduled_date=now - timedelta(days=3),
                inspector=admin,
                status=SafetyInspection.STATUS_COMPLETED,
                overall_result=SafetyInspection.RESULT_PASS,
                total_items=4,
                passed_items=4,
                failed_items=0,
            )

        if not WorkPermit.objects.exists():
            WorkPermit.objects.create(
                permit_number=generate_permit_number(),
                permit_type=WorkPermit.TYPE_HOT,
                work_description="Welding repair on conveyor frame",
                location="Factory Floor",
                department=dept,
                workers=[{"name": employees[0].full_name, "id": employees[0].employee_number}],
                valid_from=now,
                valid_until=now + timedelta(hours=8),
                hazards=["Fire", "Burns"],
                risk_level=WorkPermit.RISK_MEDIUM,
                control_measures="Fire extinguisher on standby. Fire watch assigned.",
                safety_checklist=SafetyService.build_permit_checklist(WorkPermit.TYPE_HOT),
                issued_by=admin,
                approved_by=admin,
                approved_at=now,
                status=WorkPermit.STATUS_ACTIVE,
            )

        helmet = PPEItem.objects.filter(ppe_type="HELMET").first()
        if helmet and not PPERequest.objects.exists():
            PPERequest.objects.create(
                request_number=generate_ppe_request_number(),
                employee=employees[0],
                ppe_item=helmet,
                quantity=5,
                priority=PPERequest.PRIORITY_URGENT,
                reason="New machine operators require safety helmets before site assignment.",
                status=PPERequest.STATUS_PENDING_STORE,
                requested_by=admin,
                submitted_at=now,
            )

        if not SafetyTraining.objects.exists():
            training = SafetyTraining.objects.create(
                training_name="Safety Induction — New Employees",
                training_type=SafetyTraining.TYPE_INDUCTION,
                description="Mandatory safety induction for all new employees",
                trainer="Grace Kimaro",
                scheduled_date=now + timedelta(days=7),
                duration_hours=Decimal("4"),
                location="Main Conference Room",
                max_attendees=30,
                status=SafetyTraining.STATUS_SCHEDULED,
                created_by=admin,
            )
            for emp in employees[:3]:
                TrainingAttendee.objects.get_or_create(
                    training=training,
                    employee=emp,
                )

        self.stdout.write(self.style.SUCCESS("Safety seed data created."))
