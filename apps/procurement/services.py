"""Procurement business logic — GRN confirmation, PO status, 3-way match."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.inventory.models import StockMovement
from apps.inventory.services import StockService
from apps.procurement.models import (
    GoodsReceivedNote,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequisition,
    PurchaseRequisitionItem,
    SupplierInvoice,
    SupplierQuotation,
)


class ProcurementService:
    """Core procurement workflow operations."""

    @staticmethod
    def recalculate_requisition_total(requisition):
        total = sum(
            (line.total_estimate for line in requisition.items.all()),
            Decimal("0"),
        )
        requisition.total_estimated = total
        requisition.save(update_fields=["total_estimated", "updated_at"])

    @staticmethod
    def recalculate_po_totals(po: PurchaseOrder):
        subtotal = sum(
            (line.total_price for line in po.items.all()),
            Decimal("0"),
        )
        po.subtotal = subtotal
        po.tax_amount = subtotal * Decimal("0.18") if po.apply_vat else Decimal("0")
        po.total_amount = subtotal + po.tax_amount
        po.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])

    @staticmethod
    def recalculate_quotation_total(quotation):
        total = sum(
            (line.total_price for line in quotation.items.all()),
            Decimal("0"),
        )
        quotation.total_amount = total
        quotation.save(update_fields=["total_amount", "updated_at"])

    @staticmethod
    @transaction.atomic
    def confirm_grn(grn: GoodsReceivedNote) -> dict:
        """Confirm GRN — update stock and PO receipt status."""
        if grn.status != GoodsReceivedNote.STATUS_DRAFT:
            raise ValidationError("Only draft GRNs can be confirmed.")

        po = grn.purchase_order
        if po.status not in (
            PurchaseOrder.STATUS_APPROVED,
            PurchaseOrder.STATUS_SENT,
            PurchaseOrder.STATUS_PARTIAL,
        ):
            raise ValidationError("PO must be approved or sent before receiving goods.")

        stock_summary = []
        for line in grn.items.select_related("item", "po_item"):
            if line.quantity_received <= 0:
                continue
            if line.condition == line.CONDITION_REJECTED:
                continue

            StockService.apply_quantity_change(
                item=line.item,
                warehouse=grn.warehouse,
                delta=line.quantity_received,
                movement_type=StockMovement.MOVEMENT_IN,
                reference_type=StockMovement.REFERENCE_GRN,
                reference_id=grn.grn_number,
                unit_cost=line.unit_cost,
                serial_number=line.serial_number,
                expiry_date=line.expiry_date,
                notes=line.notes,
                created_by=grn.received_by,
            )

            po_item = line.po_item
            po_item.quantity_received += line.quantity_received
            po_item.save(update_fields=["quantity_received", "updated_at"])

            stock_summary.append(
                {
                    "item": line.item.name,
                    "quantity": str(line.quantity_received),
                    "warehouse": grn.warehouse.name,
                }
            )

        all_received = True
        any_received = False
        for po_item in po.items.all():
            if po_item.quantity_received > 0:
                any_received = True
            if po_item.quantity_received < po_item.quantity_ordered:
                all_received = False

        if all_received:
            po.status = PurchaseOrder.STATUS_RECEIVED
        elif any_received:
            po.status = PurchaseOrder.STATUS_PARTIAL
        po.save(update_fields=["status", "updated_at"])

        grn.status = GoodsReceivedNote.STATUS_CONFIRMED
        grn.save(update_fields=["status", "updated_at"])

        return {"grn": grn, "stock_updates": stock_summary, "po_status": po.status}

    @staticmethod
    def match_invoice(invoice: SupplierInvoice) -> SupplierInvoice:
        """Perform 3-way match: PO total vs GRN value vs invoice total."""
        po_total = invoice.purchase_order.total_amount
        grn_value = sum(
            (
                line.quantity_received * line.unit_cost
                for line in invoice.grn.items.all()
            ),
            Decimal("0"),
        )
        tolerance = Decimal("1")
        matched = (
            abs(po_total - invoice.total_amount) <= tolerance
            and abs(grn_value - invoice.total_amount) <= tolerance
        )
        invoice.three_way_matched = matched
        invoice.save(update_fields=["three_way_matched", "updated_at"])
        return invoice

    @staticmethod
    @transaction.atomic
    def select_quotation(quotation: SupplierQuotation, user) -> PurchaseOrder:
        """Mark quotation selected and create a draft PO."""
        from apps.procurement.utils import generate_document_number

        quotation.status = SupplierQuotation.STATUS_SELECTED
        quotation.save(update_fields=["status", "updated_at"])
        SupplierQuotation.objects.filter(rfq=quotation.rfq).exclude(
            pk=quotation.pk
        ).update(status=SupplierQuotation.STATUS_REJECTED)

        po = PurchaseOrder.objects.create(
            po_number=generate_document_number("PO", PurchaseOrder, "po_number"),
            supplier=quotation.supplier,
            quotation=quotation,
            requisition=quotation.rfq.requisition,
            currency=quotation.currency,
            exchange_rate=quotation.exchange_rate,
            order_date=timezone.now().date(),
            expected_delivery=None,
            payment_terms=quotation.supplier.payment_terms,
            subtotal=quotation.total_amount,
            tax_amount=quotation.total_amount * Decimal("0.18"),
            apply_vat=True,
            total_amount=quotation.total_amount * Decimal("1.18"),
            status=PurchaseOrder.STATUS_DRAFT,
            created_by=user,
        )

        for q_item in quotation.items.select_related("item"):
            pr_item = PurchaseRequisitionItem.objects.filter(
                requisition=quotation.rfq.requisition,
                item=q_item.item,
            ).first()
            qty = q_item.quantity
            PurchaseOrderItem.objects.create(
                purchase_order=po,
                item=q_item.item,
                quantity_ordered=qty,
                unit_price=q_item.unit_price,
                discount_percent=Decimal("0"),
            )

        return po
