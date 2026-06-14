"""Inventory dashboard aggregation."""

from calendar import month_abbr
from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.inventory.models import (
    DepartmentRequest,
    Item,
    Stock,
    StockAdjustment,
    StockAlert,
    StockMovement,
    Warehouse,
)


def _pending_grn_count():
    try:
        from apps.procurement.models import GoodsReceivedNote

        return GoodsReceivedNote.objects.filter(
            status__in=[
                GoodsReceivedNote.STATUS_DRAFT,
                "PENDING",
            ]
        ).count()
    except Exception:
        return 0


def _pending_requisitions_count():
    try:
        from apps.procurement.models import PurchaseRequisition

        return PurchaseRequisition.objects.filter(status="PENDING").count()
    except Exception:
        return 0


def build_inventory_dashboard(warehouse_id=None):
    """Aggregate KPIs, charts, and recent activity for the inventory dashboard."""
    now = timezone.now()
    six_months_ago = now - timedelta(days=180)

    stock_qs = Stock.objects.select_related("item", "warehouse")
    if warehouse_id:
        stock_qs = stock_qs.filter(warehouse_id=warehouse_id)
    total_skus = (
        stock_qs.values("item_id").distinct().count()
        if warehouse_id
        else Item.objects.filter(is_active=True).count()
    )
    total_warehouses = (
        1
        if warehouse_id
        else Warehouse.objects.filter(is_active=True).count()
    )
    low_stock = stock_qs.filter(
        quantity_available__gt=0,
        quantity_available__lte=F("item__reorder_level"),
    ).count()
    out_of_stock = stock_qs.filter(quantity_available__lte=0).count()
    total_value = stock_qs.aggregate(
        total=Coalesce(Sum(F("quantity_on_hand") * F("item__unit_cost")), Decimal("0"))
    )["total"]

    pending_adjustments = StockAdjustment.objects.filter(status="PENDING").count()
    pending_dept_requests = DepartmentRequest.objects.filter(
        status__in=[
            DepartmentRequest.STATUS_PENDING,
            DepartmentRequest.STATUS_SUBMITTED,
        ]
    ).count()
    pending_grn = _pending_grn_count()
    pending_requisitions = _pending_requisitions_count()
    pending_requests = pending_dept_requests + pending_grn

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    movement_qs = StockMovement.objects.filter(created_at__gte=today_start)
    if warehouse_id:
        movement_qs = movement_qs.filter(warehouse_id=warehouse_id)
    stock_in_today = movement_qs.filter(movement_type="IN").aggregate(
        total=Coalesce(Sum("quantity"), Decimal("0"))
    )["total"]
    stock_out_today = movement_qs.filter(movement_type="OUT").aggregate(
        total=Coalesce(Sum("quantity"), Decimal("0"))
    )["total"]

    reserved_totals = stock_qs.aggregate(
        total=Coalesce(Sum("quantity_reserved"), Decimal("0"))
    )["total"]
    unread_alerts = StockAlert.objects.filter(is_read=False)
    if warehouse_id:
        unread_alerts = unread_alerts.filter(warehouse_id=warehouse_id)
    unread_alerts_count = unread_alerts.count()

    health_penalty = min(low_stock * 2 + out_of_stock * 5 + pending_adjustments, 80)
    inventory_health_score = max(20, 100 - health_penalty)

    warehouse_utilization = []
    wh_queryset = Warehouse.objects.filter(is_active=True)
    if warehouse_id:
        wh_queryset = wh_queryset.filter(pk=warehouse_id)
    for wh in wh_queryset:
        wh_stock = stock_qs.filter(warehouse=wh)
        sku_count = wh_stock.values("item_id").distinct().count()
        wh_value = wh_stock.aggregate(
            total=Coalesce(Sum(F("quantity_on_hand") * F("item__unit_cost")), Decimal("0"))
        )["total"]
        capacity = wh.capacity or 0
        on_hand = wh_stock.aggregate(total=Coalesce(Sum("quantity_on_hand"), Decimal("0")))["total"]
        utilization_pct = float(on_hand / capacity * 100) if capacity and capacity > 0 else None
        warehouse_utilization.append(
            {
                "warehouse_id": wh.id,
                "warehouse_name": wh.name,
                "sku_count": sku_count,
                "total_value": wh_value,
                "quantity_on_hand": on_hand,
                "capacity": capacity,
                "utilization_pct": utilization_pct,
            }
        )

    category_values = (
        stock_qs.values("item__category__name")
        .annotate(value=Coalesce(Sum(F("quantity_on_hand") * F("item__unit_cost")), Decimal("0")))
        .order_by("-value")[:12]
    )
    value_by_category = [
        {"category": row["item__category__name"] or "Uncategorized", "value": row["value"]}
        for row in category_values
    ]

    monthly_movements = (
        StockMovement.objects.filter(created_at__gte=six_months_ago)
        .annotate(month=TruncMonth("created_at"))
    )
    if warehouse_id:
        monthly_movements = monthly_movements.filter(warehouse_id=warehouse_id)
    monthly_movements = (
        monthly_movements.values("month")
        .annotate(
            stock_in=Coalesce(
                Sum("quantity", filter=Q(movement_type="IN")),
                Decimal("0"),
            ),
            stock_out=Coalesce(
                Sum("quantity", filter=Q(movement_type="OUT")),
                Decimal("0"),
            ),
        )
        .order_by("month")
    )
    monthly_chart = []
    for row in monthly_movements:
        month_label = month_abbr[row["month"].month] if row["month"] else ""
        monthly_chart.append(
            {
                "month": month_label,
                "stock_in": row["stock_in"],
                "stock_out": row["stock_out"],
            }
        )

    movement_totals = (
        StockMovement.objects.filter(created_at__gte=now - timedelta(days=90))
        .values("item_id", "item__code", "item__name")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")
    )
    fast_moving = [
        {
            "item_code": row["item__code"],
            "item_name": row["item__name"],
            "quantity": row["total_qty"],
        }
        for row in movement_totals[:8]
    ]
    slow_moving = [
        {
            "item_code": row["item__code"],
            "item_name": row["item__name"],
            "quantity": row["total_qty"],
        }
        for row in movement_totals.order_by("total_qty")[:8]
    ]

    top_selling = fast_moving[:5]
    top_consumed = [
        row
        for row in StockMovement.objects.filter(
            created_at__gte=now - timedelta(days=90),
            movement_type__in=["OUT", "PRODUCTION_CONSUMPTION"],
        )
        .values("item__code", "item__name")
        .annotate(quantity=Sum("quantity"))
        .order_by("-quantity")[:5]
    ]

    recent_movements = StockMovement.objects.select_related(
        "item", "warehouse", "created_by"
    ).order_by("-created_at")[:15]
    recent_activities = []
    for mv in recent_movements:
        activity_type = mv.movement_type
        if mv.movement_type == "TRANSFER":
            activity_type = "TRANSFER"
        elif mv.movement_type in ("PRODUCTION_CONSUMPTION", "PRODUCTION_OUTPUT"):
            activity_type = mv.movement_type
        elif mv.reference_type == "ADJUSTMENT":
            activity_type = "ADJUSTMENT"
        recent_activities.append(
            {
                "type": activity_type,
                "item_code": mv.item.code,
                "item_name": mv.item.name,
                "warehouse_name": mv.warehouse.name,
                "quantity": mv.quantity,
                "created_at": mv.created_at,
                "created_by_name": mv.created_by.get_full_name() if mv.created_by else None,
            }
        )

    return {
        "total_inventory_value": total_value,
        "total_skus": total_skus,
        "total_warehouses": total_warehouses,
        "low_stock_count": low_stock,
        "out_of_stock_count": out_of_stock,
        "pending_requisitions": pending_requisitions,
        "pending_adjustments": pending_adjustments,
        "pending_grn": pending_grn,
        "pending_department_requests": pending_dept_requests,
        "pending_requests": pending_requests,
        "stock_in_today": stock_in_today,
        "stock_out_today": stock_out_today,
        "total_reserved": reserved_totals,
        "unread_alerts": unread_alerts_count,
        "inventory_health_score": inventory_health_score,
        "warehouse_id": warehouse_id,
        "warehouse_utilization": warehouse_utilization,
        "store_department": "Procurement",
        "ownership_hierarchy": [
            "General Management",
            "Procurement Department",
            "Store Operations",
            "Other Departments",
        ],
        "value_by_category": value_by_category,
        "monthly_chart": monthly_chart,
        "fast_moving_items": fast_moving,
        "slow_moving_items": slow_moving,
        "top_selling_products": top_selling,
        "top_consumed_materials": top_consumed,
        "recent_activities": recent_activities,
    }


