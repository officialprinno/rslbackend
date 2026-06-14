"""Notify inventory stakeholders when critical stock alerts are raised."""

from apps.messaging.models import AppNotification


def notify_stock_alert(alert):
    """Push notification for out-of-stock and critical low-stock alerts."""
    from apps.users.models import Permission, User

    if alert.alert_type not in ("OUT_OF_STOCK", "LOW_STOCK"):
        return

    role_ids = (
        Permission.objects.filter(
            module="inventory",
            action__in=("approve", "create"),
            is_active=True,
        )
        .values_list("role_id", flat=True)
        .distinct()
    )
    users = User.objects.filter(role_id__in=role_ids, is_active=True).distinct()
    title = (
        "Out of stock alert"
        if alert.alert_type == "OUT_OF_STOCK"
        else "Low stock alert"
    )
    for user in users:
        AppNotification.objects.create(
            user=user,
            notification_type=AppNotification.TYPE_ALERT,
            title=title,
            body=alert.message,
            navigate_to="/inventory/alerts",
        )

    if alert.alert_type == "OUT_OF_STOCK":
        finance_role_ids = (
            Permission.objects.filter(module="finance", action="read", is_active=True)
            .values_list("role_id", flat=True)
            .distinct()
        )
        finance_users = User.objects.filter(role_id__in=finance_role_ids, is_active=True).distinct()
        for user in finance_users:
            AppNotification.objects.create(
                user=user,
                notification_type=AppNotification.TYPE_ALERT,
                title="Inventory stock-out",
                body=alert.message,
                navigate_to="/inventory/reports",
            )
