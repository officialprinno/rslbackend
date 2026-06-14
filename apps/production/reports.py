"""Production analytics reports — operator performance, downtime, utilization."""

from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.production.models import (
    Machine,
    MachineUsage,
    OutputRecord,
    WorkOrder,
    WorkOrderPauseRecord,
    WorkOrderProgressEntry,
)
from apps.production.services import ProductionService


def _month_bounds(month: str | None) -> tuple[date | None, date | None]:
    if not month:
        return None, None
    try:
        year, mon = month.split("-")
        start = date(int(year), int(mon), 1)
    except (ValueError, TypeError):
        return None, None
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def build_operator_performance_report(*, month: str | None = None) -> dict:
    start, end = _month_bounds(month)
    wo_qs = WorkOrder.objects.filter(is_active=True).select_related("operator")
    if start and end:
        wo_qs = wo_qs.filter(updated_at__date__gte=start, updated_at__date__lt=end)

    operators: dict[int, dict] = {}
    for wo in wo_qs:
        op = wo.operator
        if not op:
            continue
        if op.id not in operators:
            operators[op.id] = {
                "operator_id": op.id,
                "operator_name": op.get_full_name(),
                "work_orders_total": 0,
                "work_orders_completed": 0,
                "quantity_produced": Decimal("0"),
                "quantity_rejected": Decimal("0"),
                "quantity_planned": Decimal("0"),
            }
        row = operators[op.id]
        row["work_orders_total"] += 1
        row["quantity_produced"] += wo.quantity_produced
        row["quantity_rejected"] += wo.quantity_rejected
        row["quantity_planned"] += wo.quantity_planned
        if wo.status in (
            WorkOrder.STATUS_CLOSED,
            WorkOrder.STATUS_COMPLETED,
            WorkOrder.STATUS_INV_RECEIVED,
        ):
            row["work_orders_completed"] += 1

    rows = []
    for row in operators.values():
        planned = row["quantity_planned"] or Decimal("1")
        produced = row["quantity_produced"]
        rejected = row["quantity_rejected"]
        total_out = produced + rejected
        rows.append(
            {
                **row,
                "quantity_produced": str(produced.quantize(Decimal("0.0001"))),
                "quantity_rejected": str(rejected.quantize(Decimal("0.0001"))),
                "quantity_planned": str(row["quantity_planned"].quantize(Decimal("0.0001"))),
                "efficiency_pct": float((produced / planned * 100).quantize(Decimal("0.1"))),
                "rejection_rate_pct": float(
                    (rejected / total_out * 100).quantize(Decimal("0.1")) if total_out else 0
                ),
            }
        )
    rows.sort(key=lambda r: -float(r["quantity_produced"]))
    return {"month": month or timezone.now().strftime("%Y-%m"), "operators": rows}


def build_downtime_report(*, month: str | None = None) -> dict:
    start, end = _month_bounds(month)
    qs = WorkOrderPauseRecord.objects.select_related(
        "work_order__machine", "work_order__operator", "recorded_by"
    )
    if start and end:
        qs = qs.filter(paused_at__date__gte=start, paused_at__date__lt=end)

    by_machine: dict[int, dict] = {}
    by_reason: dict[str, Decimal] = {}
    events = []
    total_minutes = Decimal("0")

    for pause in qs.order_by("-paused_at")[:500]:
        mins = pause.downtime_minutes or Decimal("0")
        if pause.resumed_at and not pause.downtime_minutes:
            delta = pause.resumed_at - pause.paused_at
            mins = Decimal(str(round(delta.total_seconds() / 60, 1)))
        total_minutes += mins
        reason_key = (pause.reason or "Unspecified")[:120]
        by_reason[reason_key] = by_reason.get(reason_key, Decimal("0")) + mins

        machine = pause.work_order.machine
        if machine:
            if machine.id not in by_machine:
                by_machine[machine.id] = {
                    "machine_id": machine.id,
                    "machine_code": machine.machine_code,
                    "machine_name": machine.name,
                    "downtime_minutes": Decimal("0"),
                    "pause_count": 0,
                }
            by_machine[machine.id]["downtime_minutes"] += mins
            by_machine[machine.id]["pause_count"] += 1

        events.append(
            {
                "work_order": pause.work_order.wo_number,
                "machine_code": machine.machine_code if machine else "",
                "operator_name": pause.work_order.operator.get_full_name(),
                "reason": pause.reason,
                "paused_at": pause.paused_at.isoformat(),
                "resumed_at": pause.resumed_at.isoformat() if pause.resumed_at else None,
                "downtime_minutes": str(mins),
            }
        )

    machine_rows = sorted(
        [
            {
                **v,
                "downtime_minutes": str(v["downtime_minutes"].quantize(Decimal("0.1"))),
            }
            for v in by_machine.values()
        ],
        key=lambda r: -float(r["downtime_minutes"]),
    )
    reason_rows = [
        {"reason": k, "downtime_minutes": str(v.quantize(Decimal("0.1")))}
        for k, v in sorted(by_reason.items(), key=lambda x: -x[1])
    ]

    return {
        "month": month or timezone.now().strftime("%Y-%m"),
        "total_downtime_minutes": str(total_minutes.quantize(Decimal("0.1"))),
        "pause_event_count": qs.count(),
        "by_machine": machine_rows,
        "by_reason": reason_rows,
        "events": events[:100],
    }


