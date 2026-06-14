"""Sales business logic."""

from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import Stock
from apps.sales.models import (
    CreditNote,
    Customer,
    CustomerPayment,
    SalesInvoice,
    SalesOrder,
    SalesOrderActivity,
    SalesQuotation,
    SalesQuotationItem,
)


VAT_RATE = Decimal("0.18")


class SalesService:
    """Shared calculations and workflow helpers."""

    @staticmethod
    def line_total(quantity, unit_price, discount_percent=Decimal("0")) -> Decimal:
        gross = quantity * unit_price
        discount = gross * (discount_percent / Decimal("100"))
        return (gross - discount).quantize(Decimal("0.01"))

    @staticmethod
    def recalculate_quotation(quotation: SalesQuotation) -> None:
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        for line in quotation.items.all():
            gross = line.quantity * line.unit_price
            discount = gross * (line.discount_percent / Decimal("100"))
            line.total_price = gross - discount
            line.save(update_fields=["total_price"])
            subtotal += gross
            discount_total += discount
        net = subtotal - discount_total
        tax = net * VAT_RATE if quotation.apply_vat else Decimal("0")
        delivery = quotation.delivery_cost or Decimal("0")
        quotation.subtotal = subtotal
        quotation.discount_amount = discount_total
        quotation.tax_amount = tax
        quotation.total_amount = net + tax + delivery
        quotation.save(
            update_fields=[
                "subtotal",
                "discount_amount",
                "tax_amount",
                "total_amount",
                "updated_at",
            ]
        )

    @staticmethod
    def recalculate_order(order: SalesOrder) -> None:
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        for line in order.items.all():
            gross = line.quantity_ordered * line.unit_price
            discount = gross * (line.discount_percent / Decimal("100"))
            line.total_price = gross - discount
            line.save(update_fields=["total_price"])
            subtotal += gross
            discount_total += discount
        net = subtotal - discount_total
        tax = net * VAT_RATE if order.apply_vat else Decimal("0")
        order.subtotal = subtotal
        order.discount_amount = discount_total
        order.tax_amount = tax
        order.total_amount = net + tax
        order.save(
            update_fields=[
                "subtotal",
                "discount_amount",
                "tax_amount",
                "total_amount",
                "updated_at",
            ]
        )

    @staticmethod
    def recalculate_invoice(invoice: SalesInvoice) -> None:
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        tax_total = Decimal("0")
        for line in invoice.items.all():
            gross = line.quantity * line.unit_price
            discount = gross * (line.discount_percent / Decimal("100"))
            net = gross - discount
            tax = net * (line.tax_rate / Decimal("100"))
            line.total_price = net + tax
            line.save(update_fields=["total_price"])
            subtotal += gross
            discount_total += discount
            tax_total += tax
        invoice.subtotal = subtotal
        invoice.discount_amount = discount_total
        invoice.tax_amount = tax_total
        delivery = invoice.delivery_cost or Decimal("0")
        invoice.total_amount = subtotal - discount_total + tax_total + delivery
        invoice.save(
            update_fields=[
                "subtotal",
                "discount_amount",
                "tax_amount",
                "total_amount",
                "updated_at",
            ]
        )

    @staticmethod
    def order_amount_due(order: SalesOrder) -> Decimal:
        return (order.total_amount or Decimal("0")) + (order.delivery_cost or Decimal("0"))

    @staticmethod
    def quotation_is_editable(quotation: SalesQuotation) -> bool:
        if quotation.status in (
            SalesQuotation.STATUS_REJECTED,
            SalesQuotation.STATUS_EXPIRED,
        ):
            return False
        if quotation.sales_orders.filter(is_active=True).exists():
            return False
        return quotation.status in (
            SalesQuotation.STATUS_DRAFT,
            SalesQuotation.STATUS_SENT,
            SalesQuotation.STATUS_ACCEPTED,
        )

    @staticmethod
    def quotation_is_deletable(quotation: SalesQuotation) -> bool:
        if quotation.sales_orders.filter(is_active=True).exists():
            return False
        return quotation.status in (
            SalesQuotation.STATUS_DRAFT,
            SalesQuotation.STATUS_SENT,
            SalesQuotation.STATUS_ACCEPTED,
        )

    @staticmethod
    def sync_order_invoices(order: SalesOrder) -> None:
        """Keep linked customer invoices aligned with sales order payment state."""
        invoices = SalesInvoice.objects.filter(sales_order=order, is_active=True)
        if not invoices.exists():
            return

        for invoice in invoices:
            update_fields = []

            if order.delivery_cost and invoice.delivery_cost != order.delivery_cost:
                invoice.delivery_cost = order.delivery_cost
                SalesService.recalculate_invoice(invoice)

            if order.payment_status == SalesOrder.PAYMENT_PAID:
                if invoice.paid_amount < invoice.total_amount:
                    invoice.paid_amount = invoice.total_amount
                    update_fields.append("paid_amount")
                if invoice.status != SalesInvoice.STATUS_PAID:
                    invoice.status = SalesInvoice.STATUS_PAID
                    update_fields.append("status")
            elif order.payment_status == SalesOrder.PAYMENT_PARTIAL:
                if invoice.paid_amount >= invoice.total_amount:
                    if invoice.status != SalesInvoice.STATUS_PAID:
                        invoice.status = SalesInvoice.STATUS_PAID
                        update_fields.append("status")
                elif invoice.paid_amount > Decimal("0"):
                    if invoice.status != SalesInvoice.STATUS_PARTIAL:
                        invoice.status = SalesInvoice.STATUS_PARTIAL
                        update_fields.append("status")
            elif invoice.status == SalesInvoice.STATUS_DRAFT:
                invoice.status = SalesInvoice.STATUS_SENT
                update_fields.append("status")

            if update_fields:
                invoice.save(update_fields=list(set(update_fields + ["updated_at"])))

    @staticmethod
    def get_stock_available(item_id: int) -> Decimal:
        total = (
            Stock.objects.filter(item_id=item_id)
            .aggregate(total=Sum("quantity_available"))
            .get("total")
        )
        return total or Decimal("0")

    @staticmethod
    def log_activity(
        order: SalesOrder,
        action: str,
        user,
        details: str = "",
        previous_status: str = "",
        new_status: str = "",
        remarks: str = "",
    ) -> None:
        SalesOrderActivity.objects.create(
            sales_order=order,
            action=action,
            details=details,
            previous_status=previous_status or order.status,
            new_status=new_status or order.status,
            remarks=remarks,
            user=user,
        )

    @staticmethod
    def customer_outstanding(customer: Customer) -> Decimal:
        invoices = SalesInvoice.objects.filter(
            customer=customer,
            is_active=True,
            status__in=[
                SalesInvoice.STATUS_SENT,
                SalesInvoice.STATUS_PARTIAL,
                SalesInvoice.STATUS_OVERDUE,
            ],
        )
        total = sum((inv.balance for inv in invoices), Decimal("0"))
        credits = CreditNote.objects.filter(
            customer=customer,
            status=CreditNote.STATUS_APPLIED,
            is_active=True,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        return max(total - credits, Decimal("0"))

    @staticmethod
    def customer_credit_balance(customer: Customer) -> Decimal:
        outstanding = SalesService.customer_outstanding(customer)
        return customer.credit_limit - outstanding

    @staticmethod
    def update_invoice_status(invoice: SalesInvoice) -> None:
        if invoice.status == SalesInvoice.STATUS_DRAFT:
            return
        if invoice.paid_amount >= invoice.total_amount:
            invoice.status = SalesInvoice.STATUS_PAID
        elif invoice.paid_amount > Decimal("0"):
            invoice.status = SalesInvoice.STATUS_PARTIAL
        elif invoice.due_date < timezone.now().date():
            invoice.status = SalesInvoice.STATUS_OVERDUE
        elif invoice.status not in (SalesInvoice.STATUS_SENT, SalesInvoice.STATUS_OVERDUE):
            invoice.status = SalesInvoice.STATUS_SENT
        invoice.save(update_fields=["status", "updated_at"])

    @staticmethod
    def record_payment(payment: CustomerPayment) -> None:
        invoice = payment.invoice
        invoice.paid_amount += payment.amount
        SalesService.update_invoice_status(invoice)
        invoice.save(update_fields=["paid_amount", "status", "updated_at"])
        if invoice.sales_order_id:
            order = invoice.sales_order
            paid = (
                SalesInvoice.objects.filter(sales_order=order, is_active=True).aggregate(
                    total=Sum("paid_amount")
                )["total"]
                or Decimal("0")
            )
            total = SalesService.order_amount_due(order)
            if paid >= total:
                order.payment_status = SalesOrder.PAYMENT_PAID
            elif paid > Decimal("0"):
                order.payment_status = SalesOrder.PAYMENT_PARTIAL
            order.save(update_fields=["payment_status", "updated_at"])

    @staticmethod
    def apply_credit_note(cn: CreditNote) -> None:
        invoice = cn.invoice
        invoice.paid_amount = min(
            invoice.paid_amount + cn.amount,
            invoice.total_amount,
        )
        SalesService.update_invoice_status(invoice)
        invoice.save(update_fields=["paid_amount", "status", "updated_at"])
        cn.status = CreditNote.STATUS_APPLIED
        cn.save(update_fields=["status", "updated_at"])

    @staticmethod
    def mark_expired_quotations() -> int:
        today = timezone.now().date()
        qs = SalesQuotation.objects.filter(
            valid_until__lt=today,
            status__in=[SalesQuotation.STATUS_DRAFT, SalesQuotation.STATUS_SENT],
            is_active=True,
        )
        return qs.update(status=SalesQuotation.STATUS_EXPIRED)

    @staticmethod
    def mark_overdue_invoices() -> int:
        today = timezone.now().date()
        qs = SalesInvoice.objects.filter(
            due_date__lt=today,
            status__in=[SalesInvoice.STATUS_SENT, SalesInvoice.STATUS_PARTIAL],
            is_active=True,
        )
        return qs.update(status=SalesInvoice.STATUS_OVERDUE)

    @staticmethod
    def customer_statement(customer: Customer, date_from=None, date_to=None):
        """Build account statement lines."""
        lines = []
        invoices = SalesInvoice.objects.filter(customer=customer, is_active=True)
        payments = CustomerPayment.objects.filter(customer=customer, is_active=True)
        credit_notes = CreditNote.objects.filter(
            customer=customer,
            status=CreditNote.STATUS_APPLIED,
            is_active=True,
        )
        if date_from:
            invoices = invoices.filter(invoice_date__gte=date_from)
            payments = payments.filter(payment_date__gte=date_from)
            credit_notes = credit_notes.filter(created_at__date__gte=date_from)
        if date_to:
            invoices = invoices.filter(invoice_date__lte=date_to)
            payments = payments.filter(payment_date__lte=date_to)
            credit_notes = credit_notes.filter(created_at__date__lte=date_to)

        for inv in invoices.order_by("invoice_date"):
            lines.append(
                {
                    "date": inv.invoice_date.isoformat(),
                    "type": "INVOICE",
                    "reference": inv.invoice_number,
                    "description": f"Tax Invoice {inv.invoice_number}",
                    "debit": str(inv.total_amount),
                    "credit": "0",
                }
            )
        for pay in payments.order_by("payment_date"):
            lines.append(
                {
                    "date": pay.payment_date.isoformat(),
                    "type": "PAYMENT",
                    "reference": pay.payment_number,
                    "description": f"Payment for {pay.invoice.invoice_number}",
                    "debit": "0",
                    "credit": str(pay.amount),
                }
            )
        for cn in credit_notes.order_by("created_at"):
            lines.append(
                {
                    "date": cn.created_at.date().isoformat(),
                    "type": "CREDIT_NOTE",
                    "reference": cn.cn_number,
                    "description": cn.reason,
                    "debit": "0",
                    "credit": str(cn.amount),
                }
            )
        lines.sort(key=lambda x: x["date"])
        return lines

    @staticmethod
    def invoice_aging(customer: Customer):
        today = timezone.now().date()
        buckets = {"current": Decimal("0"), "days_30": Decimal("0"), "days_60": Decimal("0"), "days_90_plus": Decimal("0")}
        invoices = SalesInvoice.objects.filter(
            customer=customer,
            is_active=True,
            status__in=[
                SalesInvoice.STATUS_SENT,
                SalesInvoice.STATUS_PARTIAL,
                SalesInvoice.STATUS_OVERDUE,
            ],
        )
        for inv in invoices:
            balance = inv.balance
            if balance <= 0:
                continue
            days = (today - inv.due_date).days
            if days <= 0:
                buckets["current"] += balance
            elif days <= 30:
                buckets["days_30"] += balance
            elif days <= 60:
                buckets["days_60"] += balance
            else:
                buckets["days_90_plus"] += balance
        return {k: str(v) for k, v in buckets.items()}