def build_valuation_report(method: str = "WEIGHTED_AVERAGE"):
    """Build inventory valuation report by category, warehouse, and item."""
    stock_qs = Stock.objects.select_related("item", "item__category", "warehouse")
    items_detail = []
    by_category = {}
    by_warehouse = {}
    total_value = Decimal("0")

    for stock in stock_qs:
        if method == "STANDARD_COST":
            unit_cost = stock.item.unit_cost
        else:
            unit_cost = stock.item.unit_cost
        line_value = stock.quantity_on_hand * unit_cost
        total_value += line_value
        cat_name = stock.item.category.name if stock.item.category else "Uncategorized"
        wh_name = stock.warehouse.name
        by_category[cat_name] = by_category.get(cat_name, Decimal("0")) + line_value
        by_warehouse[wh_name] = by_warehouse.get(wh_name, Decimal("0")) + line_value
        items_detail.append(
            {
                "item_code": stock.item.code,
                "item_name": stock.item.name,
                "category": cat_name,
                "warehouse": wh_name,
                "quantity": stock.quantity_on_hand,
                "unit_cost": unit_cost,
                "total_value": line_value,
            }
        )

    return {
        "method": method,
        "total_value": total_value,
        "by_category": [{"category": k, "value": v} for k, v in sorted(by_category.items())],
        "by_warehouse": [{"warehouse": k, "value": v} for k, v in sorted(by_warehouse.items())],
        "items": items_detail,
    }


