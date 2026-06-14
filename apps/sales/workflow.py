"""Enterprise sales order distribution workflow — Rock Solutions FMS."""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.inventory.models import Stock, StockMovement, Warehouse
from apps.inventory.services import InsufficientStockError, StockService
from apps.messaging.models import AppNotification
from apps.procurement.models import PurchaseRequisition, PurchaseRequisitionItem
from apps.procurement.utils import generate_document_number
from apps.sales.models import (
    SalesInvoice,
    SalesInvoiceItem,
    SalesOrder,
    SalesOrderDeliveryCost,
    SalesOrderDispatchAssignment,
    SalesOrderPaymentProof,
    SalesOrderPickupDetail,
)
from apps.core.permissions import user_has_permission
from apps.logistics.services import LogisticsService
from apps.sales.services import SalesService
from apps.sales.utils import generate_document_number as sales_doc_number
from apps.users.models import Permission, User


class SalesOrderWorkflow:
    """Orchestrates the full sales order lifecycle with inventory integration."""

    EDITABLE_STATUSES = {
        SalesOrder.STATUS_NEW_ORDER,
        SalesOrder.STATUS_DRAFT,
        SalesOrder.STATUS_OUT_OF_STOCK,
        SalesOrder.STATUS_QUOTATION_REJECTED,
    }

    # Statuses that belong to the logistics / delivery pipeline
    LOGISTICS_DELIVERY_STATUSES = {
        SalesOrder.STATUS_PENDING_DELIVERY_COST,
        SalesOrder.STATUS_DELIVERY_COST_CALC,
        SalesOrder.STATUS_READY_FOR_PICKUP,
        SalesOrder.STATUS_READY_FOR_DELIVERY,
        SalesOrder.STATUS_VEHICLE_ASSIGNED,
        SalesOrder.STATUS_THIRD_PARTY_ASSIGNED,
        SalesOrder.STATUS_DISPATCHED,
        SalesOrder.STATUS_IN_TRANSIT,
        SalesOrder.STATUS_DELIVERED,
        SalesOrder.STATUS_DELIVERY_CONFIRMED,
        SalesOrder.STATUS_COMPLETED_PICKUP,
        SalesOrder.STATUS_COMPLETED_COMPANY,
        SalesOrder.STATUS_COMPLETED_THIRD_PARTY,
    }

    LOGISTICS_STATUS_LABELS = {
        SalesOrder.STATUS_PENDING_DELIVERY_COST: "Pending Delivery Cost",
        SalesOrder.STATUS_DELIVERY_COST_CALC: "Delivery Cost Calculation",
        SalesOrder.STATUS_READY_FOR_PICKUP: "Ready for Customer Pickup",
        SalesOrder.STATUS_READY_FOR_DELIVERY: "Ready for Delivery",
        SalesOrder.STATUS_VEHICLE_ASSIGNED: "Company Vehicle Assigned",
        SalesOrder.STATUS_THIRD_PARTY_ASSIGNED: "Third Party Transport Assigned",
        SalesOrder.STATUS_DISPATCHED: "Dispatched",
        SalesOrder.STATUS_IN_TRANSIT: "In Transit",
        SalesOrder.STATUS_DELIVERED: "Delivered",
        SalesOrder.STATUS_DELIVERY_CONFIRMED: "Delivery Confirmed",
        SalesOrder.STATUS_COMPLETED_PICKUP: "Completed — Customer Pickup",
        SalesOrder.STATUS_COMPLETED_COMPANY: "Completed — Company Delivery",
        SalesOrder.STATUS_COMPLETED_THIRD_PARTY: "Completed — Third Party Delivery",
    }

    @staticmethod
    def _default_warehouse(order: SalesOrder) -> Warehouse:
        if order.fulfillment_warehouse_id:
            return order.fulfillment_warehouse
        wh = Warehouse.objects.filter(is_active=True).order_by("id").first()
        if not wh:
            raise ValidationError("No active warehouse configured for fulfillment.")
        order.fulfillment_warehouse = wh
        order.save(update_fields=["fulfillment_warehouse", "updated_at"])
        return wh

    @staticmethod
    def _require_logistics(user) -> None:
        if not user_has_permission(user, "logistics", "create"):
            raise ValidationError(
                "This operation is handled by the Logistics department."
            )

    @staticmethod
    def _transition(
        order: SalesOrder,
        new_status: str,
        user,
        action: str,
        details: str = "",
        remarks: str = "",
        *,
        notify_logistics: bool = False,
        logistics_action_required: bool = False,
        skip_logistics_notify: bool = False,
    ):
        previous = order.status
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        SalesService.log_activity(
            order,
            action,
            user,
            details=details,
            previous_status=previous,
            new_status=new_status,
            remarks=remarks,
        )
        if skip_logistics_notify:
            return order
        if notify_logistics or new_status in SalesOrderWorkflow.LOGISTICS_DELIVERY_STATUSES:
            SalesOrderWorkflow._notify_logistics_delivery(
                order,
                action=action,
                details=details,
                action_required=logistics_action_required,
            )
        return order

    @staticmethod
    def _notify_sales(
        title: str,
        body: str,
        order: SalesOrder,
        *,
        notification_type=AppNotification.TYPE_ALERT,
        icon: str = "info",
        color: str = "blue",
    ):
        SalesOrderWorkflow._notify_module_users(
            "sales",
            title,
            body,
            order.id,
            f"/sales/orders/{order.id}/view",
            notification_type=notification_type,
            icon=icon,
            color=color,
        )
        SalesOrderWorkflow._notify_module_users(
            "sales",
            f"[Info] {order.so_number} — {title}",
            body,
            order.id,
            f"/sales/orders/{order.id}/view",
            notification_type=AppNotification.TYPE_SYSTEM,
            icon="info",
            color="gray",
        )

    @staticmethod
    def _notify_module_users(
        module: str,
        title: str,
        body: str,
        reference_id: int,
        navigate_to: str,
        *,
        notification_type=AppNotification.TYPE_ALERT,
        icon: str = "bell",
        color: str = "blue",
    ):
        role_ids = Permission.objects.filter(
            module=module, action="read", is_active=True
        ).values_list("role_id", flat=True)
        users = User.objects.filter(is_active=True, role_id__in=role_ids).distinct()
        for user in users[:50]:
            AppNotification.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                body=body[:250],
                icon=icon,
                color=color,
                reference_type="sales_order",
                reference_id=reference_id,
                navigate_to=navigate_to,
            )

    @staticmethod
    def _delivery_destination(order: SalesOrder) -> str:
        return (
            order.requested_delivery_location
            or order.delivery_address
            or order.customer.address
            or "—"
        )

    @staticmethod
    def _logistics_navigate_url(order: SalesOrder) -> str:
        if order.status in (
            SalesOrder.STATUS_DELIVERY_COST_CALC,
            SalesOrder.STATUS_PENDING_DELIVERY_COST,
        ):
            return "/logistics/sales-queue"
        if order.status in (
            SalesOrder.STATUS_PAYMENT_CONFIRMED,
            SalesOrder.STATUS_READY_FOR_PICKUP,
            SalesOrder.STATUS_READY_FOR_DELIVERY,
            SalesOrder.STATUS_VEHICLE_ASSIGNED,
            SalesOrder.STATUS_THIRD_PARTY_ASSIGNED,
            SalesOrder.STATUS_DISPATCHED,
            SalesOrder.STATUS_IN_TRANSIT,
            SalesOrder.STATUS_DELIVERED,
        ):
            return "/logistics/sales-queue"
        delivery = order.delivery_orders.filter(is_active=True).order_by("-created_at").first()
        if delivery:
            return f"/logistics/deliveries/{delivery.id}/view"
        return f"/sales/orders/{order.id}/view"

    @staticmethod
    def _notify_logistics_delivery(
        order: SalesOrder,
        *,
        action: str,
        details: str = "",
        action_required: bool = False,
        send_info_copy: bool = True,
    ):
        """Notify logistics department about a sales-order delivery event."""
        status_label = SalesOrderWorkflow.LOGISTICS_STATUS_LABELS.get(
            order.status, order.status.replace("_", " ").title()
        )
        destination = SalesOrderWorkflow._delivery_destination(order)
        navigate = SalesOrderWorkflow._logistics_navigate_url(order)

        alert_title = f"[Logistics] {order.so_number} — {action}"
        alert_body = (
            f"{status_label}. Customer: {order.customer.name}. "
            f"Destination: {destination[:120]}. {details}"
        ).strip()

        SalesOrderWorkflow._notify_module_users(
            "logistics",
            alert_title,
            alert_body,
            order.id,
            navigate,
            notification_type=(
                AppNotification.TYPE_ALERT if action_required else AppNotification.TYPE_APPROVAL
            ),
            icon="truck" if action_required else "info",
            color="orange" if action_required else "blue",
        )

        if send_info_copy:
            SalesOrderWorkflow._notify_module_users(
                "logistics",
                f"[Info] {order.so_number} — {status_label}",
                (
                    f"Sales order update: {action}. "
                    f"{details} View delivery details in Logistics."
                ).strip(),
                order.id,
                navigate,
                notification_type=AppNotification.TYPE_SYSTEM,
                icon="info",
                color="gray",
            )

    @staticmethod
    def _ensure_logistics_delivery_order(order: SalesOrder, user) -> None:
        """Create a logistics delivery order record when the SO enters the delivery pipeline."""
        from apps.logistics.models import DeliveryOrder, DeliveryOrderItem

        if order.delivery_orders.filter(is_active=True).exists():
            return

        warehouse = SalesOrderWorkflow._default_warehouse(order)
        scheduled = timezone.now()
        if order.delivery_date:
            naive = datetime.combine(order.delivery_date, datetime.min.time())
            scheduled = (
                timezone.make_aware(naive)
                if timezone.is_naive(naive)
                else naive
            )

        delivery = DeliveryOrder.objects.create(
            do_number=generate_document_number("DO", DeliveryOrder, "do_number"),
            sales_order=order,
            origin_warehouse=warehouse,
            destination=SalesOrderWorkflow._delivery_destination(order),
            customer=order.customer,
            scheduled_date=scheduled,
            distance_km=getattr(
                getattr(order, "delivery_cost_detail", None),
                "delivery_distance_km",
                Decimal("0"),
            ),
            notes=f"Auto-created from sales order {order.so_number}",
            created_by=user,
        )
        for line in order.items.select_related("item"):
            DeliveryOrderItem.objects.create(
                delivery_order=delivery,
                so_item=line,
                item=line.item,
                quantity=line.quantity_ordered,
            )

    @staticmethod
    def _get_logistics_delivery_order(order: SalesOrder):
        from apps.logistics.models import DeliveryOrder

        return order.delivery_orders.filter(is_active=True).order_by("-created_at").first()

    @staticmethod
    def _fleet_for_order(order: SalesOrder):
        delivery = SalesOrderWorkflow._get_logistics_delivery_order(order)
        if delivery:
            vehicle = delivery.vehicle if delivery.vehicle_id else None
            driver = delivery.driver if delivery.driver_id else None
            if vehicle or driver:
                return vehicle, driver
        assignment = getattr(order, "dispatch_assignment", None)
        if assignment:
            return assignment.vehicle, assignment.driver
        return None, None

    @staticmethod
    def _sync_logistics_delivery_status(order: SalesOrder, status: str, **extra) -> None:
        from apps.logistics.models import DeliveryOrder

        delivery = SalesOrderWorkflow._get_logistics_delivery_order(order)
        if not delivery:
            return
        delivery.status = status
        for field, value in extra.items():
            setattr(delivery, field, value)
        delivery.save(update_fields=["status", *extra.keys(), "updated_at"])

        if status == DeliveryOrder.STATUS_IN_TRANSIT:
            vehicle, driver = LogisticsService.resolve_delivery_fleet(delivery)
            LogisticsService.set_fleet_in_transit(vehicle, driver)
        elif status in (
            DeliveryOrder.STATUS_DELIVERED,
            DeliveryOrder.STATUS_FAILED,
            DeliveryOrder.STATUS_CANCELLED,
        ):
            vehicle, driver = LogisticsService.resolve_delivery_fleet(delivery)
            LogisticsService.release_fleet(vehicle, driver)

    @staticmethod
    def ensure_fleet_matches_order(order: SalesOrder) -> None:
        """Keep vehicle/driver status aligned with the sales order dispatch state."""
        from apps.logistics.models import DeliveryOrder

        if order.delivery_method == SalesOrder.METHOD_PICKUP:
            return

        vehicle, driver = SalesOrderWorkflow._fleet_for_order(order)
        if not vehicle and not driver:
            return

        in_transit_statuses = {
            SalesOrder.STATUS_DISPATCHED,
            SalesOrder.STATUS_IN_TRANSIT,
        }
        released_statuses = {
            SalesOrder.STATUS_DELIVERED,
            SalesOrder.STATUS_DELIVERY_CONFIRMED,
            SalesOrder.STATUS_COMPLETED_PICKUP,
            SalesOrder.STATUS_COMPLETED_COMPANY,
            SalesOrder.STATUS_COMPLETED_THIRD_PARTY,
            SalesOrder.STATUS_CANCELLED,
        }

        if order.status in in_transit_statuses:
            LogisticsService.set_fleet_in_transit(vehicle, driver)
            delivery = SalesOrderWorkflow._get_logistics_delivery_order(order)
            if delivery and delivery.status == DeliveryOrder.STATUS_SCHEDULED:
                delivery.status = DeliveryOrder.STATUS_IN_TRANSIT
                if not delivery.actual_departure:
                    delivery.actual_departure = timezone.now()
                if vehicle and not delivery.vehicle_id:
                    delivery.vehicle = vehicle
                if driver and not delivery.driver_id:
                    delivery.driver = driver
                delivery.save(
                    update_fields=[
                        "status",
                        "actual_departure",
                        "vehicle",
                        "driver",
                        "updated_at",
                    ]
                )
        elif order.status in released_statuses:
            LogisticsService.release_fleet(vehicle, driver)

    @staticmethod
    def stock_check(order: SalesOrder) -> dict:
        warehouse = SalesOrderWorkflow._default_warehouse(order)
        lines = []
        all_available = True
        for line in order.items.select_related("item"):
            stock = Stock.objects.filter(item=line.item, warehouse=warehouse).first()
            on_hand = stock.quantity_on_hand if stock else Decimal("0")
            reserved = stock.quantity_reserved if stock else Decimal("0")
            available = stock.quantity_available if stock else Decimal("0")
            shortfall = max(line.quantity_ordered - available, Decimal("0"))
            if shortfall > 0:
                all_available = False
            lines.append(
                {
                    "item_id": line.item_id,
                    "item_code": line.item.code,
                    "item_name": line.item.name,
                    "quantity_ordered": str(line.quantity_ordered),
                    "quantity_on_hand": str(on_hand),
                    "quantity_reserved": str(reserved),
                    "quantity_available": str(available),
                    "shortfall": str(shortfall),
                    "sufficient": shortfall <= 0,
                }
            )
        return {
            "warehouse_id": warehouse.id,
            "warehouse_name": warehouse.name,
            "all_available": all_available,
            "lines": lines,
        }

    @staticmethod
    @transaction.atomic
    def submit_order(order: SalesOrder, user) -> SalesOrder:
        if order.status not in (SalesOrder.STATUS_NEW_ORDER, SalesOrder.STATUS_DRAFT):
            raise ValidationError("Only new orders can be submitted.")
        if not order.items.exists():
            raise ValidationError("Add at least one line item before submitting.")
        if not order.requested_delivery_location and not order.delivery_address:
            order.requested_delivery_location = order.customer.address
            order.delivery_address = order.customer.address
            order.save(update_fields=["requested_delivery_location", "delivery_address", "updated_at"])
        SalesOrderWorkflow._transition(order, SalesOrder.STATUS_STOCK_VERIFICATION, user, "Order Submitted")
        SalesOrderWorkflow._notify_module_users(
            "sales",
            f"New order {order.so_number}",
            f"Customer {order.customer.name} submitted order for review.",
            order.id,
            f"/sales/orders/{order.id}/view",
        )
        return SalesOrderWorkflow.verify_stock(order, user)

    @staticmethod
    @transaction.atomic
    def verify_stock(order: SalesOrder, user, partial: bool = False) -> dict:
        if order.status not in (
            SalesOrder.STATUS_STOCK_VERIFICATION,
            SalesOrder.STATUS_OUT_OF_STOCK,
        ):
            raise ValidationError("Order is not in stock verification stage.")

        check = SalesOrderWorkflow.stock_check(order)
        warehouse = Warehouse.objects.get(pk=check["warehouse_id"])

        if check["all_available"]:
            line_map = {row["item_id"]: row for row in check["lines"]}
            for line in order.items.select_related("item"):
                qty = line.quantity_ordered
                StockService.reserve_stock(item=line.item, warehouse=warehouse, quantity=qty)
                line.quantity_reserved = qty
                snapshot = line_map.get(line.item_id, {})
                line.stock_available_snapshot = Decimal(
                    snapshot.get("quantity_available", qty)
                )
                line.save(update_fields=["quantity_reserved", "stock_available_snapshot"])
            order.inventory_status = SalesOrder.INV_RESERVED
            SalesOrderWorkflow._transition(
                order,
                SalesOrder.STATUS_PENDING_DELIVERY_COST,
                user,
                "Stock Verified & Reserved",
                details="All items reserved in inventory.",
                skip_logistics_notify=True,
            )
            return {"result": "RESERVED", "stock_check": check}

        if partial:
            for line in order.items.select_related("item"):
                stock = Stock.objects.filter(item=line.item, warehouse=warehouse).first()
                available = stock.quantity_available if stock else Decimal("0")
                reserve_qty = min(line.quantity_ordered, available)
                if reserve_qty > 0:
                    StockService.reserve_stock(item=line.item, warehouse=warehouse, quantity=reserve_qty)
                    line.quantity_reserved = reserve_qty
                    line.save(update_fields=["quantity_reserved"])
            order.inventory_status = SalesOrder.INV_RESERVED
            SalesOrderWorkflow._transition(
                order,
                SalesOrder.STATUS_PENDING_DELIVERY_COST,
                user,
                "Partial Stock Reserved",
                details="Partial fulfillment — available stock reserved.",
                skip_logistics_notify=True,
            )
            return {"result": "PARTIAL_RESERVED", "stock_check": check}

        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_OUT_OF_STOCK,
            user,
            "Insufficient Stock",
            details="One or more items are out of stock.",
        )
        return {"result": "OUT_OF_STOCK", "stock_check": check}

    @staticmethod
    @transaction.atomic
    def create_procurement_request(order: SalesOrder, user, department_id: int | None = None) -> PurchaseRequisition:
        if order.status != SalesOrder.STATUS_OUT_OF_STOCK:
            raise ValidationError("Procurement request only available for out-of-stock orders.")
        from apps.users.models import Department

        dept = Department.objects.filter(pk=department_id).first() if department_id else None
        if not dept:
            dept = Department.objects.filter(name__icontains="procurement").first()
        if not dept:
            dept = Department.objects.first()
        if not dept:
            raise ValidationError("No department configured for procurement requests.")

        pr = PurchaseRequisition.objects.create(
            pr_number=generate_document_number("PR", PurchaseRequisition, "pr_number"),
            department=dept,
            priority=PurchaseRequisition.PRIORITY_HIGH,
            status=PurchaseRequisition.STATUS_PENDING,
            notes=f"Auto-generated from sales order {order.so_number}",
            requested_by=user,
        )
        check = SalesOrderWorkflow.stock_check(order)
        warehouse = Warehouse.objects.get(pk=check["warehouse_id"])
        for line in order.items.select_related("item"):
            stock = Stock.objects.filter(item=line.item, warehouse=warehouse).first()
            available = stock.quantity_available if stock else Decimal("0")
            shortfall = max(line.quantity_ordered - available, Decimal("0"))
            if shortfall > 0:
                PurchaseRequisitionItem.objects.create(
                    requisition=pr,
                    item=line.item,
                    quantity_requested=shortfall,
                    unit_cost_estimate=line.unit_price,
                    notes=f"SO {order.so_number}",
                )
        order.linked_pr = pr
        order.save(update_fields=["linked_pr", "updated_at"])
        SalesOrderWorkflow._transition(
            order,
            order.status,
            user,
            "Procurement Request Created",
            details=pr.pr_number,
        )
        return pr

    @staticmethod
    @transaction.atomic
    def send_to_logistics_for_delivery_cost(order: SalesOrder, user) -> SalesOrder:
        if order.status != SalesOrder.STATUS_PENDING_DELIVERY_COST:
            raise ValidationError(
                "Order must be pending delivery cost before sending to Logistics."
            )
        SalesOrderWorkflow._ensure_logistics_delivery_order(order, user)
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_DELIVERY_COST_CALC,
            user,
            "Sent to Logistics for Delivery Cost",
            details="Sales requested delivery cost calculation.",
            logistics_action_required=True,
        )
        return order

    @staticmethod
    @transaction.atomic
    def calculate_delivery_cost(order: SalesOrder, user, cost_data: dict) -> SalesOrder:
        SalesOrderWorkflow._require_logistics(user)
        if order.status != SalesOrder.STATUS_DELIVERY_COST_CALC:
            raise ValidationError(
                "Order must be sent to Logistics before delivery cost can be calculated."
            )

        detail, _ = SalesOrderDeliveryCost.objects.get_or_create(sales_order=order)
        for field in (
            "delivery_distance_km",
            "transport_method",
            "vehicle_type",
            "fuel_cost",
            "loading_cost",
            "offloading_cost",
            "additional_charges",
            "notes",
        ):
            if field in cost_data:
                setattr(detail, field, cost_data[field])
        detail.calculated_by = user
        detail.recalculate_total()
        detail.save()
        order.delivery_cost = detail.total_delivery_cost
        order.save(update_fields=["delivery_cost", "updated_at"])
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_QUOTATION_PREP,
            user,
            "Delivery Cost Calculated",
            details=f"Total delivery cost: {detail.total_delivery_cost}",
            skip_logistics_notify=True,
        )
        SalesOrderWorkflow._notify_sales(
            f"{order.so_number} — Delivery Cost Ready",
            (
                f"Logistics calculated delivery cost: {detail.total_delivery_cost} TZS. "
                f"Distance: {detail.delivery_distance_km} km. "
                "You can now send the quotation to the customer."
            ),
            order,
            notification_type=AppNotification.TYPE_ALERT,
            icon="check-circle",
            color="green",
        )
        return order

    @staticmethod
    @transaction.atomic
    def send_quotation(order: SalesOrder, user) -> SalesOrder:
        if order.status not in (
            SalesOrder.STATUS_QUOTATION_PREP,
            SalesOrder.STATUS_QUOTATION_SENT,
            SalesOrder.STATUS_WAITING_CUSTOMER,
        ):
            raise ValidationError("Order is not in quotation preparation stage.")
        SalesService.recalculate_order(order)
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_QUOTATION_SENT,
            user,
            "Quotation Sent",
            details=f"Product: {order.subtotal}, Delivery: {order.delivery_cost}, Total: {order.total_amount + order.delivery_cost}",
        )
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_WAITING_CUSTOMER,
            user,
            "Awaiting Customer Response",
        )
        return order

    @staticmethod
    @transaction.atomic
    def accept_quotation(order: SalesOrder, user) -> SalesOrder:
        if order.status not in (
            SalesOrder.STATUS_QUOTATION_SENT,
            SalesOrder.STATUS_WAITING_CUSTOMER,
        ):
            raise ValidationError("Quotation has not been sent to customer.")
        SalesOrderWorkflow._transition(order, SalesOrder.STATUS_QUOTATION_ACCEPTED, user, "Quotation Accepted")
        return order

    @staticmethod
    @transaction.atomic
    def reject_quotation(order: SalesOrder, user, reason: str = "") -> SalesOrder:
        if order.status not in (
            SalesOrder.STATUS_QUOTATION_SENT,
            SalesOrder.STATUS_WAITING_CUSTOMER,
        ):
            raise ValidationError("Quotation has not been sent to customer.")
        SalesOrderWorkflow.release_reservations(order)
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_QUOTATION_REJECTED,
            user,
            "Quotation Rejected",
            remarks=reason,
        )
        return order

    @staticmethod
    @transaction.atomic
    def generate_invoice(order: SalesOrder, user) -> SalesInvoice:
        if order.status != SalesOrder.STATUS_QUOTATION_ACCEPTED:
            raise ValidationError("Quotation must be accepted before invoicing.")
        existing = SalesInvoice.objects.filter(
            sales_order=order, is_active=True
        ).first()
        if existing:
            SalesService.sync_order_invoices(order)
            return existing

        due = timezone.now().date() + timedelta(days=30)
        invoice = SalesInvoice.objects.create(
            invoice_number=sales_doc_number("INV", SalesInvoice, "invoice_number"),
            sales_order=order,
            customer=order.customer,
            currency=order.currency,
            exchange_rate=order.exchange_rate,
            due_date=due,
            delivery_cost=order.delivery_cost or Decimal("0"),
            status=SalesInvoice.STATUS_SENT,
            created_by=user,
        )
        for line in order.items.select_related("item"):
            SalesInvoiceItem.objects.create(
                invoice=invoice,
                item=line.item,
                quantity=line.quantity_ordered,
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
            )
        SalesService.recalculate_invoice(invoice)
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_INVOICE_GENERATED,
            user,
            "Invoice Generated",
            details=invoice.invoice_number,
        )
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_AWAITING_PAYMENT,
            user,
            "Awaiting Payment",
        )
        return invoice

    @staticmethod
    @transaction.atomic
    def submit_payment_proof(order: SalesOrder, user, proof_data: dict) -> SalesOrderPaymentProof:
        if order.status != SalesOrder.STATUS_AWAITING_PAYMENT:
            raise ValidationError("Order is not awaiting payment.")
        proof = SalesOrderPaymentProof.objects.create(
            sales_order=order,
            amount=proof_data["amount"],
            payment_method=proof_data["payment_method"],
            reference_number=proof_data["reference_number"],
            proof_notes=proof_data.get("proof_notes", ""),
            submitted_by=user,
        )
        SalesOrderWorkflow._transition(
            order,
            order.status,
            user,
            "Payment Submitted",
            details=f"Ref: {proof.reference_number}, Amount: {proof.amount}",
        )
        SalesOrderWorkflow._notify_module_users(
            "finance",
            f"Payment proof for {order.so_number}",
            f"Amount {proof.amount} — verify payment reference {proof.reference_number}.",
            order.id,
            f"/sales/orders/{order.id}/view",
        )
        return proof

    @staticmethod
    @transaction.atomic
    def verify_payment(
        order: SalesOrder,
        user,
        proof_id: int | None,
        approved: bool,
        reason: str = "",
    ) -> SalesOrder:
        if order.status != SalesOrder.STATUS_AWAITING_PAYMENT:
            raise ValidationError("Order is not awaiting payment verification.")
        proof = None
        if proof_id:
            proof = SalesOrderPaymentProof.objects.filter(
                pk=proof_id, sales_order=order
            ).first()
        if not proof:
            proof = (
                SalesOrderPaymentProof.objects.filter(
                    sales_order=order,
                    status=SalesOrderPaymentProof.STATUS_PENDING,
                    is_active=True,
                )
                .order_by("-created_at")
                .first()
            )
        if not proof:
            raise ValidationError(
                "No pending payment proof found. Submit payment proof first."
            )

        if approved:
            proof.status = SalesOrderPaymentProof.STATUS_VERIFIED
            proof.verified_by = user
            proof.verified_at = timezone.now()
            proof.save()
            order.inventory_status = SalesOrder.INV_LOCKED
            order.payment_status = SalesOrder.PAYMENT_PAID
            order.save(update_fields=["inventory_status", "payment_status", "updated_at"])
            SalesService.sync_order_invoices(order)
            SalesOrderWorkflow._transition(
                order,
                SalesOrder.STATUS_PAYMENT_CONFIRMED,
                user,
                "Payment Verified",
                details=f"Reference {proof.reference_number} confirmed.",
            )
            SalesOrderWorkflow._notify_logistics_delivery(
                order,
                action="Payment Confirmed — Plan Delivery",
                details="Customer payment verified. Set delivery method and schedule dispatch.",
                action_required=True,
            )
        else:
            proof.status = SalesOrderPaymentProof.STATUS_FAILED
            proof.failure_reason = reason
            proof.verified_by = user
            proof.verified_at = timezone.now()
            proof.save()
            SalesOrderWorkflow._transition(
                order,
                SalesOrder.STATUS_PAYMENT_FAILED,
                user,
                "Payment Verification Failed",
                remarks=reason,
            )
        return order

    @staticmethod
    @transaction.atomic
    def set_delivery_method(order: SalesOrder, user, method: str) -> SalesOrder:
        SalesOrderWorkflow._require_logistics(user)
        if order.status != SalesOrder.STATUS_PAYMENT_CONFIRMED:
            raise ValidationError("Payment must be confirmed before selecting delivery method.")
        if method not in (
            SalesOrder.METHOD_PICKUP,
            SalesOrder.METHOD_COMPANY,
            SalesOrder.METHOD_THIRD_PARTY,
        ):
            raise ValidationError("Invalid delivery method.")
        order.delivery_method = method
        order.save(update_fields=["delivery_method", "updated_at"])
        new_status = (
            SalesOrder.STATUS_READY_FOR_PICKUP
            if method == SalesOrder.METHOD_PICKUP
            else SalesOrder.STATUS_READY_FOR_DELIVERY
        )
        SalesOrderWorkflow._transition(
            order,
            new_status,
            user,
            "Delivery Method Set",
            details=method,
            logistics_action_required=True,
        )
        SalesOrderWorkflow._ensure_logistics_delivery_order(order, user)
        delivery = SalesOrderWorkflow._get_logistics_delivery_order(order)
        if delivery and order.delivery_cost:
            delivery.distance_km = getattr(
                getattr(order, "delivery_cost_detail", None),
                "delivery_distance_km",
                delivery.distance_km,
            )
            delivery.save(update_fields=["distance_km", "updated_at"])
        return order

    @staticmethod
    @transaction.atomic
    def assign_vehicle(order: SalesOrder, user, assignment_data: dict) -> SalesOrder:
        SalesOrderWorkflow._require_logistics(user)
        if order.status != SalesOrder.STATUS_READY_FOR_DELIVERY:
            raise ValidationError("Order must be ready for delivery.")
        from apps.logistics.models import DeliveryOrder, Driver, Vehicle

        vehicle = Vehicle.objects.get(pk=assignment_data["vehicle_id"])
        driver = Driver.objects.get(pk=assignment_data["driver_id"])

        if vehicle.status != Vehicle.STATUS_AVAILABLE:
            raise ValidationError(
                f"Vehicle {vehicle.registration_number} is not available "
                f"(current status: {vehicle.get_status_display()})."
            )
        if not driver.is_available:
            raise ValidationError(f"Driver {driver} is not available for assignment.")
        if DeliveryOrder.objects.filter(
            driver=driver,
            status=DeliveryOrder.STATUS_IN_TRANSIT,
            is_active=True,
        ).exists():
            raise ValidationError(f"Driver {driver} is already on an active trip.")
        if DeliveryOrder.objects.filter(
            vehicle=vehicle,
            status=DeliveryOrder.STATUS_IN_TRANSIT,
            is_active=True,
        ).exists():
            raise ValidationError(
                f"Vehicle {vehicle.registration_number} is already on an active trip."
            )

        assignment, _ = SalesOrderDispatchAssignment.objects.get_or_create(sales_order=order)
        assignment.assignment_type = SalesOrder.METHOD_COMPANY
        assignment.vehicle = vehicle
        assignment.driver = driver
        assignment.driver_phone = assignment_data.get("driver_phone", driver.user.phone if hasattr(driver.user, "phone") else "")
        assignment.dispatch_date = assignment_data.get("dispatch_date") or timezone.now().date()
        assignment.assigned_by = user
        assignment.save()
        SalesOrderWorkflow._ensure_logistics_delivery_order(order, user)
        delivery = SalesOrderWorkflow._get_logistics_delivery_order(order)
        if delivery:
            delivery.vehicle = vehicle
            delivery.driver = driver
            delivery.save(update_fields=["vehicle", "driver", "updated_at"])
            from apps.logistics.driver_portal_service import DriverPortalService

            DriverPortalService.ensure_assigned(delivery)
            driver.assigned_vehicle = vehicle
            driver.save(update_fields=["assigned_vehicle", "updated_at"])
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_VEHICLE_ASSIGNED,
            user,
            "Vehicle Assigned",
            details=f"{vehicle.registration_number} / {driver}",
            logistics_action_required=True,
        )
        return order

    @staticmethod
    @transaction.atomic
    def assign_third_party(order: SalesOrder, user, assignment_data: dict) -> SalesOrder:
        SalesOrderWorkflow._require_logistics(user)
        if order.status != SalesOrder.STATUS_READY_FOR_DELIVERY:
            raise ValidationError("Order must be ready for delivery.")
        assignment, _ = SalesOrderDispatchAssignment.objects.get_or_create(sales_order=order)
        assignment.assignment_type = SalesOrder.METHOD_THIRD_PARTY
        assignment.transport_company = assignment_data["transport_company"]
        assignment.tracking_number = assignment_data.get("tracking_number", "")
        assignment.contact_person = assignment_data.get("contact_person", "")
        assignment.contact_phone = assignment_data.get("contact_phone", "")
        assignment.dispatch_date = assignment_data.get("dispatch_date") or timezone.now().date()
        assignment.assigned_by = user
        assignment.save()
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_THIRD_PARTY_ASSIGNED,
            user,
            "Third Party Assigned",
            details=assignment.transport_company,
            logistics_action_required=True,
        )
        return order

    @staticmethod
    @transaction.atomic
    def dispatch_order(order: SalesOrder, user) -> SalesOrder:
        SalesOrderWorkflow._require_logistics(user)
        allowed = (
            SalesOrder.STATUS_READY_FOR_PICKUP,
            SalesOrder.STATUS_VEHICLE_ASSIGNED,
            SalesOrder.STATUS_THIRD_PARTY_ASSIGNED,
            SalesOrder.STATUS_READY_FOR_DELIVERY,
        )
        if order.status not in allowed:
            raise ValidationError("Order is not ready for dispatch.")
        warehouse = SalesOrderWorkflow._default_warehouse(order)
        for line in order.items.select_related("item"):
            qty = line.quantity_reserved or line.quantity_ordered
            if qty <= 0:
                continue
            try:
                StockService.commit_reservation_out(
                    item=line.item,
                    warehouse=warehouse,
                    quantity=qty,
                    reference_type=StockMovement.REFERENCE_SALES_ORDER,
                    reference_id=order.so_number,
                    unit_cost=line.unit_price,
                    notes=f"Dispatch for {order.so_number}",
                    created_by=user,
                )
            except InsufficientStockError:
                StockService.apply_quantity_change(
                    item=line.item,
                    warehouse=warehouse,
                    delta=-qty,
                    movement_type=StockMovement.MOVEMENT_OUT,
                    reference_type=StockMovement.REFERENCE_SALES_ORDER,
                    reference_id=order.so_number,
                    unit_cost=line.unit_price,
                    created_by=user,
                )
            line.quantity_reserved = Decimal("0")
            line.save(update_fields=["quantity_reserved"])
        order.inventory_status = SalesOrder.INV_RELEASED
        order.delivery_status = SalesOrder.DELIVERY_PROCESSING
        order.save(update_fields=["inventory_status", "delivery_status", "updated_at"])
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_DISPATCHED,
            user,
            "Dispatched",
            details="Stock released",
            logistics_action_required=True,
        )
        delivery = SalesOrderWorkflow._get_logistics_delivery_order(order)
        if order.delivery_method != SalesOrder.METHOD_PICKUP:
            if delivery:
                LogisticsService.start_trip(delivery)
            else:
                vehicle, driver = SalesOrderWorkflow._fleet_for_order(order)
                LogisticsService.set_fleet_in_transit(vehicle, driver)
            SalesOrderWorkflow.ensure_fleet_matches_order(order)
            SalesOrderWorkflow._transition(order, SalesOrder.STATUS_IN_TRANSIT, user, "In Transit")
        return order

    @staticmethod
    @transaction.atomic
    def confirm_pickup(order: SalesOrder, user, pickup_data: dict) -> SalesOrder:
        SalesOrderWorkflow._require_logistics(user)
        if order.status not in (
            SalesOrder.STATUS_READY_FOR_PICKUP,
            SalesOrder.STATUS_DISPATCHED,
        ):
            raise ValidationError("Order is not ready for customer pickup.")
        if order.status == SalesOrder.STATUS_READY_FOR_PICKUP:
            SalesOrderWorkflow.dispatch_order(order, user)
        SalesOrderPickupDetail.objects.update_or_create(
            sales_order=order,
            defaults={
                "pickup_date": pickup_data["pickup_date"],
                "receiver_name": pickup_data["receiver_name"],
                "receiver_phone": pickup_data["receiver_phone"],
                "signature_data": pickup_data.get("signature_data", ""),
                "notes": pickup_data.get("notes", ""),
                "recorded_by": user,
            },
        )
        for line in order.items.all():
            line.quantity_delivered = line.quantity_ordered
            line.save(update_fields=["quantity_delivered"])
        order.delivery_status = SalesOrder.DELIVERY_DELIVERED
        order.save(update_fields=["delivery_status", "updated_at"])
        SalesOrderWorkflow._transition(order, SalesOrder.STATUS_COMPLETED_PICKUP, user, "Customer Pickup Completed")
        SalesOrderWorkflow._sync_logistics_delivery_status(
            order,
            "DELIVERED",
            actual_arrival=timezone.now(),
        )
        return order

    @staticmethod
    @transaction.atomic
    def confirm_delivery(order: SalesOrder, user, delivery_data: dict) -> SalesOrder:
        SalesOrderWorkflow._require_logistics(user)
        if order.status not in (SalesOrder.STATUS_IN_TRANSIT, SalesOrder.STATUS_DISPATCHED):
            raise ValidationError("Order is not in transit.")
        for line in order.items.all():
            line.quantity_delivered = line.quantity_ordered
            line.save(update_fields=["quantity_delivered"])
        order.delivery_status = SalesOrder.DELIVERY_DELIVERED
        order.save(update_fields=["delivery_status", "updated_at"])
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_DELIVERED,
            user,
            "Delivered",
            details=delivery_data.get("notes", ""),
            remarks=f"Receiver: {delivery_data.get('receiver_name', '')}",
            logistics_action_required=True,
        )
        SalesOrderWorkflow._sync_logistics_delivery_status(
            order,
            "DELIVERED",
            actual_arrival=timezone.now(),
        )
        return order

    @staticmethod
    @transaction.atomic
    def logistics_confirm(order: SalesOrder, user, remarks: str = "") -> SalesOrder:
        SalesOrderWorkflow._require_logistics(user)
        if order.status != SalesOrder.STATUS_DELIVERED:
            raise ValidationError("Delivery must be completed first.")
        SalesOrderWorkflow._transition(
            order,
            SalesOrder.STATUS_DELIVERY_CONFIRMED,
            user,
            "Logistics Confirmed",
            remarks=remarks,
            logistics_action_required=True,
        )
        return order

    @staticmethod
    @transaction.atomic
    def close_order(order: SalesOrder, user) -> SalesOrder:
        if order.status not in (
            SalesOrder.STATUS_DELIVERY_CONFIRMED,
            SalesOrder.STATUS_COMPLETED_PICKUP,
        ):
            raise ValidationError("Order must be delivery-confirmed before closure.")
        if order.delivery_method == SalesOrder.METHOD_THIRD_PARTY:
            final = SalesOrder.STATUS_COMPLETED_THIRD_PARTY
        elif order.delivery_method == SalesOrder.METHOD_PICKUP:
            final = SalesOrder.STATUS_COMPLETED_PICKUP
        else:
            final = SalesOrder.STATUS_COMPLETED_COMPANY
        SalesOrderWorkflow._transition(order, final, user, "Order Closed")
        SalesService.sync_order_invoices(order)
        return order

    @staticmethod
    @transaction.atomic
    def release_reservations(order: SalesOrder):
        if order.inventory_status not in (SalesOrder.INV_RESERVED, SalesOrder.INV_LOCKED):
            return
        warehouse = SalesOrderWorkflow._default_warehouse(order)
        for line in order.items.select_related("item"):
            if line.quantity_reserved > 0:
                StockService.release_reservation(
                    item=line.item,
                    warehouse=warehouse,
                    quantity=line.quantity_reserved,
                )
                line.quantity_reserved = Decimal("0")
                line.save(update_fields=["quantity_reserved"])
        order.inventory_status = SalesOrder.INV_RELEASED
        order.save(update_fields=["inventory_status", "updated_at"])

    @staticmethod
    @transaction.atomic
    def cancel_order(order: SalesOrder, user, reason: str) -> SalesOrder:
        if order.status in (
            SalesOrder.STATUS_COMPLETED_PICKUP,
            SalesOrder.STATUS_COMPLETED_COMPANY,
            SalesOrder.STATUS_COMPLETED_THIRD_PARTY,
            SalesOrder.STATUS_CANCELLED,
        ):
            raise ValidationError("This order cannot be cancelled.")
        SalesOrderWorkflow.release_reservations(order)
        order.delivery_status = SalesOrder.DELIVERY_CANCELLED
        order.cancel_reason = reason
        order.save(update_fields=["delivery_status", "cancel_reason", "updated_at"])
        SalesOrderWorkflow._transition(order, SalesOrder.STATUS_CANCELLED, user, "Cancelled", remarks=reason)
        return order