def build_machine_utilization_report(*, month: str | None = None) -> dict:
    start, end = _month_bounds(month)
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start:
        from datetime import datetime

        month_start = timezone.make_aware(datetime.combine(start, datetime.min.time()))

    machines = Machine.objects.filter(is_active=True).order_by("machine_code")
    rows = []
    for machine in machines:
        usage_qs = MachineUsage.objects.filter(machine=machine, start_time__gte=month_start)
        if start and end:
            usage_qs = usage_qs.filter(start_time__date__gte=start, start_time__date__lt=end)
        agg = usage_qs.aggregate(
            hours=Coalesce(Sum("hours_used"), Decimal("0")),
            sessions=Count("id"),
        )
        hours = agg["hours"] or Decimal("0")
        utilization = float(min(hours / Decimal("160") * 100, Decimal("100")).quantize(Decimal("0.1")))
        rows.append(
            {
                "machine_id": machine.id,
                "machine_code": machine.machine_code,
                "machine_name": machine.name,
                "status": machine.status,
                "runtime_condition": machine.runtime_condition,
                "hours_used": str(hours.quantize(Decimal("0.01"))),
                "usage_sessions": agg["sessions"] or 0,
                "utilization_pct": utilization,
                "current_wo": machine.work_orders.filter(
                    status=WorkOrder.STATUS_IN_PROGRESS, is_active=True
                )
                .values_list("wo_number", flat=True)
                .first(),
            }
        )
    rows.sort(key=lambda r: -r["utilization_pct"])
    return {"month": month or timezone.now().strftime("%Y-%m"), "machines": rows}


def build_completed_work_orders_report(*, month: str | None = None) -> dict:
    start, end = _month_bounds(month)
    qs = WorkOrder.objects.filter(
        is_active=True,
        status__in=[
            WorkOrder.STATUS_CLOSED,
            WorkOrder.STATUS_COMPLETED,
            WorkOrder.STATUS_INV_RECEIVED,
        ],
    ).select_related("product", "operator")
    if start and end:
        qs = qs.filter(actual_end__date__gte=start, actual_end__date__lt=end)

    rows = []
    for wo in qs.order_by("-actual_end")[:200]:
        planned = wo.quantity_planned or Decimal("1")
        rows.append(
            {
                "wo_number": wo.wo_number,
                "product_name": wo.product.name,
                "operator_name": wo.operator.get_full_name(),
                "quantity_planned": str(wo.quantity_planned),
                "quantity_produced": str(wo.quantity_produced),
                "quantity_rejected": str(wo.quantity_rejected),
                "efficiency_pct": float(
                    (wo.quantity_produced / planned * 100).quantize(Decimal("0.1"))
                ),
                "actual_end": wo.actual_end.isoformat() if wo.actual_end else None,
                "status": wo.status,
            }
        )
    return {"month": month or timezone.now().strftime("%Y-%m"), "work_orders": rows}


def build_production_reports_bundle(*, month: str | None = None) -> dict:
    return {
        "month": month or timezone.now().strftime("%Y-%m"),
        "operator_performance": build_operator_performance_report(month=month),
        "downtime": build_downtime_report(month=month),
        "machine_utilization": build_machine_utilization_report(month=month),
        "completed_work_orders": build_completed_work_orders_report(month=month),
        "raw_material_status": ProductionService.raw_material_status(),
    }