def build_reorder_suggestions():
    """Suggest requisitions for items at or below reorder level."""
    suggestions = []
    stock_qs = (
        Stock.objects.select_related("item", "warehouse")
        .filter(item__is_active=True)
        .filter(quantity_available__lte=F("item__reorder_level"))
    )
    for stock in stock_qs:
        reorder = stock.item.reorder_level
        current = stock.quantity_available
        target = stock.item.maximum_stock or (reorder * 2) or reorder
        suggested = max(target - current, reorder)
        if suggested <= 0:
            suggested = reorder
        ratio = float(current / reorder) if reorder > 0 else 0
        if current <= 0:
            priority = "CRITICAL"
        elif ratio <= 0.25:
            priority = "HIGH"
        elif ratio <= 0.5:
            priority = "MEDIUM"
        else:
            priority = "LOW"
        suggestions.append(
            {
                "item": stock.item_id,
                "item_code": stock.item.code,
                "item_name": stock.item.name,
                "warehouse": stock.warehouse_id,
                "warehouse_name": stock.warehouse.name,
                "current_stock": current,
                "reorder_level": reorder,
                "suggested_quantity": suggested,
                "estimated_cost": suggested * stock.item.unit_cost,
                "priority": priority,
                "department": "PROCUREMENT",
            }
        )
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    suggestions.sort(key=lambda s: priority_order.get(s["priority"], 9))
    return suggestions


def create_requisition_from_suggestions(user, *, priorities=None, item_ids=None):
    """Create a procurement PR from low-stock reorder suggestions."""
    from apps.procurement.models import PurchaseRequisition, PurchaseRequisitionItem
    from apps.procurement.utils import generate_document_number
    from apps.users.models import Department

    suggestions = build_reorder_suggestions()
    if priorities:
        priorities_set = set(priorities)
        suggestions = [s for s in suggestions if s["priority"] in priorities_set]
    if item_ids:
        item_ids_set = set(item_ids)
        suggestions = [s for s in suggestions if s["item"] in item_ids_set]
    if not suggestions:
        raise ValueError("No reorder suggestions match the selected criteria.")

    dept = Department.objects.filter(name__icontains="procurement", is_active=True).first()
    if not dept:
        dept = Department.objects.filter(is_active=True).first()
    if not dept:
        raise ValueError("No department configured for procurement requests.")

    priority_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    top_priority = max(suggestions, key=lambda s: priority_rank.get(s["priority"], 0))["priority"]
    pr_priority_map = {
        "CRITICAL": PurchaseRequisition.PRIORITY_URGENT,
        "HIGH": PurchaseRequisition.PRIORITY_HIGH,
        "MEDIUM": PurchaseRequisition.PRIORITY_MEDIUM,
        "LOW": PurchaseRequisition.PRIORITY_LOW,
    }

    pr = PurchaseRequisition.objects.create(
        pr_number=generate_document_number("PR", PurchaseRequisition, "pr_number"),
        department=dept,
        priority=pr_priority_map.get(top_priority, PurchaseRequisition.PRIORITY_HIGH),
        status=PurchaseRequisition.STATUS_PENDING,
        notes="Suggested purchase requisition from inventory low-stock queue (Procurement governance).",
        requested_by=user,
    )
    for row in suggestions:
        PurchaseRequisitionItem.objects.create(
            requisition=pr,
            item_id=row["item"],
            quantity_requested=row["suggested_quantity"],
            unit_cost_estimate=row["estimated_cost"] / row["suggested_quantity"]
            if row["suggested_quantity"]
            else 0,
            notes=f"Reorder suggestion — {row['warehouse_name']} (priority {row['priority']})",
        )
    return pr
