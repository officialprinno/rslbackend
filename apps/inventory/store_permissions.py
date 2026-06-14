"""Store / procurement hierarchy permission checks for inventory operations."""

from decimal import Decimal

from apps.core.permissions import user_has_permission

# Default threshold (TZS) — adjustments above require HOD Procurement approval
DEFAULT_ADJUSTMENT_VALUE_THRESHOLD = Decimal("500000")

HOD_PROCUREMENT_ROLE = "HOD Procurement"
ASSISTANT_PROCUREMENT_ROLE = "Assistant Procurement"
STORE_MANAGER_ROLE = "Store Manager"
STOREKEEPER_ROLE = "Storekeeper"
COORDINATOR_ROLE = "Coordinator"  # legacy alias


def _user_role_names(user) -> set[str]:
    from apps.users.rbac import get_user_roles

    return set(get_user_roles(user).values_list("name", flat=True))


def adjustment_monetary_value(adjustment) -> Decimal:
    unit_cost = getattr(adjustment.item, "unit_cost", None) or Decimal("0")
    return adjustment.quantity * unit_cost


def get_adjustment_approval_threshold() -> Decimal:
    from apps.users.models import ApprovalThreshold, Department

    dept = Department.objects.filter(name="Procurement", is_active=True).first()
    if not dept:
        return DEFAULT_ADJUSTMENT_VALUE_THRESHOLD
    row = (
        ApprovalThreshold.objects.filter(
            department=dept,
            module="inventory",
            is_active=True,
        )
        .order_by("min_amount")
        .first()
    )
    if row and row.max_amount is not None:
        return row.max_amount
    return DEFAULT_ADJUSTMENT_VALUE_THRESHOLD


def can_approve_adjustment(user, adjustment) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    if not user or not user.is_authenticated:
        return False, "Authentication required."

    if user.is_superuser:
        return True, ""

    if not user_has_permission(user, "inventory", "approve"):
        return False, "You do not have inventory approval permission."

    roles = _user_role_names(user)
    if HOD_PROCUREMENT_ROLE in roles or "Super Admin" in roles or "General Manager" in roles:
        return True, ""

    value = adjustment_monetary_value(adjustment)
    threshold = get_adjustment_approval_threshold()

    if roles & {ASSISTANT_PROCUREMENT_ROLE, STORE_MANAGER_ROLE, COORDINATOR_ROLE}:
        if value <= threshold:
            return True, ""
        return (
            False,
            f"Adjustment value ({value:,.2f}) exceeds assistant approval limit ({threshold:,.2f}). "
            "HOD Procurement approval required.",
        )

    return False, "Only HOD Procurement or Assistant Procurement can approve adjustments."


def can_delete_inventory_record(user) -> bool:
    if user.is_superuser:
        return True
    roles = _user_role_names(user)
    return HOD_PROCUREMENT_ROLE in roles or "Super Admin" in roles


def can_approve_valuation(user) -> bool:
    roles = _user_role_names(user)
    if user.is_superuser or HOD_PROCUREMENT_ROLE in roles or "Super Admin" in roles:
        return True
    return False


def can_operate_store(user) -> bool:
    """Store operations under Procurement — receive, issue, reserve, transfer, count."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    roles = _user_role_names(user)
    if roles & {STOREKEEPER_ROLE, STORE_MANAGER_ROLE, ASSISTANT_PROCUREMENT_ROLE, HOD_PROCUREMENT_ROLE}:
        return user_has_permission(user, "inventory", "create") or user_has_permission(
            user, "inventory", "update"
        )
    return user_has_permission(user, "inventory", "create")


def can_govern_inventory(user) -> bool:
    """Procurement governance — approvals, reorder, warehouse oversight."""
    if user.is_superuser:
        return True
    roles = _user_role_names(user)
    return bool(
        roles & {HOD_PROCUREMENT_ROLE, ASSISTANT_PROCUREMENT_ROLE, STORE_MANAGER_ROLE}
        or user_has_permission(user, "inventory", "approve")
    )


def can_view_valuation_report(user) -> bool:
    if user.is_superuser:
        return True
    roles = _user_role_names(user)
    if STOREKEEPER_ROLE in roles and HOD_PROCUREMENT_ROLE not in roles and "General Manager" not in roles:
        return False
    if user_has_permission(user, "finance", "read"):
        return True
    return can_govern_inventory(user) or user_has_permission(user, "inventory", "approve")
