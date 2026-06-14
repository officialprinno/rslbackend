"""Ensure demo storekeeper user for Rock Solutions FMS."""

from django.core.management.base import BaseCommand

from apps.users.demo_accounts import (
    DEMO_STOREKEEPER_EMAIL,
    ensure_demo_storekeeper_user,
    ensure_storekeeper_role_permissions,
)

class Command(BaseCommand):
    help = "Ensure storekeeper demo user exists with Storekeeper role and inventory permissions"

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEMO_STOREKEEPER_EMAIL)
        parser.add_argument("--password", default="Storekeeper@2024")
        parser.add_argument(
            "--keep-password",
            action="store_true",
            help="Do not reset password if user already exists",
        )

    def handle(self, *args, **options):
        user = ensure_demo_storekeeper_user(
            email=options["email"],
            reset_password=not options["keep_password"],
            password=options["password"],
        )
        if user.role_id:
            ensure_storekeeper_role_permissions(user.role)
        self.stdout.write(
            self.style.SUCCESS(
                f"Storekeeper ready: {user.email} (role: {user.role_name}, dept: Procurement)"
            )
        )
        if not options["keep_password"]:
            self.stdout.write(f"  Password: {options['password']}")
        self.stdout.write("  Portal: /inventory/dashboard")
