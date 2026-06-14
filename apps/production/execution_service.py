"""Machine operator production execution workflow."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Case, IntegerField, Sum, When
from django.utils import timezone

from apps.core.models import AuditLog
from apps.inventory.models import StockMovement, Warehouse
from apps.inventory.services import StockService
from apps.production.models import (
    FinishedGoodsReceipt,
    Machine,
    MachineBreakdownRecord,
    WorkOrder,
    WorkOrderExecutionEvent,
    WorkOrderMaterialIssue,
    WorkOrderPauseRecord,
    WorkOrderPendingMaterial,
    WorkOrderProgressEntry,
)
from apps.production.notifications import (
    notify_completion_submitted,
    notify_machine_breakdown,
    notify_operator_assigned,
    notify_ready_for_store_receipt,
)
from apps.production.production_permissions import (
    can_approve_production_completion,
    can_operate_assigned_work_order,
    can_receive_finished_goods,
)
from apps.production.services import ProductionService
from apps.production.utils import generate_document_number


class ProductionExecutionService:
    """Operator-driven production execution without immediate inventory movement."""

    @staticmethod
    def _log_event(wo, user, action, *, old_status="", new_status="", payload=None):
        WorkOrderExecutionEvent.objects.create(
            work_order=wo,
            user=user,
            action=action,
            old_status=old_status or wo.status,
            new_status=new_status or wo.status,
            payload=payload or {},
        )
        AuditLog.objects.create(
            user=user,
            module="production",
            action=action,
            record_id=wo.wo_number,
            old_values={"status": old_status} if old_status else None,
            new_values={"status": new_status, **(payload or {})},
        )

    @staticmethod
    def _transition(wo, user, new_status, action, **payload):
        old = wo.status
        wo.status = new_status
        wo.save(update_fields=["status", "updated_at"])
        ProductionExecutionService._log_event(
            wo, user, action, old_status=old, new_status=new_status, payload=payload
        )

    @staticmethod
    @transaction.atomic
    def assign_operator(wo: WorkOrder, operator, user) -> None:
        if wo.status != WorkOrder.STATUS_APPROVED:
            raise ValueError("Only approved work orders can be assigned to an operator.")
        wo.operator = operator
        wo.assigned_at = timezone.now()
        wo.execution_workflow = True
        old = wo.status
        wo.status = WorkOrder.STATUS_ASSIGNED
        wo.save(update_fields=["operator", "assigned_at", "execution_workflow", "status", "updated_at"])
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_ASSIGN,
            old_status=old,
            new_status=wo.status,
            payload={"operator_id": operator.id},
        )
        notify_operator_assigned(wo)

    @staticmethod
    @transaction.atomic
    def operator_start(wo: WorkOrder, user, *, machine_id=None) -> None:
        if not can_operate_assigned_work_order(user, wo):
            raise PermissionError("You are not assigned to this work order.")
        if wo.status not in (WorkOrder.STATUS_ASSIGNED, WorkOrder.STATUS_APPROVED):
            raise ValueError("Work order must be assigned before starting.")
        if machine_id:
            wo.machine_id = machine_id
        wo.actual_start = timezone.now()
        old = wo.status
        wo.status = WorkOrder.STATUS_IN_PROGRESS
        wo.save(update_fields=["machine", "actual_start", "status", "updated_at"])
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_START,
            old_status=old,
            new_status=wo.status,
            payload={"machine_id": wo.machine_id},
        )
        if wo.machine_id:
            machine = Machine.objects.get(pk=wo.machine_id)
            machine.runtime_condition = Machine.RUNTIME_RUNNING
            machine.runtime_updated_at = timezone.now()
            machine.runtime_updated_by = user
            machine.save(update_fields=["runtime_condition", "runtime_updated_at", "runtime_updated_by", "updated_at"])

    @staticmethod
    @transaction.atomic
    def pause(wo: WorkOrder, user, reason: str) -> WorkOrderPauseRecord:
        if not can_operate_assigned_work_order(user, wo):
            raise PermissionError("You are not assigned to this work order.")
        if wo.status != WorkOrder.STATUS_IN_PROGRESS:
            raise ValueError("Only in-progress work orders can be paused.")
        pause = WorkOrderPauseRecord.objects.create(
            work_order=wo,
            reason=reason,
            paused_at=timezone.now(),
            recorded_by=user,
        )
        old = wo.status
        wo.status = WorkOrder.STATUS_PAUSED
        wo.save(update_fields=["status", "updated_at"])
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_PAUSE,
            old_status=old,
            new_status=wo.status,
            payload={"reason": reason, "pause_id": pause.id},
        )
        return pause

    @staticmethod
    @transaction.atomic
    def resume(wo: WorkOrder, user) -> None:
        if not can_operate_assigned_work_order(user, wo):
            raise PermissionError("You are not assigned to this work order.")
        if wo.status != WorkOrder.STATUS_PAUSED:
            raise ValueError("Work order is not paused.")
        open_pause = (
            WorkOrderPauseRecord.objects.filter(work_order=wo, resumed_at__isnull=True)
            .order_by("-paused_at")
            .first()
        )
        if open_pause:
            now = timezone.now()
            delta = now - open_pause.paused_at
            open_pause.resumed_at = now
            open_pause.downtime_minutes = Decimal(str(round(delta.total_seconds() / 60, 1)))
            open_pause.save(update_fields=["resumed_at", "downtime_minutes"])
        old = wo.status
        wo.status = WorkOrder.STATUS_IN_PROGRESS
        wo.save(update_fields=["status", "updated_at"])
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_RESUME,
            old_status=old,
            new_status=wo.status,
        )

    @staticmethod
    @transaction.atomic
    def record_progress(
        wo: WorkOrder,
        user,
        *,
        quantity_produced: Decimal,
        quantity_defective: Decimal = Decimal("0"),
        machine_notes: str = "",
    ) -> WorkOrderProgressEntry:
        if not can_operate_assigned_work_order(user, wo):
            raise PermissionError("You are not assigned to this work order.")
        if wo.status not in (WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_PAUSED):
            raise ValueError("Progress can only be recorded during active production.")
        progress_pct = Decimal("0")
        if wo.quantity_planned > 0:
            progress_pct = (quantity_produced / wo.quantity_planned * 100).quantize(Decimal("0.1"))
        entry = WorkOrderProgressEntry.objects.create(
            work_order=wo,
            quantity_produced=quantity_produced,
            quantity_defective=quantity_defective,
            progress_percent=progress_pct,
            machine_notes=machine_notes,
            recorded_by=user,
        )
        wo.quantity_produced = quantity_produced
        wo.quantity_rejected = quantity_defective
        wo.save(update_fields=["quantity_produced", "quantity_rejected", "updated_at"])
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_PROGRESS,
            payload={
                "quantity_produced": str(quantity_produced),
                "quantity_defective": str(quantity_defective),
                "progress_percent": str(progress_pct),
            },
        )
        return entry

    @staticmethod
    @transaction.atomic
    def record_consumption(
        wo: WorkOrder,
        user,
        lines: list[dict],
    ) -> list[WorkOrderPendingMaterial]:
        if not can_operate_assigned_work_order(user, wo):
            raise PermissionError("You are not assigned to this work order.")
        if wo.status not in (WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_PAUSED):
            raise ValueError("Consumption can only be recorded during active production.")
        if wo.materials_issued:
            raise ValueError("Materials already posted to inventory for this work order.")
        created = []
        for line in lines:
            item_id = line["item_id"]
            qty = Decimal(str(line["quantity_consumed"]))
            waste = Decimal(str(line.get("waste_quantity", "0")))
            if qty <= 0:
                continue
            WorkOrderPendingMaterial.objects.filter(
                work_order=wo, item_id=item_id, posted=False
            ).delete()
            pending = WorkOrderPendingMaterial.objects.create(
                work_order=wo,
                item_id=item_id,
                quantity_consumed=qty,
                waste_quantity=waste,
                recorded_by=user,
            )
            created.append(pending)
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_CONSUMPTION,
            payload={"lines": len(created)},
        )
        return created

    @staticmethod
    @transaction.atomic
    def submit_completion(
        wo: WorkOrder,
        user,
        *,
        quantity_produced: Decimal,
        quantity_defective: Decimal = Decimal("0"),
        machine_condition: str = "",
        completion_notes: str = "",
    ) -> None:
        if not can_operate_assigned_work_order(user, wo):
            raise PermissionError("You are not assigned to this work order.")
        if wo.status not in (WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_PAUSED):
            raise ValueError("Only active work orders can be submitted for completion.")
        wo.quantity_produced = quantity_produced
        wo.quantity_rejected = quantity_defective
        wo.machine_condition = machine_condition
        wo.completion_notes = completion_notes
        old = wo.status
        wo.status = WorkOrder.STATUS_COMPLETED_PENDING
        wo.save(
            update_fields=[
                "quantity_produced",
                "quantity_rejected",
                "machine_condition",
                "completion_notes",
                "status",
                "updated_at",
            ]
        )
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_SUBMIT,
            old_status=old,
            new_status=wo.status,
            payload={
                "quantity_produced": str(quantity_produced),
                "quantity_defective": str(quantity_defective),
            },
        )
        notify_completion_submitted(wo)

    @staticmethod
    @transaction.atomic
    def approve_production(wo: WorkOrder, user) -> FinishedGoodsReceipt:
        if not can_approve_production_completion(user):
            raise PermissionError("Production supervisor approval required.")
        if wo.status != WorkOrder.STATUS_COMPLETED_PENDING:
            raise ValueError("Work order is not pending production approval.")
        warehouse = ProductionService.default_warehouse()
        pending_lines = wo.pending_materials.filter(posted=False)
        if pending_lines.exists():
            for pending in pending_lines.select_related("item"):
                total_qty = pending.quantity_consumed + pending.waste_quantity
                StockService.apply_quantity_change(
                    item=pending.item,
                    warehouse=warehouse,
                    delta=-total_qty,
                    movement_type=StockMovement.MOVEMENT_PRODUCTION_CONSUMPTION,
                    reference_type=StockMovement.REFERENCE_WORK_ORDER,
                    reference_id=wo.wo_number,
                    notes=f"Production consumption for {wo.wo_number}",
                    created_by=user,
                )
                WorkOrderMaterialIssue.objects.create(
                    work_order=wo,
                    item=pending.item,
                    quantity_issued=pending.quantity_consumed,
                    wastage=pending.waste_quantity,
                )
                pending.posted = True
                pending.save(update_fields=["posted"])
        elif not wo.materials_issued:
            for line in wo.bom.items.select_related("item"):
                qty = line.effective_quantity * wo.quantity_planned
                WorkOrderPendingMaterial.objects.get_or_create(
                    work_order=wo,
                    item=line.item,
                    posted=True,
                    defaults={
                        "quantity_consumed": qty,
                        "waste_quantity": Decimal("0"),
                        "recorded_by": user,
                    },
                )
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
        wo.materials_issued = True
        wo.production_approved_by = user
        wo.production_approved_at = timezone.now()
        old = wo.status
        wo.status = WorkOrder.STATUS_WAITING_STORE
        wo.save(
            update_fields=[
                "materials_issued",
                "production_approved_by",
                "production_approved_at",
                "status",
                "updated_at",
            ]
        )
        batch = generate_document_number("FG", FinishedGoodsReceipt, "batch_number")
        receipt = FinishedGoodsReceipt.objects.create(
            work_order=wo,
            warehouse=warehouse,
            quantity_received=wo.quantity_produced,
            batch_number=batch,
            notes=f"Pending store receipt for {wo.wo_number}",
            received_by=user,
            posted=False,
        )
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_PROD_APPROVE,
            old_status=old,
            new_status=wo.status,
        )
        notify_ready_for_store_receipt(wo)
        return receipt

    @staticmethod
    @transaction.atomic
    def store_receipt(
        wo: WorkOrder,
        user,
        *,
        warehouse_id: int,
        quantity_received: Decimal,
        batch_number: str = "",
        notes: str = "",
    ) -> FinishedGoodsReceipt:
        if not can_receive_finished_goods(user):
            raise PermissionError("Storekeeper permission required to receive finished goods.")
        if wo.status != WorkOrder.STATUS_WAITING_STORE:
            raise ValueError("Work order is not waiting for store receipt.")
        warehouse = Warehouse.objects.get(pk=warehouse_id, is_active=True)
        receipt = getattr(wo, "finished_goods_receipt", None)
        if receipt and receipt.posted:
            raise ValueError("Finished goods already received.")
        if not receipt:
            receipt = FinishedGoodsReceipt.objects.create(
                work_order=wo,
                warehouse=warehouse,
                quantity_received=quantity_received,
                batch_number=batch_number or generate_document_number("FG", FinishedGoodsReceipt, "batch_number"),
                notes=notes,
                received_by=user,
            )
        else:
            receipt.warehouse = warehouse
            receipt.quantity_received = quantity_received
            if batch_number:
                receipt.batch_number = batch_number
            receipt.notes = notes
            receipt.received_by = user
            receipt.save()
        if quantity_received > 0:
            StockService.apply_quantity_change(
                item=wo.product.item,
                warehouse=warehouse,
                delta=quantity_received,
                movement_type=StockMovement.MOVEMENT_PRODUCTION_OUTPUT,
                reference_type=StockMovement.REFERENCE_WORK_ORDER,
                reference_id=wo.wo_number,
                unit_cost=wo.bom.material_cost_per_unit,
                notes=f"Finished goods receipt {receipt.batch_number}",
                created_by=user,
            )
        receipt.posted = True
        receipt.save(update_fields=["posted", "updated_at"])
        wo.store_received_by = user
        wo.store_received_at = timezone.now()
        wo.actual_end = timezone.now()
        old = wo.status
        wo.status = WorkOrder.STATUS_INV_RECEIVED
        wo.save(
            update_fields=[
                "store_received_by",
                "store_received_at",
                "actual_end",
                "status",
                "updated_at",
            ]
        )
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_STORE_RECEIPT,
            old_status=old,
            new_status=wo.status,
            payload={"quantity_received": str(quantity_received), "warehouse_id": warehouse_id},
        )
        wo.status = WorkOrder.STATUS_CLOSED
        wo.save(update_fields=["status", "updated_at"])
        ProductionExecutionService._log_event(
            wo,
            user,
            WorkOrderExecutionEvent.ACTION_STORE_RECEIPT,
            old_status=WorkOrder.STATUS_INV_RECEIVED,
            new_status=wo.status,
        )
        return receipt

    @staticmethod
    @transaction.atomic
    def report_machine_breakdown(
        machine: Machine,
        user,
        notes: str,
        *,
        photo=None,
        work_order=None,
    ) -> MachineBreakdownRecord:
        machine.status = Machine.STATUS_BREAKDOWN
        machine.runtime_condition = Machine.RUNTIME_BREAKDOWN
        machine.runtime_notes = notes
        machine.notes = notes or machine.notes
        machine.runtime_updated_at = timezone.now()
        machine.runtime_updated_by = user
        machine.save(
            update_fields=[
                "status",
                "runtime_condition",
                "runtime_notes",
                "notes",
                "runtime_updated_at",
                "runtime_updated_by",
                "updated_at",
            ]
        )
        record = MachineBreakdownRecord.objects.create(
            machine=machine,
            work_order=work_order,
            reported_by=user,
            notes=notes,
            photo=photo,
        )
        notify_machine_breakdown(machine, work_order=work_order, reported_by=user)
        if work_order:
            ProductionExecutionService._log_event(
                work_order,
                user,
                WorkOrderExecutionEvent.ACTION_MACHINE_STATUS,
                payload={
                    "machine_id": machine.id,
                    "condition": Machine.RUNTIME_BREAKDOWN,
                    "breakdown_id": record.id,
                    "has_photo": bool(photo),
                },
            )
        return record

    @staticmethod
    @transaction.atomic
    def update_machine_runtime(
        machine: Machine,
        user,
        *,
        condition: str,
        notes: str = "",
        work_order=None,
    ) -> Machine:
        machine.runtime_condition = condition
        machine.runtime_notes = notes
        machine.runtime_updated_at = timezone.now()
        machine.runtime_updated_by = user
        if condition == Machine.RUNTIME_BREAKDOWN:
            machine.status = Machine.STATUS_BREAKDOWN
            notify_machine_breakdown(machine, work_order=work_order, reported_by=user)
        machine.save(
            update_fields=[
                "runtime_condition",
                "runtime_notes",
                "runtime_updated_at",
                "runtime_updated_by",
                "status",
                "updated_at",
            ]
        )
        if work_order:
            ProductionExecutionService._log_event(
                work_order,
                user,
                WorkOrderExecutionEvent.ACTION_MACHINE_STATUS,
                payload={"machine_id": machine.id, "condition": condition, "notes": notes},
            )
        return machine

    @staticmethod
    def _operator_order_row(wo: WorkOrder) -> dict:
        planned = wo.quantity_planned or Decimal("1")
        progress = float((wo.quantity_produced / planned * 100).quantize(Decimal("0.1")))
        machine = wo.machine
        return {
            "id": wo.id,
            "wo_number": wo.wo_number,
            "status": wo.status,
            "product_name": wo.product.name if wo.product_id else "",
            "machine_id": machine.id if machine else None,
            "machine_code": machine.machine_code if machine else "",
            "machine_name": machine.name if machine else "",
            "quantity_planned": str(wo.quantity_planned),
            "quantity_produced": str(wo.quantity_produced),
            "progress_percent": progress,
            "planned_end": wo.planned_end.isoformat() if wo.planned_end else None,
            "can_operator_start": wo.status == WorkOrder.STATUS_ASSIGNED,
        }

    @staticmethod
    def operator_dashboard(user) -> dict:
        base_qs = WorkOrder.objects.filter(is_active=True, execution_workflow=True)
        if user and not user.is_superuser:
            from apps.production.production_permissions import is_production_supervisor

            if not is_production_supervisor(user):
                base_qs = base_qs.filter(operator=user)
        assigned = base_qs.filter(status=WorkOrder.STATUS_ASSIGNED).count()
        in_progress = base_qs.filter(status=WorkOrder.STATUS_IN_PROGRESS).count()
        paused = base_qs.filter(status=WorkOrder.STATUS_PAUSED).count()
        completed = base_qs.filter(
            status__in=[
                WorkOrder.STATUS_COMPLETED_PENDING,
                WorkOrder.STATUS_PROD_APPROVED,
                WorkOrder.STATUS_WAITING_STORE,
                WorkOrder.STATUS_INV_RECEIVED,
                WorkOrder.STATUS_CLOSED,
            ]
        ).count()
        active_qs = (
            base_qs.filter(
                status__in=[
                    WorkOrder.STATUS_ASSIGNED,
                    WorkOrder.STATUS_IN_PROGRESS,
                    WorkOrder.STATUS_PAUSED,
                ]
            )
            .select_related("product", "machine", "operator")
            .annotate(
                sort_priority=Case(
                    When(status=WorkOrder.STATUS_IN_PROGRESS, then=0),
                    When(status=WorkOrder.STATUS_PAUSED, then=1),
                    When(status=WorkOrder.STATUS_ASSIGNED, then=2),
                    default=3,
                    output_field=IntegerField(),
                )
            )
            .order_by("sort_priority", "planned_start")[:10]
        )
        active_list = list(active_qs)
        focus_order = None
        for wo in active_list:
            if wo.status in (WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_PAUSED):
                focus_order = wo
                break
        if focus_order is None and active_list:
            focus_order = active_list[0]

        machine_ids = {
            wo.machine_id for wo in active_list if wo.machine_id
        }
        machines = Machine.objects.filter(is_active=True).order_by("machine_code")
        if machine_ids:
            machines = machines.filter(id__in=machine_ids)
        machines = list(machines[:20])
        machines.sort(
            key=lambda m: (
                0 if m.status == Machine.STATUS_BREAKDOWN else 1,
                m.machine_code,
            )
        )

        total_planned = sum(wo.quantity_planned for wo in active_list)
        total_produced = sum(wo.quantity_produced for wo in active_list)
        efficiency = (
            float(total_produced / total_planned * 100) if total_planned else 100.0
        )

        today = timezone.localdate()
        units_today = WorkOrderProgressEntry.objects.filter(
            recorded_by=user,
            created_at__date=today,
        ).aggregate(total=Sum("quantity_produced"))["total"] or Decimal("0")

        machines_down = Machine.objects.filter(
            is_active=True, status=Machine.STATUS_BREAKDOWN
        ).count()

        return {
            "assigned_count": assigned,
            "in_progress_count": in_progress,
            "paused_count": paused,
            "completed_count": completed,
            "efficiency_rate": round(efficiency, 1),
            "units_today": str(units_today.quantize(Decimal("0.0001"))),
            "machines_down": machines_down,
            "focus_order": (
                ProductionExecutionService._operator_order_row(focus_order)
                if focus_order
                else None
            ),
            "assigned_orders": [
                ProductionExecutionService._operator_order_row(wo) for wo in active_list
            ],
            "machine_status": [
                {
                    "id": m.id,
                    "machine_code": m.machine_code,
                    "name": m.name,
                    "runtime_condition": m.runtime_condition,
                    "status": m.status,
                    "is_breakdown": m.status == Machine.STATUS_BREAKDOWN,
                }
                for m in machines
            ],
        }
