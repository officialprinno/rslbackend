"""Ensure General Manager demo user with full module access."""

from django.core.management.base import BaseCommand

from apps.users.demo_accounts import (
    DEMO_GM_EMAIL,
    DEMO_GM_PASSWORD,
    ensure_demo_gm_user,
    ensure_gm_role_permissions,
)


class Command(BaseCommand):
    help = "Ensure General Manager user exists with full access to all modules"

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEMO_GM_EMAIL)
        parser.add_argument("--password", default=DEMO_GM_PASSWORD)
        parser.add_argument(
            "--keep-password",
            action="store_true",
            help="Do not reset password if user already exists",
        )

    def handle(self, *args, **options):
        user = ensure_demo_gm_user(
            email=options["email"],
            reset_password=not options["keep_password"],
            password=options["password"],
        )
        if user.role_id:
            ensure_gm_role_permissions(user.role)
        self.stdout.write(
            self.style.SUCCESS(
                f"General Manager ready: {user.email} (role: {user.role_name})"
            )
        )
        if not options["keep_password"]:
            self.stdout.write(f"  Password: {options['password']}")
        self.stdout.write("  Portal: /dashboard (GM multi-module dashboard)")
