"""Storekeeper production receipt queue — finished goods after production approval."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions import HasModulePermission, user_has_permission
from apps.core.responses import api_error, api_response
from apps.production.execution_service import ProductionExecutionService
from apps.production.models import WorkOrder
from apps.production.production_permissions import can_receive_finished_goods
from apps.production.serializers import StoreReceiptSerializer


def _serialize_receipt_row(wo: WorkOrder) -> dict:
    receipt = getattr(wo, "finished_goods_receipt", None)
    return {
        "id": wo.id,
        "wo_number": wo.wo_number,
        "product_name": wo.product.name,
        "product_code": wo.product.item.code,
        "quantity_planned": str(wo.quantity_planned),
        "quantity_produced": str(wo.quantity_produced),
        "quantity_rejected": str(wo.quantity_rejected),
        "operator_name": wo.operator.get_full_name(),
        "production_approved_at": wo.production_approved_at,
        "production_approved_by_name": (
            wo.production_approved_by.get_full_name() if wo.production_approved_by else None
        ),
        "status": wo.status,
        "pending_receipt": {
            "quantity": str(receipt.quantity_received) if receipt else str(wo.quantity_produced),
            "batch_number": receipt.batch_number if receipt else "",
            "posted": receipt.posted if receipt else False,
        },
    }


class ProductionReceiptQueueView(APIView):
    """List work orders awaiting storekeeper finished-goods receipt."""

    permission_classes = [IsAuthenticated, HasModulePermission]
    module_name = "inventory"
    required_action = "read"

    def get(self, request):
        if not can_receive_finished_goods(request.user) and not user_has_permission(
            request.user, "inventory", "read"
        ):
            return api_error(message="You do not have permission to view production receipts.")
        rows = (
            WorkOrder.objects.filter(
                is_active=True,
                execution_workflow=True,
                status=WorkOrder.STATUS_WAITING_STORE,
            )
            .select_related(
                "product__item",
                "operator",
                "production_approved_by",
                "finished_goods_receipt",
            )
            .order_by("-production_approved_at", "-updated_at")
        )
        return api_response(data=[_serialize_receipt_row(wo) for wo in rows])


class ProductionReceiptReceiveView(APIView):
    """Confirm finished goods into inventory (PRODUCTION_OUTPUT)."""

    permission_classes = [IsAuthenticated, HasModulePermission]
    module_name = "inventory"
    required_action = "create"

    def post(self, request, wo_id):
        if not can_receive_finished_goods(request.user):
            return api_error(message="Storekeeper permission required to receive finished goods.")
        try:
            wo = WorkOrder.objects.get(pk=wo_id, is_active=True)
        except WorkOrder.DoesNotExist:
            return api_error(message="Work order not found.", status=404)
        ser = StoreReceiptSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            ProductionExecutionService.store_receipt(
                wo,
                request.user,
                warehouse_id=ser.validated_data["warehouse"],
                quantity_received=ser.validated_data["quantity_received"],
                batch_number=ser.validated_data.get("batch_number", ""),
                notes=ser.validated_data.get("notes", ""),
            )
        except (ValueError, PermissionError) as exc:
            return api_error(message=str(exc))
        wo.refresh_from_db()
        return api_response(
            data=_serialize_receipt_row(wo),
            message="Finished goods received into inventory",
        )
