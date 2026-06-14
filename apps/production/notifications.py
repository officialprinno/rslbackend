"""Production execution workflow notifications."""

from apps.messaging.models import AppNotification


def _notify(user, title, body, *, notification_type=AppNotification.TYPE_SYSTEM, navigate_to=""):
    if not user or not getattr(user, "is_active", True):
        return
    AppNotification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        body=body,
        navigate_to=navigate_to or None,
    )


def notify_operator_assigned(work_order):
    _notify(
        work_order.operator,
        f"New assignment: {work_order.wo_number}",
        f"You have been assigned to produce {work_order.product.name}.",
        notification_type=AppNotification.TYPE_SYSTEM,
        navigate_to=f"/production/work-orders/{work_order.id}/view",
    )


def notify_completion_submitted(work_order):
    from apps.users.models import Permission, User

    approver_ids = Permission.objects.filter(
        module="production", action="approve", is_active=True
    ).values_list("role_id", flat=True)
    users = User.objects.filter(role_id__in=approver_ids, is_active=True).distinct()
    title = f"Completion submitted: {work_order.wo_number}"
    body = (
        f"{work_order.operator.get_full_name()} submitted production completion "
        f"for {work_order.product.name}."
    )
    nav = f"/production/work-orders/{work_order.id}/view"
    for user in users:
        _notify(user, title, body, notification_type=AppNotification.TYPE_APPROVAL, navigate_to=nav)


def notify_ready_for_store_receipt(work_order):
    from apps.users.models import Permission, User

    store_role_ids = Permission.objects.filter(
        module="inventory", action="create", is_active=True
    ).values_list("role_id", flat=True)
    users = User.objects.filter(role_id__in=store_role_ids, is_active=True).distinct()
    title = f"Ready for receipt: {work_order.wo_number}"
    body = f"Finished goods from {work_order.wo_number} await storekeeper confirmation."
    nav = "/inventory/production-receipts"
    for user in users:
        _notify(user, title, body, notification_type=AppNotification.TYPE_SYSTEM, navigate_to=nav)


def notify_machine_breakdown(machine, work_order=None, reported_by=None):
    from apps.users.models import Permission, User

    approver_ids = Permission.objects.filter(
        module="production", action="approve", is_active=True
    ).values_list("role_id", flat=True)
    users = User.objects.filter(role_id__in=approver_ids, is_active=True).distinct()
    reporter = reported_by.get_full_name() if reported_by else "Operator"
    wo_ref = f" ({work_order.wo_number})" if work_order else ""
    title = f"Machine breakdown: {machine.machine_code}"
    body = f"{reporter} reported breakdown on {machine.name}{wo_ref}."
    for user in users:
        _notify(
            user,
            title,
            body,
            notification_type=AppNotification.TYPE_ALERT,
            navigate_to=f"/production/machines/{machine.id}",
        )
