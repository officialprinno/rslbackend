"""Procurement dashboard aggregation."""

from calendar import month_abbr
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.procurement.models import (
    GoodsReceivedNote,
    PurchaseOrder,
    PurchaseRequisition,
    RequestForQuotation,
    Supplier,
    SupplierInvoice,
    SupplierQuotation,
)


def build_procurement_dashboard():
    """Aggregate KPIs, charts, and recent activity for the procurement dashboard."""
    now = timezone.now()
    today = now.date()
    month_start = today.replace(day=1)
    six_months_ago = now - timedelta(days=180)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    active = Q(is_active=True)

    total_suppliers = Supplier.objects.filter(is_active=True).count()
    pending_requisitions = PurchaseRequisition.objects.filter(
        active, status=PurchaseRequisition.STATUS_PENDING
    ).count()
    approved_requisitions = PurchaseRequisition.objects.filter(
        active, status=PurchaseRequisition.STATUS_APPROVED
    ).count()
    open_rfqs = RequestForQuotation.objects.filter(
        active, status=RequestForQuotation.STATUS_OPEN
    ).count()
    pending_quotations = SupplierQuotation.objects.filter(
        active, status=SupplierQuotation.STATUS_PENDING
    ).count()
    pending_po_approvals = PurchaseOrder.objects.filter(
        active, status=PurchaseOrder.STATUS_PENDING
    ).count()
    open_purchase_orders = PurchaseOrder.objects.filter(
        active,
        status__in=[
            PurchaseOrder.STATUS_SENT,
            PurchaseOrder.STATUS_PARTIAL,
            PurchaseOrder.STATUS_APPROVED,
        ],
    ).count()
    pending_grn = GoodsReceivedNote.objects.filter(
        active, status=GoodsReceivedNote.STATUS_DRAFT
    ).count()
    grn_today = GoodsReceivedNote.objects.filter(active, created_at__gte=today_start).count()
    pending_invoices = SupplierInvoice.objects.filter(
        active,
        status__in=[
            SupplierInvoice.STATUS_PENDING,
            SupplierInvoice.STATUS_PARTIAL,
        ],
    ).count()
    overdue_invoices = SupplierInvoice.objects.filter(
        active,
        status=SupplierInvoice.STATUS_OVERDUE,
    ).count()

    monthly_spend = PurchaseOrder.objects.filter(
        active,
        order_date__gte=month_start,
        status__in=[
            PurchaseOrder.STATUS_SENT,
            PurchaseOrder.STATUS_PARTIAL,
            PurchaseOrder.STATUS_RECEIVED,
        ],
    ).aggregate(total=Coalesce(Sum("total_amount"), Decimal("0")))["total"]

    monthly_po_count = PurchaseOrder.objects.filter(
        active,
        order_date__gte=month_start,
        status__in=[
            PurchaseOrder.STATUS_SENT,
            PurchaseOrder.STATUS_PARTIAL,
            PurchaseOrder.STATUS_RECEIVED,
        ],
    ).count()

    po_by_status = (
        PurchaseOrder.objects.filter(active)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    status_breakdown = [
        {"status": row["status"], "count": row["count"]} for row in po_by_status
    ]

    monthly_chart_qs = (
        PurchaseOrder.objects.filter(
            active,
            created_at__gte=six_months_ago,
            status__in=[
                PurchaseOrder.STATUS_SENT,
                PurchaseOrder.STATUS_PARTIAL,
                PurchaseOrder.STATUS_RECEIVED,
            ],
        )
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            total=Coalesce(Sum("total_amount"), Decimal("0")),
            count=Count("id"),
        )
        .order_by("month")
    )
    monthly_chart = []
    for row in monthly_chart_qs:
        month_label = month_abbr[row["month"].month] if row["month"] else ""
        monthly_chart.append(
            {
                "month": month_label,
                "spend": row["total"],
                "po_count": row["count"],
            }
        )

    top_suppliers = (
        PurchaseOrder.objects.filter(active, order_date__gte=month_start)
        .exclude(status__in=[PurchaseOrder.STATUS_DRAFT, PurchaseOrder.STATUS_CANCELLED])
        .values("supplier__name")
        .annotate(
            total=Coalesce(Sum("total_amount"), Decimal("0")),
            order_count=Count("id"),
        )
        .order_by("-total")[:5]
    )
    top_suppliers_list = [
        {
            "name": row["supplier__name"],
            "total": row["total"],
            "order_count": row["order_count"],
        }
        for row in top_suppliers
    ]

    recent_activities = []
    for pr in PurchaseRequisition.objects.filter(active).select_related(
        "requested_by", "department"
    ).order_by("-created_at")[:5]:
        recent_activities.append(
            {
                "type": "REQUISITION",
                "reference": pr.pr_number,
                "status": pr.status,
                "detail": pr.department.name if pr.department_id else "",
                "amount": pr.total_estimated,
                "created_at": pr.created_at,
                "created_by_name": pr.requested_by.get_full_name() if pr.requested_by else None,
            }
        )
    for po in PurchaseOrder.objects.filter(active).select_related(
        "supplier", "created_by"
    ).order_by("-created_at")[:5]:
        recent_activities.append(
            {
                "type": "PURCHASE_ORDER",
                "reference": po.po_number,
                "status": po.status,
                "detail": po.supplier.name if po.supplier_id else "",
                "amount": po.total_amount,
                "created_at": po.created_at,
                "created_by_name": po.created_by.get_full_name() if po.created_by else None,
            }
        )
    for grn in GoodsReceivedNote.objects.filter(active).select_related(
        "purchase_order", "received_by"
    ).order_by("-created_at")[:5]:
        recent_activities.append(
            {
                "type": "GRN",
                "reference": grn.grn_number,
                "status": grn.status,
                "detail": grn.purchase_order.po_number if grn.purchase_order_id else "",
                "amount": None,
                "created_at": grn.created_at,
                "created_by_name": grn.received_by.get_full_name() if grn.received_by else None,
            }
        )
    recent_activities.sort(key=lambda a: a["created_at"], reverse=True)
    recent_activities = recent_activities[:12]

    return {
        "total_suppliers": total_suppliers,
        "pending_requisitions": pending_requisitions,
        "approved_requisitions": approved_requisitions,
        "open_rfqs": open_rfqs,
        "pending_quotations": pending_quotations,
        "pending_po_approvals": pending_po_approvals,
        "open_purchase_orders": open_purchase_orders,
        "pending_grn": pending_grn,
        "grn_today": grn_today,
        "pending_invoices": pending_invoices,
        "overdue_invoices": overdue_invoices,
        "monthly_spend": monthly_spend,
        "monthly_po_count": monthly_po_count,
        "po_status_breakdown": status_breakdown,
        "monthly_chart": monthly_chart,
        "top_suppliers": top_suppliers_list,
        "recent_activities": recent_activities,
    }
