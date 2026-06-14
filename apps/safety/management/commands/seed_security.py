"""Seed Security sub-department data."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.hr.models import Employee
from apps.safety.security_models import (
    AccessZone,
    SecurityLocation,
    SecurityPersonnel,
    SecurityShift,
    SecurityShiftOfficer,
    Visitor,
)
from apps.safety.utils import generate_visitor_number
from apps.users.models import User


MAIN_ZONES = [
    ("Main Gate", "PUBLIC"),
    ("Reception", "PUBLIC"),
    ("Main Warehouse", "STAFF_ONLY"),
    ("Finance Office", "AUTHORIZED_ONLY"),
    ("GM Office", "RESTRICTED"),
    ("Server Room", "RESTRICTED"),
    ("Parking", "PUBLIC"),
]

STEIN_ZONES = [
    ("Factory Gate", "PUBLIC"),
    ("Production Floor", "AUTHORIZED_ONLY"),
    ("Factory Store", "STAFF_ONLY"),
    ("Machine Room", "RESTRICTED"),
    ("QC Area", "AUTHORIZED_ONLY"),
    ("Finished Goods Area", "STAFF_ONLY"),
]


class Command(BaseCommand):
    help = "Seed security locations, zones, and sample data"

    @transaction.atomic
    def handle(self, *args, **options):
        main, _ = SecurityLocation.objects.update_or_create(
            name="Main Office",
            defaults={
                "address": "Plot 252 Block L, Misungwi, Mwanza",
                "description": "All offices, main warehouse, reception",
                "color": "#1B3A6B",
                "icon": "🏢",
                "is_active": True,
            },
        )
        stein, _ = SecurityLocation.objects.update_or_create(
            name="Stein",
            defaults={
                "address": "~2.5km from Main Office, Mwanza",
                "description": "Wire mesh factory, factory store, production floor",
                "color": "#F0A500",
                "icon": "🏭",
                "is_active": True,
            },
        )
        self.stdout.write("  Locations: Main Office, Stein")

        for name, level in MAIN_ZONES:
            AccessZone.objects.get_or_create(
                location=main, name=name, defaults={"access_level": level}
            )
        for name, level in STEIN_ZONES:
            AccessZone.objects.get_or_create(
                location=stein, name=name, defaults={"access_level": level}
            )
        self.stdout.write(f"  Access zones: {AccessZone.objects.count()}")

        today = timezone.now().date()
        shift, _ = SecurityShift.objects.get_or_create(
            date=today,
            shift_type=SecurityShift.SHIFT_MORNING,
            location=main,
            defaults={"status": SecurityShift.STATUS_ACTIVE},
        )
        admin = User.objects.filter(is_superuser=True).first()
        if admin and not shift.officers.exists():
            SecurityShiftOfficer.objects.get_or_create(
                shift=shift, officer=admin, defaults={"post_station": "Main Gate"}
            )

        host = Employee.objects.filter(is_active=True).first()
        if host and not Visitor.objects.filter(full_name="John Mining Visitor").exists():
            now = timezone.now()
            Visitor.objects.create(
                visitor_number=generate_visitor_number(),
                full_name="John Mining Visitor",
                id_type=Visitor.ID_NATIONAL,
                id_number="19800101-12345-67890-12",
                phone="255712345678",
                company="John Mining Co.",
                purpose=Visitor.PURPOSE_MEETING,
                host_employee=host,
                department=host.department,
                location=main,
                expected_time_in=now,
                expected_time_out=now + timedelta(hours=2),
                actual_time_in=now,
                status=Visitor.STATUS_SIGNED_IN,
                registered_by=admin,
            )
            self.stdout.write("  Sample visitor on site")

        self.stdout.write(self.style.SUCCESS("Security seed complete"))
