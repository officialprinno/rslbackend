"""Unified dashboard for multi-department HOD users."""

from django.db.models import Count, Q
from django.utils import timezone

from apps.core.permissions import user_has_permission
from apps.inventory.dashboard import build_inventory_dashboard
from apps.logistics.models import DeliveryOrder, Vehicle
from apps.logistics.services import LogisticsService
from apps.procurement.models import GoodsReceivedNote, PurchaseOrder, Supplier
from apps.sales.models import SalesInvoice, SalesOrder, SalesQuotation


def build_multi_department_dashboard(user, department_filter: str | None = None):
    """Aggregate KPIs across modules the user can access."""
    today = timezone.now().date()
    show_all = not department_filter or department_filter in ("all", "")

    data = {
        "is_multi_department": getattr(user, "is_multi_department", False),
        "department_filter": department_filter or "all",
        "procurement": None,
        "sales": None,
        "logistics": None,
        "inventory": None,
    }

    if show_all or department_filter == "procurement":
        if user_has_permission(user, "procurement", "read"):
            data["procurement"] = {
                "pending_pos": PurchaseOrder.objects.filter(
                    is_active=True,
                    status__in=[
                        PurchaseOrder.STATUS_PENDING,
                        PurchaseOrder.STATUS_APPROVED,
                    ],
                ).count(),
                "suppliers": Supplier.objects.filter(is_active=True).count(),
                "grns_today": GoodsReceivedNote.objects.filter(
                    is_active=True,
                    received_date=today,
                ).count(),
            }

    if show_all or department_filter == "sales":
        if user_has_permission(user, "sales", "read"):
            data["sales"] = {
                "open_orders": SalesOrder.objects.filter(
                    is_active=True,
                    status__in=[
                        SalesOrder.STATUS_CONFIRMED,
                        SalesOrder.STATUS_PROCESSING,
                        SalesOrder.STATUS_PARTIAL,
                    ],
                ).count(),
                "quotations": SalesQuotation.objects.filter(
                    is_active=True,
                    status__in=[
                        SalesQuotation.STATUS_SENT,
                        SalesQuotation.STATUS_ACCEPTED,
                    ],
                ).count(),
                "invoices": SalesInvoice.objects.filter(
                    is_active=True,
                    status__in=[
                        SalesInvoice.STATUS_SENT,
                        SalesInvoice.STATUS_PARTIAL,
                    ],
                ).count(),
            }

    if show_all or department_filter == "logistics":
        if user_has_permission(user, "logistics", "read"):
            orders = DeliveryOrder.objects.filter(is_active=True)
            data["logistics"] = {
                "active_dos": orders.filter(
                    status__in=[
                        DeliveryOrder.STATUS_SCHEDULED,
                        DeliveryOrder.STATUS_IN_TRANSIT,
                    ]
                ).count(),
                "in_transit": orders.filter(status=DeliveryOrder.STATUS_IN_TRANSIT).count(),
                "vehicles": Vehicle.objects.filter(is_active=True).count(),
            }

    if show_all or department_filter == "inventory":
        if user_has_permission(user, "inventory", "read"):
            inv = build_inventory_dashboard()
            pending_approvals = inv.get("pending_adjustments", 0) + inv.get(
                "pending_department_requests", 0
            )
            data["inventory"] = {
                "low_stock": inv.get("low_stock_count", 0),
                "total_items": inv.get("total_skus", 0),
                "alerts": inv.get("unread_alerts", 0),
                "health_score": inv.get("inventory_health_score", 100),
                "pending_approvals": pending_approvals,
                "total_reserved": str(inv.get("total_reserved", 0)),
                "store_under": "Procurement",
                "low_stock_queue": inv.get("low_stock_count", 0),
            }

    return data
