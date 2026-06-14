"""
Seed sample procurement data: suppliers, purchase requisitions, RFQ.

Prerequisites:
    python manage.py migrate
    python manage.py seed_fms
    python manage.py seed_procurement

Optional: inventory items (created automatically if missing).
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Currency
from apps.inventory.models import Item, ItemCategory, Warehouse
from apps.procurement.models import (
    PurchaseRequisition,
    PurchaseRequisitionItem,
    RequestForQuotation,
    RFQSupplier,
    Supplier,
)
from apps.procurement.utils import generate_document_number
from apps.users.models import Department, User

SAMPLE_ITEMS = [
    ("RM-STEEL-01", "Raw Steel Wire 6mm", "RAW_MATERIAL", "KG", Decimal("4500")),
    ("RM-MESH-01", "Galvanized Wire Mesh Roll", "RAW_MATERIAL", "ROLL", Decimal("185000")),
    ("TL-DRILL-01", "Rock Drill Bit 38mm", "TRADED", "PCS", Decimal("320000")),
    ("TL-BEAR-01", "Industrial Bearing 6205", "TRADED", "PCS", Decimal("45000")),
    ("MF-WIRE-01", "Welding Electrode 3.2mm", "RAW_MATERIAL", "BOX", Decimal("28000")),
    ("MF-MESH-BLANK", "Wire Mesh Roll (Unconfigured)", "MANUFACTURED", "ROLL", Decimal("0")),
]

SAMPLE_SUPPLIERS = [
    {
        "name": "Tanzania Steel Supplies Ltd",
        "tin_number": "100-200-300",
        "email": "sales@tzsteelsupplies.co.tz",
        "phone": "+255 22 211 0001",
        "city": "Dar es Salaam",
        "country": "Tanzania",
        "payment_terms": Supplier.PAYMENT_NET_30,
        "rating": 5,
    },
    {
        "name": "China Mining Tools Co.",
        "tin_number": "CN-MIN-8842",
        "email": "export@chinaminingtools.com",
        "phone": "+86 21 5555 0100",
        "city": "Shanghai",
        "country": "China",
        "payment_terms": Supplier.PAYMENT_NET_60,
        "rating": 4,
    },
    {
        "name": "Dar Industrial Parts Ltd",
        "tin_number": "200-300-400",
        "email": "orders@darindustrial.co.tz",
        "phone": "+255 22 277 8899",
        "city": "Dar es Salaam",
        "country": "Tanzania",
        "payment_terms": Supplier.PAYMENT_NET_15,
        "rating": 4,
    },
    {
        "name": "East Africa Wire Mesh Ltd",
        "tin_number": "300-400-500",
        "email": "procurement@eawiremesh.co.tz",
        "phone": "+255 27 254 1200",
        "city": "Arusha",
        "country": "Tanzania",
        "payment_terms": Supplier.PAYMENT_IMMEDIATE,
        "rating": 3,
    },
]


class Command(BaseCommand):
    help = "Seed sample suppliers and purchase requisitions for procurement module"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Remove previously seeded sample procurement records",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            self._clear_sample_data()
            self.stdout.write(self.style.SUCCESS("Sample procurement data cleared."))
            return

        admin = User.objects.filter(email="admin@rocksolutions.co.tz").first()
        if not admin:
            self.stderr.write("Run seed_fms first — admin user not found.")
            return

        tzs = Currency.objects.filter(code="TZS").first()
        if not tzs:
            self.stderr.write("Run seed_fms first — TZS currency not found.")
            return

        procurement_dept = Department.objects.filter(name="Procurement").first()
        production_dept = Department.objects.filter(name="Production").first()
        if not procurement_dept or not production_dept:
            self.stderr.write("Departments missing — run seed_fms first.")
            return

        items = self._ensure_sample_items(tzs)
        suppliers = self._ensure_suppliers(tzs)
        self._ensure_warehouse()
        prs = self._ensure_requisitions(admin, procurement_dept, production_dept, items)
        self._ensure_sample_rfq(admin, prs, suppliers)

        self.stdout.write(self.style.SUCCESS("Procurement sample data seeded successfully."))
        self.stdout.write(f"  Suppliers: {len(suppliers)}")
        self.stdout.write(f"  Requisitions: {len(prs)}")

    def _clear_sample_data(self):
        tins = [s["tin_number"] for s in SAMPLE_SUPPLIERS]
        Supplier.objects.filter(tin_number__in=tins).update(is_active=False)
        PurchaseRequisition.objects.filter(
            pr_number__startswith="PR-",
            notes__icontains="[SAMPLE]",
        ).delete()

    def _ensure_sample_items(self, currency):
        category, _ = ItemCategory.objects.get_or_create(
            name="Raw Materials",
            parent=None,
            defaults={"description": "Production raw materials"},
        )
        items = []
        for code, name, item_type, uom, cost in SAMPLE_ITEMS:
            item, _ = Item.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": category,
                    "item_type": item_type,
                    "unit_of_measure": uom,
                    "currency": currency,
                    "unit_cost": cost,
                    "selling_price": cost * Decimal("1.2"),
                    "reorder_level": Decimal("10"),
                    "is_active": True,
                },
            )
            items.append(item)
        self.stdout.write(self.style.SUCCESS(f"  Inventory items: {len(items)}"))
        return items

    def _ensure_warehouse(self):
        Warehouse.objects.get_or_create(
            name="Main Warehouse",
            defaults={"location": "Ubungo Industrial Area, Dar es Salaam", "is_active": True},
        )

    def _ensure_suppliers(self, currency):
        suppliers = []
        for data in SAMPLE_SUPPLIERS:
            supplier, created = Supplier.objects.update_or_create(
                tin_number=data["tin_number"],
                defaults={
                    **data,
                    "registration_number": f"REG-{data['tin_number']}",
                    "vat_number": f"VAT-{data['tin_number']}",
                    "address": f"{data['city']}, {data['country']}",
                    "currency": currency,
                    "is_active": True,
                },
            )
            suppliers.append(supplier)
            label = "created" if created else "updated"
            self.stdout.write(f"    Supplier {label}: {supplier.name}")
        return suppliers

    def _ensure_requisitions(self, admin, procurement_dept, production_dept, items):
        specs = [
            {
                "key": "draft-production",
                "department": production_dept,
                "priority": PurchaseRequisition.PRIORITY_MEDIUM,
                "status": PurchaseRequisition.STATUS_DRAFT,
                "notes": "[SAMPLE] Draft PR — production raw steel wire requirement",
                "lines": [(items[0], Decimal("500"), Decimal("4500"))],
            },
            {
                "key": "pending-procurement",
                "department": procurement_dept,
                "priority": PurchaseRequisition.PRIORITY_HIGH,
                "status": PurchaseRequisition.STATUS_PENDING,
                "notes": "[SAMPLE] Pending PR — drill bits for mining tools division",
                "lines": [(items[2], Decimal("20"), Decimal("320000"))],
            },
            {
                "key": "approved-wire-mesh",
                "department": production_dept,
                "priority": PurchaseRequisition.PRIORITY_URGENT,
                "status": PurchaseRequisition.STATUS_APPROVED,
                "notes": "[SAMPLE] Approved PR — wire mesh for Q2 production run",
                "lines": [
                    (items[1], Decimal("50"), Decimal("185000")),
                    (items[4], Decimal("100"), Decimal("28000")),
                ],
            },
        ]

        prs = []
        for spec in specs:
            existing = PurchaseRequisition.objects.filter(
                notes=spec["notes"],
                is_active=True,
            ).first()
            if existing:
                prs.append(existing)
                continue

            pr = PurchaseRequisition.objects.create(
                pr_number=generate_document_number("PR", PurchaseRequisition, "pr_number"),
                department=spec["department"],
                priority=spec["priority"],
                status=spec["status"],
                notes=spec["notes"],
                requested_by=admin,
                approved_by=admin if spec["status"] == PurchaseRequisition.STATUS_APPROVED else None,
                approved_at=timezone.now() if spec["status"] == PurchaseRequisition.STATUS_APPROVED else None,
            )
            total = Decimal("0")
            for item, qty, unit_cost in spec["lines"]:
                line = PurchaseRequisitionItem.objects.create(
                    requisition=pr,
                    item=item,
                    quantity_requested=qty,
                    unit_cost_estimate=unit_cost,
                )
                total += line.total_estimate
            pr.total_estimated = total
            pr.save(update_fields=["total_estimated"])
            prs.append(pr)
            self.stdout.write(f"    PR created: {pr.pr_number} ({pr.status})")
        return prs

    def _ensure_sample_rfq(self, admin, prs, suppliers):
        approved = next(
            (p for p in prs if p.status == PurchaseRequisition.STATUS_APPROVED),
            None,
        )
        if not approved:
            return

        if RequestForQuotation.objects.filter(requisition=approved).exists():
            self.stdout.write("    RFQ already exists for approved PR — skipped")
            return

        rfq = RequestForQuotation.objects.create(
            rfq_number=generate_document_number("RFQ", RequestForQuotation, "rfq_number"),
            requisition=approved,
            deadline=timezone.now().date() + timedelta(days=14),
            status=RequestForQuotation.STATUS_OPEN,
            notes="[SAMPLE] RFQ for wire mesh and welding supplies",
            created_by=admin,
        )
        for supplier in suppliers[:3]:
            RFQSupplier.objects.create(rfq=rfq, supplier=supplier)
        self.stdout.write(f"    RFQ created: {rfq.rfq_number}")
