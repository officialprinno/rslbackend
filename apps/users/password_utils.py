"""Helpers for setting passwords and recording admin-visible credentials."""

from apps.users.models import User


def apply_user_password(user: User, password: str, *, record_for_admin: bool = True) -> None:
    """Hash password and optionally store a copy for super-admin credential export."""
    user.set_password(password)
    if record_for_admin:
        user.admin_password = password
    if user.pk:
        update_fields = ["password"]
        if record_for_admin:
            update_fields.append("admin_password")
        user.save(update_fields=update_fields)
        return
    user.save()


def clear_admin_password_record(user: User) -> None:
    """Remove stored admin password after the user changes it themselves."""
    user.admin_password = ""
    if user.pk:
        user.save(update_fields=["admin_password"])
