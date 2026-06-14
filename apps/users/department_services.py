"""User department assignment helpers."""

from django.db import transaction

from apps.users.models import Department, Role, User, UserDepartment


@transaction.atomic
def sync_user_department_assignments(user, assignments: list[dict] | None) -> None:
    """
    Replace user department rows.

    assignments: [{"department": id, "role": id, "is_primary": bool}, ...]
    """
    if assignments is None:
        return

    if not assignments:
        UserDepartment.objects.filter(user=user).delete()
        user.is_multi_department = False
        user.save(update_fields=["is_multi_department", "updated_at"])
        return

    primary_set = False
    normalized = []
    for row in assignments:
        dept_id = row.get("department")
        role_id = row.get("role")
        if not dept_id or not role_id:
            continue
        is_primary = bool(row.get("is_primary"))
        if is_primary:
            primary_set = True
        normalized.append(
            {
                "department_id": dept_id,
                "role_id": role_id,
                "is_primary": is_primary,
            }
        )

    if not normalized:
        return

    if not primary_set:
        normalized[0]["is_primary"] = True

    keep_ids: list[int] = []
    for row in normalized:
        obj, _ = UserDepartment.objects.update_or_create(
            user=user,
            department_id=row["department_id"],
            defaults={
                "role_id": row["role_id"],
                "is_primary": row["is_primary"],
                "is_active": True,
            },
        )
        keep_ids.append(obj.id)

    UserDepartment.objects.filter(user=user).exclude(id__in=keep_ids).delete()

    primary = next((r for r in normalized if r["is_primary"]), normalized[0])
    user.department_id = primary["department_id"]
    user.role_id = primary["role_id"]
    user.is_multi_department = len(normalized) > 1
    user.save(update_fields=["department", "role", "is_multi_department", "updated_at"])


def ensure_primary_assignment_from_user(user) -> None:
    """Create a primary user_departments row from legacy user.department/role."""
    if not user.department_id or not user.role_id:
        return
    UserDepartment.objects.update_or_create(
        user=user,
        department_id=user.department_id,
        defaults={
            "role_id": user.role_id,
            "is_primary": True,
            "is_active": True,
        },
    )
