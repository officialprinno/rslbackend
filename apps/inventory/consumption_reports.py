"""Internal consumption and cost allocation reports."""

from calendar import month_abbr
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.inventory.models import DepartmentRequest, DepartmentRequestLine, Item, StockMovement


def build_internal_consumption_report(*, department=None, month=None):
    """Aggregate internal consumption KPIs and trends."""
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month:
        try:
            year, mon = [int(x) for x in month.split("-")]
            month_start = month_start.replace(year=year, month=mon)
        except (ValueError, TypeError):
            pass

    issued_statuses = [
        DepartmentRequest.STATUS_ISSUED,
        DepartmentRequest.STATUS_PARTIALLY_ISSUED,
    ]
    base_qs = DepartmentRequest.objects.filter(
        is_active=True,
        status__in=issued_statuses,
        issued_at__gte=month_start,
    )
    if department:
        base_qs = base_qs.filter(department=department)

    department_usage = []
    for row in (
        base_qs.values("department")
        .annotate(
            request_count=Count("id"),
            total_cost=Coalesce(
                Sum(F("lines__issued_qty") * F("lines__item__unit_cost")),
                Decimal("0"),
            ),
        )
        .order_by("-total_cost")
    ):
        department_usage.append(
            {
                "department": row["department"],
                "request_count": row["request_count"],
                "total_cost": row["total_cost"],
            }
        )

    item_usage = (
        DepartmentRequestLine.objects.filter(
            request__in=base_qs,
            issued_qty__gt=0,
        )
        .values("item__code", "item__name")
        .annotate(
            total_qty=Coalesce(Sum("issued_qty"), Decimal("0")),
            total_cost=Coalesce(
                Sum(F("issued_qty") * F("item__unit_cost")),
                Decimal("0"),
            ),
            request_count=Count("request_id", distinct=True),
        )
        .order_by("-total_qty")[:20]
    )
    most_consumed = [
        {
            "item_code": row["item__code"],
            "item_name": row["item__name"],
            "quantity": row["total_qty"],
            "total_cost": row["total_cost"],
            "request_count": row["request_count"],
        }
        for row in item_usage
    ]

    most_requested = (
        DepartmentRequestLine.objects.filter(request__is_active=True)
        .values("item__code", "item__name")
        .annotate(
            total_requested=Coalesce(Sum("quantity"), Decimal("0")),
            request_count=Count("request_id", distinct=True),
        )
        .order_by("-request_count")[:20]
    )
    most_requested_items = [
        {
            "item_code": row["item__code"],
            "item_name": row["item__name"],
            "total_requested": row["total_requested"],
            "request_count": row["request_count"],
        }
        for row in most_requested
    ]

    six_months_ago = now - timedelta(days=180)
    monthly_trend_qs = (
        DepartmentRequest.objects.filter(
            is_active=True,
            status__in=issued_statuses,
            issued_at__gte=six_months_ago,
        )
        .annotate(month=TruncMonth("issued_at"))
        .values("month")
        .annotate(
            issue_count=Count("id"),
            total_cost=Coalesce(
                Sum(F("lines__issued_qty") * F("lines__item__unit_cost")),
                Decimal("0"),
            ),
        )
        .order_by("month")
    )
    if department:
        monthly_trend_qs = monthly_trend_qs.filter(department=department)

    monthly_trend = []
    for row in monthly_trend_qs:
        month_label = month_abbr[row["month"].month] if row["month"] else ""
        monthly_trend.append(
            {
                "month": month_label,
                "issue_count": row["issue_count"],
                "total_cost": row["total_cost"],
            }
        )

    movement_cost = (
        StockMovement.objects.filter(
            movement_type=StockMovement.MOVEMENT_OUT,
            reference_type__in=[
                StockMovement.REFERENCE_GIN,
                StockMovement.REFERENCE_DEPT_REQUEST,
            ],
            created_at__gte=month_start,
        )
        .aggregate(total=Coalesce(Sum(F("quantity") * F("unit_cost")), Decimal("0")))["total"]
    )

    internal_items = Item.objects.filter(
        is_active=True,
        item_usage__in=[Item.USAGE_INTERNAL, Item.USAGE_BOTH],
    ).count()

    pending_issue = DepartmentRequest.objects.filter(
        is_active=True,
        status__in=[DepartmentRequest.STATUS_APPROVED, DepartmentRequest.STATUS_PROCESSING],
    ).count()

    return {
        "department": department,
        "month": month_start.strftime("%Y-%m"),
        "internal_items_count": internal_items,
        "pending_issue_count": pending_issue,
        "movement_cost_mtd": movement_cost,
        "department_usage": department_usage,
        "most_consumed_items": most_consumed,
        "most_requested_items": most_requested_items,
        "monthly_trend": monthly_trend,
    }


def build_cost_allocation_report(*, month=None):
    """Department cost allocation for internal consumption."""
    report = build_internal_consumption_report(month=month)
    total = sum((row["total_cost"] for row in report["department_usage"]), Decimal("0"))
    allocations = []
    for row in report["department_usage"]:
        pct = float(row["total_cost"] / total * 100) if total else 0
        allocations.append(
            {
                "department": row["department"],
                "consumption_cost": row["total_cost"],
                "request_count": row["request_count"],
                "share_percent": round(pct, 1),
            }
        )
    return {
        "month": report["month"],
        "total_internal_expense": total,
        "allocations": allocations,
        "monthly_trend": report["monthly_trend"],
    }
