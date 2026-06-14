"""Audit logging utilities."""

from apps.core.models import AuditLog


def get_client_ip(request):
    """Extract client IP from request, respecting X-Forwarded-For."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_audit(
    user,
    module,
    action,
    record_id="",
    old_values=None,
    new_values=None,
    ip_address=None,
    department_context=None,
):
    """Create an audit log entry."""
    payload = dict(new_values) if new_values else {}
    if department_context:
        payload["department_context"] = department_context
    return AuditLog.objects.create(
        user=user,
        module=module,
        action=action,
        record_id=str(record_id) if record_id else "",
        old_values=old_values,
        new_values=payload or None,
        ip_address=ip_address,
    )
