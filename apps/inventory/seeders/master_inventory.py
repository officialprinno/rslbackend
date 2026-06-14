"""
Master inventory seeder for Rock Solutions Limited.
"""

from decimal import Decimal

from django.db import transaction

from apps.core.models import Currency
from apps.inventory.data.master_inventory import (
    DEFAULT_MAX_STOCK,
    DEFAULT_MIN_STOCK,
    DEFAULT_REORDER,
    DEFAULT_SAFETY_STOCK,
    MASTER_CATEGORIES,
    MASTER_ITEMS,
)
from apps.inventory.models import Item, ItemCategory


def preview_master_inventory() -> dict:
    """Return catalogue summary without writing to the database."""
    existing_categories = ItemCategory.objects.filter(
        code__in=[c["code"] for c in MASTER_CATEGORIES]
    ).count()
    existing_items = Item.objects.filter(
        code__in=[i["code"] for i in MASTER_ITEMS]
    ).count()
    return {
        "categories_total": len(MASTER_CATEGORIES),
        "items_total": len(MASTER_ITEMS),
        "categories_existing": existing_categories,
        "items_existing": existing_items,
        "categories_pending": len(MASTER_CATEGORIES) - existing_categories,
        "items_pending": len(MASTER_ITEMS) - existing_items,
    }


@transaction.atomic
def seed_master_inventory(*, currency=None, update: bool = False) -> dict:
    """
    Create or update all master inventory categories and items.

    Idempotent: uses code as the natural key. Set update=True to refresh
    existing master records from the catalogue.
    """
    if currency is None:
        currency = Currency.objects.filter(code="TZS", is_active=True).first()
    if not currency:
        raise ValueError("TZS currency not found. Run seed_fms first.")

    stats = {
        "categories_created": 0,
        "categories_updated": 0,
        "items_created": 0,
        "items_updated": 0,
        "items_unchanged": 0,
    }

    category_map: dict[str, ItemCategory] = {}
    for cat_data in MASTER_CATEGORIES:
        category, created = ItemCategory.objects.get_or_create(
            code=cat_data["code"],
            defaults={
                "name": cat_data["name"],
                "description": cat_data["description"],
                "parent": None,
                "is_active": True,
            },
        )
        if created:
            stats["categories_created"] += 1
        elif update:
            changed = False
            for field in ("name", "description"):
                if getattr(category, field) != cat_data[field]:
                    setattr(category, field, cat_data[field])
                    changed = True
            if not category.is_active:
                category.is_active = True
                changed = True
            if changed:
                category.save()
                stats["categories_updated"] += 1
        category_map[cat_data["code"]] = category

    for item_data in MASTER_ITEMS:
        category = category_map[item_data["category_code"]]
        defaults = {
            "name": item_data["name"],
            "category": category,
            "item_type": item_data["item_type"],
            "unit_of_measure": item_data["unit_of_measure"],
            "has_serial_number": item_data["has_serial_number"],
            "has_batch_tracking": item_data["has_batch_tracking"],
            "has_expiry_date": item_data["has_expiry_date"],
            "currency": currency,
            "unit_cost": Decimal("0"),
            "selling_price": Decimal("0"),
            "reorder_level": DEFAULT_REORDER,
            "minimum_stock": DEFAULT_MIN_STOCK,
            "maximum_stock": DEFAULT_MAX_STOCK,
            "safety_stock": DEFAULT_SAFETY_STOCK,
            "is_active": True,
        }
        item, created = Item.objects.get_or_create(
            code=item_data["code"],
            defaults=defaults,
        )
        if created:
            stats["items_created"] += 1
        elif update:
            changed_fields = []
            for key, value in defaults.items():
                if getattr(item, key) != value:
                    setattr(item, key, value)
                    changed_fields.append(key)
            if changed_fields:
                item.save(update_fields=changed_fields + ["updated_at"])
                stats["items_updated"] += 1
            else:
                stats["items_unchanged"] += 1
        else:
            stats["items_unchanged"] += 1

    stats["preview"] = preview_master_inventory()
    return stats
