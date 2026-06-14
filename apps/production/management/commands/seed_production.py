"""
Seed wire mesh production data.

Prerequisites:
    python manage.py migrate
    python manage.py seed_fms
    python manage.py seed_procurement  (raw materials)
    python manage.py seed_production
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.inventory.models import Item, ItemCategory, Warehouse
from apps.inventory.services import StockService
from apps.inventory.models import StockMovement
from apps.production.models import (
    BillOfMaterials,
    BOMItem,
    Machine,
    OutputRecord,
    Product,
    WorkOrder,
)
from apps.production.services import ProductionService
from apps.production.utils import generate_document_number, generate_machine_code
from apps.users.models import Department, Role, User

WIRE_MESH_SPECS = {
    "wire_gauge": "4.0",
    "mesh_size": "50 x 50",
    "roll_width": "2.0",
    "roll_length": "50",
    "roll_weight": "120",
}

RAW_MATERIALS = [
    ("RM-STEEL-01", "Raw Steel Wire 6mm", Decimal("5000")),
    ("RM-MESH-01", "Galvanized Wire Mesh Roll", Decimal("500")),
]


class Command(BaseCommand):
    help = "Seed wire mesh product, BOM, machines, and work orders"

    @transaction.atomic
    def handle(self, *args, **options):
        admin = User.objects.filter(email="admin@rocksolutions.co.tz").first()
        if not admin:
            self.stdout.write(self.style.ERROR("Run seed_fms first."))
            return

        prod_dept = Department.objects.filter(name="Production").first()
        op_role = Role.objects.filter(name="Machine Operator", department=prod_dept).first()
        operator, _ = User.objects.get_or_create(
            email="operator@rocksolutions.co.tz",
            defaults={
                "first_name": "Joseph",
                "last_name": "Macha",
                "phone": "+255 754 000 222",
                "department": prod_dept,
                "role": op_role,
                "is_active": True,
            },
        )
        if not operator.has_usable_password():
            operator.set_password("Operator@2024")
            operator.save()

        currency_item = Item.objects.filter(is_active=True).first()
        if not currency_item:
            self.stdout.write(self.style.ERROR("No inventory items. Run seed_procurement."))
            return

        category, _ = ItemCategory.objects.get_or_create(
            name="Wire Mesh Products",
            defaults={"description": "Manufactured wire mesh"},
        )

        mesh_item, _ = Item.objects.get_or_create(
            code="MF-WIRE-MESH-01",
            defaults={
                "name": "Wire Mesh Safety Net — Underground",
                "description": "Rock Solutions underground safety wire mesh",
                "category": category,
                "item_type": Item.ITEM_TYPE_MANUFACTURED,
                "unit_of_measure": "ROLL",
                "currency": currency_item.currency,
                "unit_cost": Decimal("0"),
                "selling_price": Decimal("850000"),
            },
        )

        product, _ = Product.objects.update_or_create(
            item=mesh_item,
            defaults={
                "name": "Wire Mesh Safety Net — Underground",
                "specifications": WIRE_MESH_SPECS,
                "standard_output": Decimal("20"),
                "unit_of_measure": "ROLL",
            },
        )
        self.stdout.write(f"  Product: {product.name}")

        warehouse = Warehouse.objects.filter(is_active=True).first()
        if not warehouse:
            warehouse = Warehouse.objects.create(name="Factory Store", location="Mwanza")

        raw_items = []
        for code, name, qty in RAW_MATERIALS:
            item = Item.objects.filter(code=code).first()
            if item:
                StockService.apply_quantity_change(
                    item=item,
                    warehouse=warehouse,
                    delta=qty,
                    movement_type=StockMovement.MOVEMENT_IN,
                    reference_type=StockMovement.REFERENCE_MANUAL,
                    reference_id="SEED",
                    notes="Production seed stock",
                    created_by=admin,
                )
                raw_items.append(item)

        if len(raw_items) < 2:
            self.stdout.write(self.style.WARNING("Need raw materials from seed_procurement."))
            return

        bom, created = BillOfMaterials.objects.get_or_create(
            product=product,
            version="1.0",
            defaults={
                "status": BillOfMaterials.STATUS_DRAFT,
                "created_by": admin,
                "notes": "Standard underground wire mesh recipe",
            },
        )
        if created or not bom.items.exists():
            BOMItem.objects.filter(bom=bom).delete()
            BOMItem.objects.create(
                bom=bom, item=raw_items[0], quantity_required=Decimal("2.5"), wastage_percent=Decimal("5")
            )
            BOMItem.objects.create(
                bom=bom, item=raw_items[1], quantity_required=Decimal("0.5"), wastage_percent=Decimal("3")
            )
        ProductionService.activate_bom(bom)
        self.stdout.write(f"  BOM v{bom.version} activated")

        machines = []
        for name, mtype in [
            ("Wire Drawing Unit 1", Machine.TYPE_WIRE_DRAWING),
            ("Mesh Weaving Line A", Machine.TYPE_MESH_WEAVING),
            ("Cutting Station 1", Machine.TYPE_CUTTING),
        ]:
            m, _ = Machine.objects.get_or_create(
                machine_code=generate_machine_code(Machine),
                defaults={
                    "name": name,
                    "machine_type": mtype,
                    "status": Machine.STATUS_ACTIVE,
                    "purchase_date": timezone.now().date() - timedelta(days=365 * 2),
                    "last_service_date": timezone.now().date() - timedelta(days=60),
                    "next_service_date": timezone.now().date() + timedelta(days=30),
                },
            )
            machines.append(m)

        now = timezone.now()
        wo_draft, _ = WorkOrder.objects.get_or_create(
            wo_number=generate_document_number("WO", WorkOrder, "wo_number"),
            defaults={
                "product": product,
                "bom": bom,
                "quantity_planned": Decimal("20"),
                "planned_start": now + timedelta(days=1),
                "planned_end": now + timedelta(days=2),
                "shift": WorkOrder.SHIFT_MORNING,
                "status": WorkOrder.STATUS_DRAFT,
                "operator": operator,
                "machine": machines[1],
                "created_by": admin,
                "notes": "Customer order — Geita Gold Mine",
            },
        )

        wo_approved, _ = WorkOrder.objects.get_or_create(
            product=product,
            status=WorkOrder.STATUS_APPROVED,
            defaults={
                "wo_number": generate_document_number("WO", WorkOrder, "wo_number"),
                "bom": bom,
                "quantity_planned": Decimal("15"),
                "planned_start": now,
                "planned_end": now + timedelta(hours=8),
                "shift": WorkOrder.SHIFT_AFTERNOON,
                "operator": operator,
                "machine": machines[1],
                "created_by": admin,
                "approved_by": admin,
                "approved_at": now,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f"Production seed complete: 1 product, 1 BOM, {len(machines)} machines, "
            f"2 work orders ({wo_draft.wo_number}, {wo_approved.wo_number})"
        ))
