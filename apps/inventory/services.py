"""
Stock management service — single entry point for quantity changes.

All stock mutations go through this service to enforce non-negative stock
and attach movement metadata for audit signals.
"""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.inventory.models import (
    Stock,
    StockAdjustment,
    StockMovement,
)


class InsufficientStockError(ValidationError):
    """Raised when an OUT movement would drive quantity below zero."""


class StockService:
    """Apply stock quantity changes with validation and movement metadata."""

    @staticmethod
    def get_or_create_stock(item, warehouse) -> Stock:
        stock, _ = Stock.objects.get_or_create(
            item=item,
            warehouse=warehouse,
            defaults={
                "quantity_on_hand": Decimal("0"),
                "quantity_reserved": Decimal("0"),
                "quantity_available": Decimal("0"),
            },
        )
        return stock

    @staticmethod
    @transaction.atomic
    def apply_quantity_change(
        *,
        item,
        warehouse,
        delta: Decimal,
        movement_type: str,
        reference_type: str,
        reference_id: str = "",
        unit_cost=None,
        serial_number: str = "",
        expiry_date=None,
        notes: str = "",
        created_by=None,
    ) -> Stock:
        """
        Change stock on-hand by delta (positive = IN, negative = OUT).

        Attaches _movement_meta on the Stock instance so post_save signal
        creates the corresponding StockMovement record.
        """
        if delta == 0:
            raise ValidationError("Quantity change cannot be zero.")

        if not item.tracks_stock:
            raise ValidationError(
                f"Item {item.code} is a non-stock service and cannot affect inventory quantities."
            )

        stock = StockService.get_or_create_stock(item, warehouse)
        new_on_hand = stock.quantity_on_hand + delta

        if new_on_hand < 0:
            raise InsufficientStockError(
                f"Insufficient stock for {item.code} at {warehouse.name}. "
                f"Available: {stock.quantity_available}, requested: {abs(delta)}."
            )

        resolved_movement_type = movement_type
        if movement_type == StockMovement.MOVEMENT_ADJUSTMENT:
            resolved_movement_type = (
                StockMovement.MOVEMENT_IN if delta > 0 else StockMovement.MOVEMENT_OUT
            )

        stock._movement_meta = {
            "movement_type": resolved_movement_type,
            "reference_type": reference_type,
            "reference_id": str(reference_id),
            "quantity": abs(delta),
            "unit_cost": unit_cost if unit_cost is not None else item.unit_cost,
            "serial_number": serial_number,
            "expiry_date": expiry_date,
            "notes": notes,
            "created_by": created_by,
        }
        stock.quantity_on_hand = new_on_hand
        stock.save()
        return stock

    @staticmethod
    @transaction.atomic
    def record_movement(
        *,
        item,
        warehouse,
        movement_type: str,
        quantity: Decimal,
        reference_type: str,
        reference_id: str = "",
        unit_cost=None,
        serial_number: str = "",
        expiry_date=None,
        notes: str = "",
        created_by=None,
    ) -> tuple[Stock, StockMovement]:
        """
        Record an explicit stock movement and apply the quantity change.

        Returns the updated stock and the auto-created movement (via signal).
        """
        if quantity <= 0:
            raise ValidationError("Movement quantity must be greater than zero.")

        if movement_type in (StockMovement.MOVEMENT_OUT,):
            delta = -quantity
        elif movement_type in (StockMovement.MOVEMENT_IN,):
            delta = quantity
        elif movement_type == StockMovement.MOVEMENT_ADJUSTMENT:
            delta = quantity
        else:
            delta = quantity

        stock = StockService.apply_quantity_change(
            item=item,
            warehouse=warehouse,
            delta=delta,
            movement_type=movement_type,
            reference_type=reference_type,
            reference_id=reference_id,
            unit_cost=unit_cost,
            serial_number=serial_number,
            expiry_date=expiry_date,
            notes=notes,
            created_by=created_by,
        )
        movement = getattr(stock, "_last_movement", None)
        return stock, movement

    @staticmethod
    @transaction.atomic
    def reserve_stock(*, item, warehouse, quantity: Decimal) -> Stock:
        """Reserve stock for a sales order (reduces quantity_available)."""
        if quantity <= 0:
            raise ValidationError("Reservation quantity must be greater than zero.")
        if not item.tracks_stock:
            return StockService.get_or_create_stock(item, warehouse)

        stock = StockService.get_or_create_stock(item, warehouse)
        if stock.quantity_available < quantity:
            raise InsufficientStockError(
                f"Insufficient available stock for {item.code}. "
                f"Available: {stock.quantity_available}, requested: {quantity}."
            )
        stock.quantity_reserved += quantity
        stock.save()
        return stock

    @staticmethod
    @transaction.atomic
    def release_reservation(*, item, warehouse, quantity: Decimal) -> Stock:
        """Release previously reserved stock back to available pool."""
        if quantity <= 0:
            return StockService.get_or_create_stock(item, warehouse)
        stock = StockService.get_or_create_stock(item, warehouse)
        stock.quantity_reserved = max(stock.quantity_reserved - quantity, Decimal("0"))
        stock.save()
        return stock

    @staticmethod
    @transaction.atomic
    def commit_reservation_out(
        *,
        item,
        warehouse,
        quantity: Decimal,
        reference_type: str,
        reference_id: str,
        unit_cost=None,
        notes: str = "",
        created_by=None,
    ) -> Stock:
        """Release reservation and create stock OUT movement (dispatch)."""
        if quantity <= 0:
            raise ValidationError("Dispatch quantity must be greater than zero.")
        StockService.release_reservation(item=item, warehouse=warehouse, quantity=quantity)
        return StockService.apply_quantity_change(
            item=item,
            warehouse=warehouse,
            delta=-quantity,
            movement_type=StockMovement.MOVEMENT_OUT,
            reference_type=reference_type,
            reference_id=reference_id,
            unit_cost=unit_cost,
            notes=notes,
            created_by=created_by,
        )

    @staticmethod
    @transaction.atomic
    def apply_adjustment(adjustment: StockAdjustment, approved_by) -> Stock:
        """Apply an approved stock adjustment to inventory."""
        if adjustment.status != StockAdjustment.STATUS_APPROVED:
            raise ValidationError("Only approved adjustments can be applied.")

        delta = adjustment.quantity
        if adjustment.adjustment_type == StockAdjustment.ADJUSTMENT_DECREASE:
            delta = -delta

        return StockService.apply_quantity_change(
            item=adjustment.item,
            warehouse=adjustment.warehouse,
            delta=delta,
            movement_type=StockMovement.MOVEMENT_ADJUSTMENT,
            reference_type=StockMovement.REFERENCE_ADJUSTMENT,
            reference_id=adjustment.pk,
            notes=adjustment.reason,
            created_by=approved_by,
        )
