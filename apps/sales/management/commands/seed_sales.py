"""
Seed sample sales data: customers, quotations, sales orders, invoices.

Prerequisites:
    python manage.py migrate
    python manage.py seed_fms
    python manage.py seed_sales
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Currency
from apps.inventory.models import Item
from apps.sales.models import (
    Customer,
    SalesInvoice,
    SalesInvoiceItem,
    SalesOrder,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationItem,
)
from apps.sales.services import SalesService
from apps.sales.utils import generate_document_number
from apps.users.models import User

SAMPLE_CUSTOMERS = [
    {
        "name": "Geita Gold Mining Ltd",
        "tin_number": "100-111-222",
        "vat_number": "40011111R",
        "email": "procurement@geitagold.co.tz",
        "phone": "+255 28 252 0001",
        "address": "Geita Gold Mine, Geita Region",
        "city": "Geita",
        "country": "Tanzania",
        "mine_name": "Geita Gold Mine",
        "mine_location": "Geita, Tanzania",
        "mine_type": Customer.MINE_OPEN_PIT,
        "contact_person": "John Mwangi",
        "contact_phone": "+255 754 111 222",
        "credit_limit": Decimal("500000000"),
        "payment_terms": Customer.PAYMENT_NET_30,
    },
    {
        "name": "Bulyanhulu Gold Mine Ltd",
        "tin_number": "200-222-333",
        "vat_number": "40022222R",
        "email": "supply@bulyanhulu.co.tz",
        "phone": "+255 28 262 0002",
        "address": "Bulyanhulu Mine, Kahama",
        "city": "Kahama",
        "country": "Tanzania",
        "mine_name": "Bulyanhulu Underground Mine",
        "mine_location": "Kahama, Shinyanga",
        "mine_type": Customer.MINE_UNDERGROUND,
        "contact_person": "Sarah Kimaro",
        "contact_phone": "+255 755 222 333",
        "credit_limit": Decimal("300000000"),
        "payment_terms": Customer.PAYMENT_NET_60,
    },
    {
        "name": "North Mara Gold Mine Ltd",
        "tin_number": "300-333-444",
        "email": "orders@northmara.co.tz",
        "phone": "+255 28 272 0003",
        "address": "North Mara Mine, Tarime",
        "city": "Tarime",
        "country": "Tanzania",
        "mine_name": "North Mara Mine",
        "mine_location": "Tarime, Mara Region",
        "mine_type": Customer.MINE_BOTH,
        "contact_person": "Peter Ole Saitoti",
        "contact_phone": "+255 756 333 444",
        "credit_limit": Decimal("200000000"),
        "payment_terms": Customer.PAYMENT_NET_15,
    },
    {
        "name": "Kahama Mining Corporation",
        "tin_number": "400-444-555",
        "email": "purchasing@kahamamining.co.tz",
        "phone": "+255 22 211 5500",
        "address": "Plot 45, Industrial Area, Kahama",
        "city": "Kahama",
        "country": "Tanzania",
        "mine_name": "Kahama Copper Mine",
        "mine_location": "Kahama",
        "mine_type": Customer.MINE_OPEN_PIT,
        "contact_person": "David Mrema",
        "contact_phone": "+255 757 444 555",
        "credit_limit": Decimal("150000000"),
        "payment_terms": Customer.PAYMENT_IMMEDIATE,
    },
]


class Command(BaseCommand):
    help = "Seed sample customers and sales documents"

    @transaction.atomic
    def handle(self, *args, **options):
        admin = User.objects.filter(email="admin@rocksolutions.co.tz").first()
        if not admin:
            self.stdout.write(self.style.ERROR("Run seed_fms first."))
            return

        currency = Currency.objects.filter(code="TZS").first()
        if not currency:
            currency = Currency.objects.first()
        if not currency:
            self.stdout.write(self.style.ERROR("No currency found."))
            return

        items = list(
            Item.objects.filter(
                item_type__in=[Item.ITEM_TYPE_TRADED, Item.ITEM_TYPE_MANUFACTURED],
                is_active=True,
            )[:5]
        )
        if not items:
            self.stdout.write(self.style.WARNING("No traded/manufactured items — skipping line items."))

        customers = []
        for data in SAMPLE_CUSTOMERS:
            cust, created = Customer.objects.update_or_create(
                tin_number=data["tin_number"],
                defaults={**data, "currency": currency},
            )
            customers.append(cust)
            self.stdout.write(f"  {'Created' if created else 'Updated'} customer: {cust.name}")

        if not customers or not items:
            self.stdout.write(self.style.SUCCESS("Customers seeded."))
            return

        c1 = customers[0]
        qt_draft = self._create_quotation(
            c1, currency, admin, SalesQuotation.STATUS_DRAFT, items[:2]
        )
        qt_sent = self._create_quotation(
            customers[1], currency, admin, SalesQuotation.STATUS_SENT, items[1:3]
        )
        qt_accepted = self._create_quotation(
            customers[2], currency, admin, SalesQuotation.STATUS_ACCEPTED, items[:3]
        )

        so = self._create_order(c1, currency, admin, qt_accepted, items[:2])
        inv = self._create_invoice(so, currency, admin, SalesInvoice.STATUS_SENT)

        self.stdout.write(self.style.SUCCESS(
            f"Sales seed complete: {len(customers)} customers, "
            f"3 quotations, 1 SO ({so.so_number}), 1 invoice ({inv.invoice_number})"
        ))

    def _create_quotation(self, customer, currency, user, status, items):
        qt = SalesQuotation.objects.create(
            quotation_number=generate_document_number("QT", SalesQuotation, "quotation_number"),
            customer=customer,
            currency=currency,
            exchange_rate=Decimal("1"),
            valid_until=timezone.now().date() + timedelta(days=30),
            status=status,
            created_by=user,
        )
        for item in items:
            SalesQuotationItem.objects.create(
                quotation=qt,
                item=item,
                quantity=Decimal("10"),
                unit_price=item.selling_price or item.unit_cost,
            )
        SalesService.recalculate_quotation(qt)
        return qt

    def _create_order(self, customer, currency, user, quotation, items):
        order = SalesOrder.objects.create(
            so_number=generate_document_number("SO", SalesOrder, "so_number"),
            customer=customer,
            quotation=quotation,
            currency=currency,
            exchange_rate=Decimal("1"),
            delivery_date=timezone.now().date() + timedelta(days=14),
            delivery_address=customer.address,
            status=SalesOrder.STATUS_CONFIRMED,
            delivery_status=SalesOrder.DELIVERY_PROCESSING,
            created_by=user,
            approved_by=user,
            approved_at=timezone.now(),
        )
        for item in items:
            SalesOrderItem.objects.create(
                sales_order=order,
                item=item,
                quantity_ordered=Decimal("10"),
                unit_price=item.selling_price or item.unit_cost,
            )
        SalesService.recalculate_order(order)
        SalesService.log_activity(order, "Confirmed", user)
        return order

    def _create_invoice(self, order, currency, user, status):
        inv = SalesInvoice.objects.create(
            invoice_number=generate_document_number("INV", SalesInvoice, "invoice_number"),
            sales_order=order,
            customer=order.customer,
            currency=currency,
            exchange_rate=Decimal("1"),
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=30),
            status=status,
            created_by=user,
        )
        for line in order.items.all():
            SalesInvoiceItem.objects.create(
                invoice=inv,
                item=line.item,
                quantity=line.quantity_ordered,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
            )
        SalesService.recalculate_invoice(inv)
        return inv
