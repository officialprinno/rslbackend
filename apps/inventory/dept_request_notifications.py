"""In-app notifications for department requisition workflow."""

from apps.messaging.models import AppNotification


def _notify(user, title, body, *, notification_type=AppNotification.TYPE_APPROVAL, navigate_to=""):
    if not user or not getattr(user, "is_active", True):
        return
    AppNotification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        body=body,
        navigate_to=navigate_to or None,
    )


def notify_request_submitted(dept_request):
    """Notify department approvers when a request is submitted."""
    from apps.users.models import Permission, User

    approver_ids = (
        Permission.objects.filter(module="inventory", action="approve", is_active=True)
        .values_list("role_id", flat=True)
        .distinct()
    )
    users = User.objects.filter(role_id__in=approver_ids, is_active=True).distinct()
    title = f"New requisition {dept_request.request_number}"
    body = (
        f"{dept_request.requested_by.get_full_name()} submitted a "
        f"{dept_request.get_priority_display()} request for {dept_request.get_department_display()}."
    )
    nav = "/inventory/department-approvals"
    for user in users:
        _notify(user, title, body, navigate_to=nav)
    if dept_request.priority == dept_request.PRIORITY_URGENT:
        for user in users:
            _notify(
                user,
                f"URGENT: {dept_request.request_number}",
                body,
                notification_type=AppNotification.TYPE_ALERT,
                navigate_to=nav,
            )


def notify_request_approved(dept_request):
    _notify(
        dept_request.requested_by,
        f"Request approved: {dept_request.request_number}",
        dept_request.approval_comment or "Your department requisition was approved.",
        navigate_to="/inventory/my-requests",
    )
    notify_storekeeper_pending_issue(dept_request)


def notify_request_rejected(dept_request):
    _notify(
        dept_request.requested_by,
        f"Request rejected: {dept_request.request_number}",
        dept_request.rejection_reason or "Your department requisition was rejected.",
        notification_type=AppNotification.TYPE_ALERT,
        navigate_to="/inventory/my-requests",
    )


def notify_request_issued(dept_request, *, partial=False):
    status_label = "partially issued" if partial else "issued"
    _notify(
        dept_request.requested_by,
        f"Request {status_label}: {dept_request.request_number}",
        f"Stock has been {status_label} for your requisition.",
        navigate_to="/inventory/my-requests",
    )


def notify_storekeeper_pending_issue(dept_request):
    from apps.users.models import Permission, User

    issuer_ids = (
        Permission.objects.filter(
            module="inventory",
            action__in=("create", "approve"),
            is_active=True,
        )
        .values_list("role_id", flat=True)
        .distinct()
    )
    users = User.objects.filter(role_id__in=issuer_ids, is_active=True).distinct()
    title = f"Pending issue: {dept_request.request_number}"
    body = f"Approved requisition awaiting store issue for {dept_request.get_department_display()}."
    nav = "/inventory/internal-issue"
    for user in users:
        _notify(user, title, body, navigate_to=nav)
