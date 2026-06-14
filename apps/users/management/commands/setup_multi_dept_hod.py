"""Assign Naomi (or any user) to multiple department HOD roles."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.users.department_services import sync_user_department_assignments
from apps.users.models import Department, Role, User

HOD_ROLE_NAMES = {
    "Procurement": "HOD Procurement",
    "Sales": "HOD Sales",
    "Logistics": "HOD Logistics",
}


class Command(BaseCommand):
    help = "Configure multi-department HOD access (default: Naomi — Procurement, Sales, Logistics)"

    def add_arguments(self, parser):
        parser.add_argument("--email", default="naomilogistic@rsl.co.tz")
        parser.add_argument("--first-name", default="Naomi")
        parser.add_argument("--last-name", default="Mollel")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            self.stdout.write(self.style.ERROR(f"User not found: {email}"))
            self.stdout.write("Create the user first, then re-run this command.")
            return

        dept_map = {d.name: d for d in Department.objects.filter(is_active=True)}
        required = list(HOD_ROLE_NAMES.keys())
        missing = [name for name in required if name not in dept_map]
        if missing:
            self.stdout.write(self.style.ERROR(f"Missing departments: {', '.join(missing)}. Run seed_fms."))
            return

        assignments = []
        for dept_name in required:
            role = Role.objects.filter(
                name=HOD_ROLE_NAMES[dept_name],
                department=dept_map[dept_name],
            ).first()
            if not role:
                self.stdout.write(self.style.ERROR(f"HOD role missing for {dept_name}"))
                return
            assignments.append(
                {
                    "department": dept_map[dept_name].id,
                    "role": role.id,
                    "is_primary": dept_name == "Procurement",
                }
            )

        sync_user_department_assignments(user, assignments)
        user.first_name = options["first_name"]
        user.last_name = options["last_name"]
        user.is_multi_department = True
        user.save(update_fields=["first_name", "last_name", "is_multi_department", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f"Multi-department HOD configured for {user.email}"))
        for row in assignments:
            dept = Department.objects.get(pk=row["department"])
            role = Role.objects.get(pk=row["role"])
            primary = " (primary)" if row["is_primary"] else ""
            self.stdout.write(f"  {dept.name}: {role.name}{primary}")
        self.stdout.write("  Inventory: read/query (auto for HOD roles)")
        self.stdout.write("User must log out and log back in to refresh permissions.")
