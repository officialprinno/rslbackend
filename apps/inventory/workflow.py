"""Inventory workflow operations — transfers, issues, stock takes."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.audit import log_audit
from apps.inventory.dept_request_notifications import (
    notify_request_approved,
    notify_request_issued,
    notify_request_rejected,
    notify_request_submitted,
)
from apps.inventory.models import (
    DepartmentRequest,
    DepartmentRequestLine,
    GoodsIssueLine,
    GoodsIssueNote,
    Item,
    Stock,
    StockAdjustment,
    StockMovement,
    StockTake,
    StockTransfer,
)
from apps.inventory.services import InsufficientStockError, StockService
from apps.inventory.utils import generate_inventory_number


SUBMITTED_STATUSES = frozenset(
    {
        DepartmentRequest.STATUS_PENDING,
        DepartmentRequest.STATUS_SUBMITTED,
    }
)


def _line_requested(line: DepartmentRequestLine) -> Decimal:
    return line.requested_qty or line.quantity


def _validate_internal_items(lines):
    for line in lines:
        usage = line.item.item_usage
        if usage == Item.USAGE_FOR_SALE:
            raise ValidationError(
                f"Item {line.item.code} is for sale only and cannot be requisitioned internally."
            )


@transaction.atomic
def approve_stock_transfer(transfer: StockTransfer, user) -> StockTransfer:
    if transfer.status != StockTransfer.STATUS_PENDING:
        raise ValidationError("Only pending transfers can be approved.")
    transfer.status = StockTransfer.STATUS_APPROVED
    transfer.approved_by = user
    transfer.approved_at = timezone.now()
    transfer.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return transfer


@transaction.atomic
def complete_stock_transfer(transfer: StockTransfer, user) -> StockTransfer:
    if transfer.status != StockTransfer.STATUS_APPROVED:
        raise ValidationError("Only approved transfers can be completed.")
    for line in transfer.lines.select_related("item"):
        StockService.record_movement(
            item=line.item,
            warehouse=transfer.source_warehouse,
            movement_type=StockMovement.MOVEMENT_OUT,
            quantity=line.quantity,
            reference_type=StockMovement.REFERENCE_TRANSFER,
            reference_id=transfer.transfer_number,
            notes=f"Transfer to {transfer.destination_warehouse.name}",
            created_by=user,
        )
        StockService.record_movement(
            item=line.item,
            warehouse=transfer.destination_warehouse,
            movement_type=StockMovement.MOVEMENT_IN,
            quantity=line.quantity,
            reference_type=StockMovement.REFERENCE_TRANSFER,
            reference_id=transfer.transfer_number,
            notes=f"Transfer from {transfer.source_warehouse.name}",
            created_by=user,
        )
    transfer.status = StockTransfer.STATUS_COMPLETED
    transfer.save(update_fields=["status", "updated_at"])
    return transfer


@transaction.atomic
def reject_stock_transfer(transfer: StockTransfer, user) -> StockTransfer:
    if transfer.status != StockTransfer.STATUS_PENDING:
        raise ValidationError("Only pending transfers can be rejected.")
    transfer.status = StockTransfer.STATUS_REJECTED
    transfer.approved_by = user
    transfer.approved_at = timezone.now()
    transfer.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return transfer


@transaction.atomic
def submit_department_request(request: DepartmentRequest, user) -> DepartmentRequest:
    if request.status != DepartmentRequest.STATUS_DRAFT:
        raise ValidationError("Only draft requests can be submitted.")
    if request.requested_by_id != user.id:
        raise ValidationError("You can only submit your own requests.")
    old_status = request.status
    request.status = DepartmentRequest.STATUS_SUBMITTED
    request.save(update_fields=["status", "updated_at"])
    log_audit(
        user,
        "inventory",
        "dept_request_submit",
        request.request_number,
        old_values={"status": old_status},
        new_values={"status": request.status},
    )
    notify_request_submitted(request)
    return request


@transaction.atomic
def cancel_department_request(request: DepartmentRequest, user) -> DepartmentRequest:
    if request.status != DepartmentRequest.STATUS_DRAFT:
        raise ValidationError("Only draft requests can be cancelled.")
    if request.requested_by_id != user.id:
        raise ValidationError("You can only cancel your own requests.")
    request.is_active = False
    request.save(update_fields=["is_active", "updated_at"])
    log_audit(
        user,
        "inventory",
        "dept_request_cancel",
        request.request_number,
        new_values={"is_active": False},
    )
    return request


@transaction.atomic
def approve_department_request(
    request: DepartmentRequest, user, *, comment: str = ""
) -> DepartmentRequest:
    if request.status not in SUBMITTED_STATUSES:
        raise ValidationError("Only submitted requests can be approved.")
    old_status = request.status
    request.status = DepartmentRequest.STATUS_APPROVED
    request.approved_by = user
    request.approved_at = timezone.now()
    request.approval_comment = comment or request.approval_comment
    request.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "approval_comment",
            "updated_at",
        ]
    )
    log_audit(
        user,
        "inventory",
        "dept_request_approve",
        request.request_number,
        old_values={"status": old_status},
        new_values={"status": request.status, "comment": comment},
        department_context=request.department,
    )
    notify_request_approved(request)
    return request


def _create_internal_gin(request: DepartmentRequest, user, lines_issued) -> GoodsIssueNote:
    gin = GoodsIssueNote.objects.create(
        gin_number=create_gin_number(),
        issue_type=GoodsIssueNote.ISSUE_INTERNAL,
        department=request.department,
        warehouse=request.warehouse,
        status=GoodsIssueNote.STATUS_APPROVED,
        reason=request.purpose or f"Internal issue for {request.request_number}",
        requested_by=user,
        approved_by=user,
        approved_at=timezone.now(),
        department_request=request,
    )
    for line, qty in lines_issued:
        GoodsIssueLine.objects.create(gin=gin, item=line.item, quantity=qty)
    return gin


@transaction.atomic
def issue_department_request(
    request: DepartmentRequest,
    user,
    *,
    line_quantities=None,
    partial: bool = False,
) -> DepartmentRequest:
    """Issue stock for an approved request. Stock deducts only on confirmed issue."""
    if request.status not in (
        DepartmentRequest.STATUS_APPROVED,
        DepartmentRequest.STATUS_PROCESSING,
        DepartmentRequest.STATUS_PARTIALLY_ISSUED,
    ):
        raise ValidationError("Only approved requests can be issued.")

    request.status = DepartmentRequest.STATUS_PROCESSING
    request.save(update_fields=["status", "updated_at"])

    lines = list(request.lines.select_related("item"))
    _validate_internal_items(lines)
    qty_map = {entry["line_id"]: Decimal(str(entry["quantity"])) for entry in (line_quantities or [])}

    lines_issued = []
    any_partial = False
    all_complete = True

    for line in lines:
        requested = _line_requested(line)
        remaining = requested - (line.issued_qty or Decimal("0"))
        if remaining <= 0:
            continue

        if qty_map:
            issue_qty = qty_map.get(line.id, remaining)
        elif partial:
            issue_qty = remaining
        else:
            issue_qty = remaining

        if issue_qty <= 0:
            continue
        if issue_qty > remaining:
            raise ValidationError(f"Issue quantity exceeds remaining for {line.item.code}.")

        wh = line.warehouse or request.warehouse
        stock = Stock.objects.filter(item=line.item, warehouse=wh).first()
        available = stock.quantity_available if stock else Decimal("0")
        if issue_qty > available:
            if partial and available > 0:
                issue_qty = available
                any_partial = True
            else:
                raise ValidationError(
                    f"Insufficient stock for {line.item.code}. "
                    f"Available: {available}, requested: {issue_qty}."
                )

        if issue_qty <= 0:
            all_complete = False
            continue

        StockService.record_movement(
            item=line.item,
            warehouse=wh,
            movement_type=StockMovement.MOVEMENT_OUT,
            quantity=issue_qty,
            reference_type=StockMovement.REFERENCE_DEPT_REQUEST,
            reference_id=request.request_number,
            unit_cost=line.item.unit_cost,
            notes=f"Internal consumption: {request.get_department_display()}",
            created_by=user,
        )
        line.issued_qty = (line.issued_qty or Decimal("0")) + issue_qty
        line.save(update_fields=["issued_qty"])
        lines_issued.append((line, issue_qty))

        if line.issued_qty < requested:
            all_complete = False
            any_partial = True

    if not lines_issued:
        raise ValidationError("Nothing to issue — check stock availability.")

    gin = _create_internal_gin(request, user, lines_issued)

    if all_complete and not any_partial:
        request.status = DepartmentRequest.STATUS_ISSUED
        notify_partial = False
    else:
        request.status = DepartmentRequest.STATUS_PARTIALLY_ISSUED
        notify_partial = True

    request.issued_at = timezone.now()
    request.save(update_fields=["status", "issued_at", "updated_at"])

    log_audit(
        user,
        "inventory",
        "dept_request_issue",
        request.request_number,
        new_values={
            "status": request.status,
            "gin_number": gin.gin_number,
            "partial": notify_partial,
        },
        department_context=request.department,
    )
    notify_request_issued(request, partial=notify_partial)
    return request


@transaction.atomic
def reject_department_request(
    request: DepartmentRequest, user, *, reason: str = ""
) -> DepartmentRequest:
    if request.status not in SUBMITTED_STATUSES:
        raise ValidationError("Only submitted requests can be rejected.")
    old_status = request.status
    request.status = DepartmentRequest.STATUS_REJECTED
    request.approved_by = user
    request.approved_at = timezone.now()
    request.rejection_reason = reason
    request.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "updated_at",
        ]
    )
    log_audit(
        user,
        "inventory",
        "dept_request_reject",
        request.request_number,
        old_values={"status": old_status},
        new_values={"status": request.status, "reason": reason},
        department_context=request.department,
    )
    notify_request_rejected(request)
    return request


@transaction.atomic
def approve_goods_issue(gin: GoodsIssueNote, user) -> GoodsIssueNote:
    if gin.status not in (GoodsIssueNote.STATUS_PENDING, GoodsIssueNote.STATUS_DRAFT):
        raise ValidationError("Only pending GINs can be approved.")
    if gin.department_request_id:
        gin.status = GoodsIssueNote.STATUS_APPROVED
        gin.approved_by = user
        gin.approved_at = timezone.now()
        gin.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return gin

    ref_type = StockMovement.REFERENCE_GIN
    for line in gin.lines.select_related("item"):
        StockService.record_movement(
            item=line.item,
            warehouse=gin.warehouse,
            movement_type=StockMovement.MOVEMENT_OUT,
            quantity=line.quantity,
            reference_type=ref_type,
            reference_id=gin.gin_number,
            notes=gin.reason or f"Issue to {gin.get_department_display()}",
            created_by=user,
        )
    gin.status = GoodsIssueNote.STATUS_APPROVED
    gin.approved_by = user
    gin.approved_at = timezone.now()
    gin.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return gin


@transaction.atomic
def reject_goods_issue(gin: GoodsIssueNote, user) -> GoodsIssueNote:
    if gin.status not in (GoodsIssueNote.STATUS_PENDING, GoodsIssueNote.STATUS_DRAFT):
        raise ValidationError("Only pending GINs can be rejected.")
    gin.status = GoodsIssueNote.STATUS_REJECTED
    gin.approved_by = user
    gin.approved_at = timezone.now()
    gin.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return gin


@transaction.atomic
def approve_stock_take(stock_take: StockTake, user) -> StockTake:
    if stock_take.status != StockTake.STATUS_PENDING:
        raise ValidationError("Only pending stock takes can be approved.")
    for line in stock_take.lines.select_related("item"):
        variance = line.variance
        if variance == 0:
            continue
        adjustment_type = (
            StockAdjustment.ADJUSTMENT_INCREASE
            if variance > 0
            else StockAdjustment.ADJUSTMENT_PHYSICAL_COUNT
        )
        adjustment = StockAdjustment.objects.create(
            item=line.item,
            warehouse=stock_take.warehouse,
            adjustment_type=adjustment_type,
            quantity=abs(variance),
            reason=line.reason or f"Stock take {stock_take.take_number}",
            status=StockAdjustment.STATUS_APPROVED,
            requested_by=user,
            approved_by=user,
            approved_at=timezone.now(),
        )
        try:
            StockService.apply_adjustment(adjustment, approved_by=user)
        except InsufficientStockError as exc:
            raise ValidationError(str(exc.detail)) from exc
    stock_take.status = StockTake.STATUS_APPROVED
    stock_take.approved_by = user
    stock_take.approved_at = timezone.now()
    stock_take.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return stock_take


@transaction.atomic
def reject_stock_take(stock_take: StockTake, user) -> StockTake:
    if stock_take.status != StockTake.STATUS_PENDING:
        raise ValidationError("Only pending stock takes can be rejected.")
    stock_take.status = StockTake.STATUS_REJECTED
    stock_take.approved_by = user
    stock_take.approved_at = timezone.now()
    stock_take.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return stock_take


def create_transfer_number():
    return generate_inventory_number("TRF", StockTransfer, "transfer_number")


def create_dept_request_number():
    return generate_inventory_number("DR", DepartmentRequest, "request_number")


def create_gin_number():
    return generate_inventory_number("GIN", GoodsIssueNote, "gin_number")


def create_stock_take_number():
    return generate_inventory_number("STK", StockTake, "take_number")
