"""
Inventory signals — auto stock movements and stock alerts on quantity changes.
"""

from decimal import Decimal

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.inventory.models import Stock, StockAlert, StockMovement


@receiver(pre_save, sender=Stock)
def cache_stock_quantities(sender, instance, **kwargs):
    """Store previous on-hand quantity for movement delta calculation."""
    if instance.pk:
        old = Stock.objects.filter(pk=instance.pk).values("quantity_on_hand").first()
        instance._previous_on_hand = old["quantity_on_hand"] if old else Decimal("0")
    else:
        instance._previous_on_hand = Decimal("0")


@receiver(post_save, sender=Stock)
def create_movement_on_stock_change(sender, instance, created, **kwargs):
    """
    Auto-create a StockMovement when quantity_on_hand changes.

    Movement metadata is supplied via instance._movement_meta from StockService.
    Falls back to ADJUSTMENT/MANUAL when stock is saved without the service.
    """
    previous = getattr(instance, "_previous_on_hand", Decimal("0"))
    delta = instance.quantity_on_hand - previous

    if delta == 0:
        return

    meta = getattr(instance, "_movement_meta", None)
    if meta:
        instance._last_movement = StockMovement.objects.create(
            item=instance.item,
            warehouse=instance.warehouse,
            movement_type=meta["movement_type"],
            reference_type=meta["reference_type"],
            reference_id=meta.get("reference_id", ""),
            quantity=meta["quantity"],
            unit_cost=meta.get("unit_cost", instance.item.unit_cost),
            serial_number=meta.get("serial_number", ""),
            expiry_date=meta.get("expiry_date"),
            notes=meta.get("notes", ""),
            created_by=meta.get("created_by"),
        )
    else:
        instance._last_movement = StockMovement.objects.create(
            item=instance.item,
            warehouse=instance.warehouse,
            movement_type=(
                StockMovement.MOVEMENT_IN if delta > 0 else StockMovement.MOVEMENT_OUT
            ),
            reference_type=StockMovement.REFERENCE_MANUAL,
            reference_id="",
            quantity=abs(delta),
            unit_cost=instance.item.unit_cost,
            notes="Auto-logged stock change",
        )


@receiver(post_save, sender=Stock)
def evaluate_stock_alerts(sender, instance, **kwargs):
    """Generate low-stock and out-of-stock alerts after quantity changes."""
    item = instance.item
    warehouse = instance.warehouse
    on_hand = instance.quantity_on_hand
    reorder = item.reorder_level

    if on_hand <= 0:
        StockAlert.objects.create(
            item=item,
            warehouse=warehouse,
            alert_type=StockAlert.ALERT_OUT_OF_STOCK,
            message=(
                f"{item.name} ({item.code}) is out of stock at {warehouse.name}."
            ),
        )
        _notify_latest_alert(item, warehouse, StockAlert.ALERT_OUT_OF_STOCK)
    elif reorder > 0 and on_hand <= reorder:
        StockAlert.objects.create(
            item=item,
            warehouse=warehouse,
            alert_type=StockAlert.ALERT_LOW_STOCK,
            message=(
                f"{item.name} ({item.code}) is low at {warehouse.name}: "
                f"{on_hand} {item.unit_of_measure} (reorder level: {reorder})."
            ),
        )
        if on_hand <= 0 or (reorder > 0 and on_hand <= reorder * Decimal("0.25")):
            _notify_latest_alert(item, warehouse, StockAlert.ALERT_LOW_STOCK)


def _notify_latest_alert(item, warehouse, alert_type):
    try:
        from apps.inventory.stock_alert_notifications import notify_stock_alert

        alert = (
            StockAlert.objects.filter(
                item=item,
                warehouse=warehouse,
                alert_type=alert_type,
                is_read=False,
            )
            .order_by("-created_at")
            .first()
        )
        if alert:
            notify_stock_alert(alert)
    except Exception:
        pass
