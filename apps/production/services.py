"""Production business logic."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import Item, Stock, StockMovement, Warehouse
from apps.inventory.services import StockService
from apps.production.models import (
    BillOfMaterials,
    BOMItem,
    Machine,
    MachineBreakdownRecord,
    MachineServiceRecord,
    MachineUsage,
    OutputRecord,
    Product,
    WorkOrder,
    WorkOrderMaterialIssue,
)
from apps.production.utils import generate_document_number


class ProductionService:
    """BOM calculations, stock integration, and workflow."""

    @staticmethod
    def default_warehouse() -> Warehouse:
        wh = Warehouse.objects.filter(is_active=True).first()
        if not wh:
            raise ValueError("No active warehouse configured.")
        return wh

    @staticmethod
    def get_stock_level(item_id: int) -> Decimal:
        total = (
            Stock.objects.filter(item_id=item_id)
            .aggregate(total=Sum("quantity_available"))
            .get("total")
        )
        return total or Decimal("0")

    @staticmethod
    def recalculate_bom_cost(bom: BillOfMaterials) -> None:
        total = Decimal("0")
        for line in bom.items.select_related("item"):
            cost = line.effective_quantity * line.item.unit_cost
            total += cost
        bom.material_cost_per_unit = total
        bom.save(update_fields=["material_cost_per_unit", "updated_at"])

    @staticmethod
    def material_requirements(bom: BillOfMaterials, quantity: Decimal) -> list:
        reqs = []
        for line in bom.items.select_related("item"):
            required = line.effective_quantity * quantity
            available = ProductionService.get_stock_level(line.item_id)
            shortage = max(required - available, Decimal("0"))
            reqs.append(
                {
                    "item_id": line.item_id,
                    "item_code": line.item.code,
                    "item_name": line.item.name,
                    "required_quantity": str(required.quantize(Decimal("0.0001"))),
                    "available_stock": str(available.quantize(Decimal("0.0001"))),
                    "is_sufficient": available >= required,
                    "shortage": str(shortage.quantize(Decimal("0.0001"))),
                }
            )
        return reqs

    @staticmethod
    def check_material_availability(bom: BillOfMaterials, quantity: Decimal) -> list:
        return ProductionService.material_requirements(bom, quantity)

    @staticmethod
    def all_materials_sufficient(bom: BillOfMaterials, quantity: Decimal) -> bool:
        reqs = ProductionService.material_requirements(bom, quantity)
        return all(r["is_sufficient"] for r in reqs)

    @staticmethod
    def activate_bom(bom: BillOfMaterials) -> None:
        BillOfMaterials.objects.filter(
            product=bom.product,
            status=BillOfMaterials.STATUS_ACTIVE,
            is_active=True,
        ).exclude(pk=bom.pk).update(status=BillOfMaterials.STATUS_INACTIVE)
        bom.status = BillOfMaterials.STATUS_ACTIVE
        bom.save(update_fields=["status", "updated_at"])
        ProductionService.recalculate_bom_cost(bom)

    @staticmethod
    def approve_work_order(wo: WorkOrder, user) -> None:
        wo.status = WorkOrder.STATUS_APPROVED
        wo.approved_by = user
        wo.approved_at = timezone.now()
        wo.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

    @staticmethod
    def start_production(wo: WorkOrder, user) -> None:
        if wo.execution_workflow:
            raise ValueError(
                "This work order uses execution workflow. Use operator start instead."
            )
        if not ProductionService.all_materials_sufficient(wo.bom, wo.quantity_planned):
            raise ValueError("Insufficient raw materials to start production.")
        warehouse = ProductionService.default_warehouse()
        for line in wo.bom.items.select_related("item"):
            qty = line.effective_quantity * wo.quantity_planned
            StockService.apply_quantity_change(
                item=line.item,
                warehouse=warehouse,
                delta=-qty,
                movement_type=StockMovement.MOVEMENT_PRODUCTION_CONSUMPTION,
                reference_type=StockMovement.REFERENCE_WORK_ORDER,
                reference_id=wo.wo_number,
                notes=f"Materials issued for {wo.wo_number}",
                created_by=user,
            )
            WorkOrderMaterialIssue.objects.create(
                work_order=wo,
                item=line.item,
                quantity_issued=qty,
            )
        wo.status = WorkOrder.STATUS_IN_PROGRESS
        wo.actual_start = timezone.now()
        wo.materials_issued = True
        wo.save(
            update_fields=[
                "status",
                "actual_start",
                "materials_issued",
                "updated_at",
            ]
        )

    @staticmethod
    def record_output(record: OutputRecord) -> None:
        wo = record.work_order
        wo.quantity_produced += record.quantity_produced
        wo.quantity_rejected += record.quantity_rejected
        wo.save(update_fields=["quantity_produced", "quantity_rejected", "updated_at"])

        if record.quantity_produced > 0:
            warehouse = ProductionService.default_warehouse()
            product_item = wo.product.item
            StockService.apply_quantity_change(
                item=product_item,
                warehouse=warehouse,
                delta=record.quantity_produced,
                movement_type=StockMovement.MOVEMENT_PRODUCTION_OUTPUT,
                reference_type=StockMovement.REFERENCE_WORK_ORDER,
                reference_id=wo.wo_number,
                unit_cost=wo.bom.material_cost_per_unit,
                notes=f"Finished goods from batch {record.batch_number}",
                created_by=record.operator,
            )

    @staticmethod
    def complete_work_order(wo: WorkOrder) -> None:
        if wo.execution_workflow:
            raise ValueError(
                "This work order uses execution workflow. Use submit completion flow instead."
            )
        if not wo.output_records.filter(is_active=True).exists():
            raise ValueError("At least one output record is required.")
        accounted = wo.quantity_produced + wo.quantity_rejected
        if accounted < wo.quantity_planned:
            raise ValueError(
                f"Produced + rejected ({accounted}) must equal planned ({wo.quantity_planned})."
            )
        wo.status = WorkOrder.STATUS_COMPLETED
        wo.actual_end = timezone.now()
        wo.save(update_fields=["status", "actual_end", "updated_at"])

    @staticmethod
    def machine_hours_this_month(machine: Machine) -> Decimal:
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total = (
            MachineUsage.objects.filter(machine=machine, start_time__gte=month_start)
            .aggregate(total=Sum("hours_used"))
            .get("total")
        )
        return total or Decimal("0")

    @staticmethod
    def machine_history_payload(machine: Machine, request, *, usage_serializer, service_serializer) -> dict:
        """Usage, service, and breakdown history for a machine detail page."""
        usage = (
            MachineUsage.objects.filter(machine=machine)
            .select_related("machine", "work_order", "operator")
            .order_by("-start_time")[:50]
        )
        services = (
            MachineServiceRecord.objects.filter(machine=machine)
            .order_by("-service_date")[:50]
        )
        breakdown_rows = ProductionService._machine_breakdown_rows(machine, request)
        return {
            "usage": usage_serializer(usage, many=True).data,
            "services": service_serializer(services, many=True).data,
            "breakdowns": breakdown_rows,
            "hours_this_month": str(ProductionService.machine_hours_this_month(machine)),
        }

    @staticmethod
    def _machine_breakdown_rows(machine: Machine, request) -> list[dict]:
        import logging

        from django.db.utils import OperationalError, ProgrammingError

        logger = logging.getLogger(__name__)
        try:
            breakdowns = (
                MachineBreakdownRecord.objects.filter(machine=machine)
                .select_related("reported_by", "work_order")
                .order_by("-created_at")[:20]
            )
        except (ProgrammingError, OperationalError):
            logger.exception(
                "MachineBreakdownRecord table missing — run: python manage.py migrate production"
            )
            return []

        rows = []
        for record in breakdowns:
            photo_url = None
            if record.photo and getattr(record.photo, "name", None):
                try:
                    url = record.photo.url
                    photo_url = (
                        url
                        if url.startswith("http")
                        else request.build_absolute_uri(url)
                    )
                except (ValueError, AttributeError):
                    photo_url = None
            rows.append(
                {
                    "id": record.id,
                    "notes": record.notes,
                    "photo_url": photo_url,
                    "reported_by_name": record.reported_by.get_full_name(),
                    "work_order": record.work_order.wo_number if record.work_order_id else None,
                    "created_at": record.created_at.isoformat(),
                }
            )
        return rows

    @staticmethod
    def raw_material_status() -> list:
        active_wos = WorkOrder.objects.filter(
            is_active=True,
            status__in=[
                WorkOrder.STATUS_APPROVED,
                WorkOrder.STATUS_ASSIGNED,
                WorkOrder.STATUS_IN_PROGRESS,
                WorkOrder.STATUS_PAUSED,
            ],
        ).select_related("bom", "product")
        material_totals: dict[int, Decimal] = {}
        for wo in active_wos:
            remaining = wo.quantity_planned - wo.quantity_produced - wo.quantity_rejected
            if remaining <= 0:
                continue
            for line in wo.bom.items.all():
                req = line.effective_quantity * remaining
                material_totals[line.item_id] = material_totals.get(line.item_id, Decimal("0")) + req

        results = []
        for item_id, required in material_totals.items():
            item = Item.objects.get(pk=item_id)
            stock = ProductionService.get_stock_level(item_id)
            if stock >= required:
                status = "SUFFICIENT"
            elif stock >= required * Decimal("0.5"):
                status = "LOW"
            else:
                status = "INSUFFICIENT"
            results.append(
                {
                    "item_id": item_id,
                    "item_name": item.name,
                    "current_stock": str(stock),
                    "required_for_active_wos": str(required.quantize(Decimal("0.0001"))),
                    "is_sufficient": stock >= required,
                    "status": status,
                }
            )
        return results

    @staticmethod
    def dashboard_data() -> dict:
        today = timezone.now().date()
        month_start = today.replace(day=1)
        active_wos = WorkOrder.objects.filter(
            is_active=True,
            status__in=[WorkOrder.STATUS_APPROVED, WorkOrder.STATUS_IN_PROGRESS],
        )
        outputs_today = OutputRecord.objects.filter(is_active=True, date=today)
        outputs_month = OutputRecord.objects.filter(is_active=True, date__gte=month_start)
        units_today = outputs_today.aggregate(t=Sum("quantity_produced"))["t"] or Decimal("0")
        units_month = outputs_month.aggregate(t=Sum("quantity_produced"))["t"] or Decimal("0")

        in_progress = WorkOrder.objects.filter(
            is_active=True,
            status__in=[
                WorkOrder.STATUS_IN_PROGRESS,
                WorkOrder.STATUS_PAUSED,
            ],
        )
        planned_total = in_progress.aggregate(t=Sum("quantity_planned"))["t"] or Decimal("0")
        produced_total = in_progress.aggregate(t=Sum("quantity_produced"))["t"] or Decimal("0")
        efficiency = (
            float(produced_total / planned_total * 100) if planned_total else 100.0
        )

        daily_output = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            actual = (
                OutputRecord.objects.filter(is_active=True, date=d).aggregate(
                    t=Sum("quantity_produced")
                )["t"]
                or Decimal("0")
            )
            planned = (
                WorkOrder.objects.filter(
                    is_active=True,
                    planned_start__date=d,
                ).aggregate(t=Sum("quantity_planned"))["t"]
                or Decimal("0")
            )
            daily_output.append(
                {
                    "date": d.isoformat(),
                    "planned": str(planned),
                    "actual": str(actual),
                }
            )

        return {
            "active_work_orders": active_wos.count(),
            "units_today": str(units_today),
            "units_this_month": str(units_month),
            "efficiency_rate": round(efficiency, 1),
            "active_wo_ids": list(
                WorkOrder.objects.filter(
                    is_active=True,
                    status__in=[
                        WorkOrder.STATUS_APPROVED,
                        WorkOrder.STATUS_ASSIGNED,
                        WorkOrder.STATUS_IN_PROGRESS,
                        WorkOrder.STATUS_PAUSED,
                    ],
                ).values_list("id", flat=True)[:20]
            ),
            "raw_material_status": ProductionService.raw_material_status(),
            "machine_ids": list(
                Machine.objects.filter(is_active=True).values_list("id", flat=True)
            ),
            "daily_output": daily_output,
        }
