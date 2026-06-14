"""Backfill invoice delivery costs and sync invoice status from sales orders."""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.sales.models import SalesInvoice, SalesOrder
from apps.sales.services import SalesService


class Command(BaseCommand):
    help = "Sync customer invoice status and delivery cost from linked sales orders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--so-number",
            type=str,
            help="Sync only the sales order with this number (e.g. SO-2026-006).",
        )

    def handle(self, *args, **options):
        so_number = options.get("so_number")
        orders = SalesOrder.objects.filter(is_active=True).exclude(invoices__isnull=True)
        if so_number:
            orders = orders.filter(so_number=so_number)

        updated_orders = 0
        for order in orders.distinct():
            before = list(
                order.invoices.filter(is_active=True).values(
                    "invoice_number", "status", "paid_amount", "delivery_cost"
                )
            )
            SalesService.sync_order_invoices(order)
            after = list(
                order.invoices.filter(is_active=True).values(
                    "invoice_number", "status", "paid_amount", "delivery_cost"
                )
            )
            if before != after:
                updated_orders += 1
                self.stdout.write(f"{order.so_number}:")
                for inv_before, inv_after in zip(before, after):
                    self.stdout.write(
                        f"  {inv_after['invoice_number']}: "
                        f"{inv_before['status']} -> {inv_after['status']}, "
                        f"paid {inv_before['paid_amount']} -> {inv_after['paid_amount']}, "
                        f"delivery {inv_before['delivery_cost']} -> {inv_after['delivery_cost']}"
                    )

        # Fix legacy invoices that had delivery baked into total without delivery_cost field
        legacy = SalesInvoice.objects.filter(
            is_active=True,
            sales_order__isnull=False,
            delivery_cost=Decimal("0"),
        ).select_related("sales_order")
        if so_number:
            legacy = legacy.filter(sales_order__so_number=so_number)

        for invoice in legacy:
            order = invoice.sales_order
            if order and order.delivery_cost:
                invoice.delivery_cost = order.delivery_cost
                SalesService.recalculate_invoice(invoice)
                SalesService.sync_order_invoices(order)
                self.stdout.write(
                    f"Backfilled delivery cost on {invoice.invoice_number}: "
                    f"{order.delivery_cost}"
                )

        self.stdout.write(
            self.style.SUCCESS(f"Done. Updated invoices for {updated_orders} order(s).")
        )
