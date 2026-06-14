"""PPE request workflow business logic."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.procurement.models import PurchaseRequisition, PurchaseRequisitionItem
from apps.procurement.services import ProcurementService
from apps.procurement.utils import generate_document_number
from apps.safety.models import PPEIssuance, PPERequest
from apps.safety.utils import generate_ppe_request_number


class PPERequestService:
    WORKFLOW_STEPS = [
        ("safety_officer", "Safety Officer — Anaomba PPE"),
        ("store_keeper", "Store Keeper — Je, PPE zipo?"),
        ("issue_or_procure", "Ndiyo → PPE zinatolewa / Hapana → Procurement"),
        ("procurement", "Procurement"),
        ("supplier", "Supplier"),
        ("store", "Store"),
        ("safety_return", "Safety Officer — PPE zinatolewa"),
    ]

    @staticmethod
    def workflow_index(status, stock_available=None):
        mapping = {
            PPERequest.STATUS_DRAFT: 0,
            PPERequest.STATUS_PENDING_STORE: 1,
            PPERequest.STATUS_AVAILABLE: 2,
            PPERequest.STATUS_IN_PROCUREMENT: 3,
            PPERequest.STATUS_STOCK_RECEIVED: 5,
            PPERequest.STATUS_READY_FOR_ISSUE: 6,
            PPERequest.STATUS_ISSUED: 6,
            PPERequest.STATUS_CANCELLED: 0,
        }
        idx = mapping.get(status, 0)
        if status == PPERequest.STATUS_IN_PROCUREMENT:
            return 3
        return idx

    @staticmethod
    @transaction.atomic
    def submit(request_obj, user):
        if request_obj.status != PPERequest.STATUS_DRAFT:
            raise ValueError("Only draft requests can be submitted")
        request_obj.status = PPERequest.STATUS_PENDING_STORE
        request_obj.submitted_at = timezone.now()
        request_obj.requested_by = user
        request_obj.save()
        return request_obj

    @staticmethod
    @transaction.atomic
    def store_review(request_obj, user, stock_available, notes=""):
        if request_obj.status != PPERequest.STATUS_PENDING_STORE:
            raise ValueError("Request is not pending store review")
        request_obj.store_reviewed_by = user
        request_obj.store_reviewed_at = timezone.now()
        request_obj.store_notes = notes
        request_obj.stock_available = stock_available

        ppe_item = request_obj.ppe_item
        if stock_available:
            if ppe_item.stock_on_hand < request_obj.quantity:
                raise ValueError(
                    f"Insufficient stock. Available: {ppe_item.stock_on_hand}, "
                    f"requested: {request_obj.quantity}"
                )
            request_obj.status = PPERequest.STATUS_AVAILABLE
        else:
            pr = PPERequestService._create_procurement_request(request_obj, user)
            request_obj.purchase_requisition = pr
            request_obj.status = PPERequest.STATUS_IN_PROCUREMENT
            request_obj.procurement_notes = (
                f"Auto-created PR {pr.pr_number} for PPE restock"
            )
        request_obj.save()
        return request_obj

    @staticmethod
    def _create_procurement_request(request_obj, user):
        ppe_item = request_obj.ppe_item
        department = getattr(user, "department", None)
        if not department and request_obj.employee.department_id:
            department = request_obj.employee.department
        if not department:
            from apps.users.models import Department

            department = Department.objects.first()
        if not department:
            raise ValueError("No department available for procurement request")

        pr = PurchaseRequisition.objects.create(
            pr_number=generate_document_number(
                "PR", PurchaseRequisition, "pr_number"
            ),
            department=department,
            priority=PurchaseRequisition.PRIORITY_HIGH
            if request_obj.priority == PPERequest.PRIORITY_URGENT
            else PurchaseRequisition.PRIORITY_MEDIUM,
            status=PurchaseRequisition.STATUS_PENDING,
            notes=(
                f"PPE Request {request_obj.request_number}: "
                f"{ppe_item.name} x{request_obj.quantity}. "
                f"{request_obj.reason}"
            ),
            requested_by=user,
        )
        if ppe_item.inventory_item_id:
            PurchaseRequisitionItem.objects.create(
                requisition=pr,
                item=ppe_item.inventory_item,
                quantity_requested=Decimal(str(request_obj.quantity)),
                unit_cost_estimate=Decimal("0"),
                notes=f"PPE restock — {ppe_item.name}",
            )
            ProcurementService.recalculate_requisition_total(pr)
        elif request_obj.requested_new_item:
            pr.notes = (
                f"{pr.notes}\n\nNew PPE item (not in inventory): "
                f"{ppe_item.get_ppe_type_display()} — {ppe_item.name} "
                f"x{request_obj.quantity}. Add to inventory when received."
            ).strip()
            pr.save(update_fields=["notes", "updated_at"])
        return pr

    @staticmethod
    @transaction.atomic
    def mark_stock_received(request_obj, user, quantity_received=None, notes=""):
        if request_obj.status != PPERequest.STATUS_IN_PROCUREMENT:
            raise ValueError("Request is not in procurement")
        qty = quantity_received or request_obj.quantity
        ppe_item = request_obj.ppe_item
        ppe_item.stock_on_hand += qty
        ppe_item.save(update_fields=["stock_on_hand", "updated_at"])

        request_obj.stock_received_by = user
        request_obj.stock_received_at = timezone.now()
        request_obj.status = PPERequest.STATUS_STOCK_RECEIVED
        if notes:
            request_obj.store_notes = (
                f"{request_obj.store_notes}\n{notes}".strip()
            )
        request_obj.save()
        return request_obj

    @staticmethod
    @transaction.atomic
    def confirm_ready(request_obj, user):
        allowed = (
            PPERequest.STATUS_AVAILABLE,
            PPERequest.STATUS_STOCK_RECEIVED,
        )
        if request_obj.status not in allowed:
            raise ValueError("Request is not ready to confirm")
        if request_obj.ppe_item.stock_on_hand < request_obj.quantity:
            raise ValueError("Insufficient stock to issue")
        request_obj.status = PPERequest.STATUS_READY_FOR_ISSUE
        request_obj.ready_at = timezone.now()
        request_obj.save()
        return request_obj

    @staticmethod
    @transaction.atomic
    def issue(request_obj, user, condition_issued=PPEIssuance.COND_NEW, notes=""):
        if request_obj.status not in (
            PPERequest.STATUS_AVAILABLE,
            PPERequest.STATUS_READY_FOR_ISSUE,
        ):
            raise ValueError("Request is not ready for issuance")
        ppe_item = request_obj.ppe_item
        if ppe_item.stock_on_hand < request_obj.quantity:
            raise ValueError("Insufficient stock")

        issuance = PPEIssuance.objects.create(
            employee=request_obj.employee,
            ppe_item=ppe_item,
            quantity=request_obj.quantity,
            issue_date=timezone.now().date(),
            condition_issued=condition_issued,
            issued_by=user,
            notes=notes or request_obj.reason,
            ppe_request=request_obj,
        )
        ppe_item.stock_on_hand -= request_obj.quantity
        ppe_item.total_issued += request_obj.quantity
        ppe_item.save()

        request_obj.issuance = issuance
        request_obj.issued_at = timezone.now()
        request_obj.status = PPERequest.STATUS_ISSUED
        request_obj.save()
        return request_obj, issuance

    @staticmethod
    @transaction.atomic
    def cancel(request_obj, user, reason=""):
        if request_obj.status == PPERequest.STATUS_ISSUED:
            raise ValueError("Cannot cancel an issued request")
        request_obj.status = PPERequest.STATUS_CANCELLED
        request_obj.cancelled_at = timezone.now()
        request_obj.cancellation_reason = reason
        request_obj.save()
        return request_obj
