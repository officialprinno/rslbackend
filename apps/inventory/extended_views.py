"""Extended inventory API viewsets."""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions import HasModulePermission
from apps.core.responses import api_error, api_response
from apps.inventory.consumption_reports import (
    build_cost_allocation_report,
    build_internal_consumption_report,
)
from apps.inventory.dashboard import (
    build_inventory_dashboard,
    build_reorder_suggestions,
    build_valuation_report,
    create_requisition_from_suggestions,
)
from apps.inventory.extended_serializers import (
    DepartmentRequestSerializer,
    GoodsIssueNoteSerializer,
    StockBatchSerializer,
    StockTakeSerializer,
    StockTransferSerializer,
)
from apps.inventory.filters import (
    DepartmentRequestFilter,
    GoodsIssueNoteFilter,
    StockBatchFilter,
    StockTakeFilter,
    StockTransferFilter,
)
from apps.inventory.mixins import InventoryViewSetMixin
from apps.inventory.models import (
    DepartmentRequest,
    GoodsIssueNote,
    StockBatch,
    StockTake,
    StockTransfer,
)
from apps.inventory.workflow import (
    approve_department_request,
    approve_goods_issue,
    approve_stock_take,
    approve_stock_transfer,
    cancel_department_request,
    complete_stock_transfer,
    issue_department_request,
    reject_department_request,
    reject_goods_issue,
    reject_stock_take,
    reject_stock_transfer,
    submit_department_request,
)


class InventoryDashboardView(APIView):
    """Inventory module dashboard KPIs and charts."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        warehouse_id = request.query_params.get("warehouse")
        wh_id = int(warehouse_id) if warehouse_id and warehouse_id.isdigit() else None
        return api_response(data=build_inventory_dashboard(warehouse_id=wh_id))


class InventoryValuationView(APIView):
    """Inventory valuation report."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.inventory.store_permissions import can_view_valuation_report

        if not can_view_valuation_report(request.user):
            return api_error(message="You do not have permission to view inventory valuation.")
        method = request.query_params.get("method", "WEIGHTED_AVERAGE")
        return api_response(data=build_valuation_report(method))


class ReorderSuggestionsView(APIView):
    """Auto-generated reorder suggestions."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return api_response(data=build_reorder_suggestions())

    def post(self, request):
        """Create a suggested purchase requisition from reorder queue."""
        from apps.core.permissions import user_has_permission
        from apps.procurement.serializers import PurchaseRequisitionSerializer

        if not user_has_permission(request.user, "inventory", "approve") and not user_has_permission(
            request.user, "procurement", "create"
        ):
            return api_error(message="Procurement or inventory approval permission required.")
        priorities = request.data.get("priorities")
        item_ids = request.data.get("item_ids")
        try:
            pr = create_requisition_from_suggestions(
                request.user,
                priorities=priorities,
                item_ids=item_ids,
            )
        except ValueError as exc:
            return api_error(message=str(exc))
        return api_response(
            data=PurchaseRequisitionSerializer(pr).data,
            message="Suggested purchase requisition created",
        )


class InternalConsumptionReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        department = request.query_params.get("department")
        month = request.query_params.get("month")
        data = build_internal_consumption_report(department=department, month=month)
        payload = {
            **data,
            "movement_cost_mtd": str(data["movement_cost_mtd"]),
            "department_usage": [
                {**row, "total_cost": str(row["total_cost"])} for row in data["department_usage"]
            ],
            "most_consumed_items": [
                {
                    **row,
                    "quantity": str(row["quantity"]),
                    "total_cost": str(row["total_cost"]),
                }
                for row in data["most_consumed_items"]
            ],
            "most_requested_items": [
                {**row, "total_requested": str(row["total_requested"])}
                for row in data["most_requested_items"]
            ],
            "monthly_trend": [
                {**row, "total_cost": str(row["total_cost"])} for row in data["monthly_trend"]
            ],
        }
        return api_response(data=payload)


class CostAllocationReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month = request.query_params.get("month")
        data = build_cost_allocation_report(month=month)
        payload = {
            **data,
            "total_internal_expense": str(data["total_internal_expense"]),
            "allocations": [
                {**row, "consumption_cost": str(row["consumption_cost"])}
                for row in data["allocations"]
            ],
            "monthly_trend": [
                {**row, "total_cost": str(row["total_cost"])} for row in data["monthly_trend"]
            ],
        }
        return api_response(data=payload)


class StockBatchViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    queryset = StockBatch.objects.select_related(
        "item", "warehouse", "supplier"
    ).all()
    serializer_class = StockBatchSerializer
    filterset_class = StockBatchFilter
    search_fields = ["batch_number", "item__code", "item__name"]
    ordering_fields = ["created_at", "expiry_date"]

    def get_create_message(self):
        return "Batch created"


class StockTransferViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    queryset = StockTransfer.objects.select_related(
        "source_warehouse",
        "destination_warehouse",
        "requested_by",
        "approved_by",
    ).prefetch_related("lines__item").all()
    serializer_class = StockTransferSerializer
    filterset_class = StockTransferFilter
    search_fields = ["transfer_number", "notes"]
    ordering_fields = ["created_at", "status"]
    http_method_names = ["get", "post", "head", "options"]

    def get_create_message(self):
        return "Stock transfer created"

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        transfer = self.get_object()
        try:
            transfer = approve_stock_transfer(transfer, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=StockTransferSerializer(transfer).data,
            message="Transfer approved",
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        transfer = self.get_object()
        try:
            transfer = complete_stock_transfer(transfer, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=StockTransferSerializer(transfer).data,
            message="Transfer completed and stock updated",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        transfer = self.get_object()
        try:
            transfer = reject_stock_transfer(transfer, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=StockTransferSerializer(transfer).data,
            message="Transfer rejected",
        )


class DepartmentRequestViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    queryset = DepartmentRequest.objects.select_related(
        "warehouse", "requested_by", "approved_by"
    ).prefetch_related("lines__item", "lines__warehouse").filter(is_active=True)
    serializer_class = DepartmentRequestSerializer
    filterset_class = DepartmentRequestFilter
    search_fields = ["request_number", "notes", "purpose"]
    ordering_fields = ["created_at", "status", "priority", "needed_by_date"]
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        self.required_action = self.get_required_action()
        if self.action in ("list", "retrieve", "create", "submit", "cancel"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), HasModulePermission()]

    def get_required_action(self):
        if self.action in ("issue", "partial_issue"):
            return "create"
        if self.action in ("approve", "reject", "bulk_approve"):
            return "approve"
        return "read"

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.action == "create":
            submit = self.request.data.get("submit", False)
            if isinstance(submit, str):
                submit = submit.lower() in ("true", "1", "yes")
            ctx["submit"] = bool(submit)
        return ctx

    def get_create_message(self):
        return "Department request created"

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        dept_request = self.get_object()
        try:
            dept_request = submit_department_request(dept_request, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=DepartmentRequestSerializer(dept_request).data,
            message="Request submitted for approval",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        dept_request = self.get_object()
        try:
            dept_request = cancel_department_request(dept_request, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(message="Request cancelled")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        dept_request = self.get_object()
        comment = request.data.get("comment", "")
        try:
            dept_request = approve_department_request(dept_request, request.user, comment=comment)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=DepartmentRequestSerializer(dept_request).data,
            message="Request approved",
        )

    @action(detail=False, methods=["post"])
    def bulk_approve(self, request):
        ids = request.data.get("ids", [])
        comment = request.data.get("comment", "")
        if not ids:
            return api_error(message="No request IDs provided.")
        approved = []
        errors = []
        for pk in ids:
            dept_request = DepartmentRequest.objects.filter(pk=pk, is_active=True).first()
            if not dept_request:
                errors.append(f"Request {pk} not found.")
                continue
            try:
                approved.append(
                    approve_department_request(dept_request, request.user, comment=comment)
                )
            except DRFValidationError as exc:
                errors.append(f"{dept_request.request_number}: {exc.detail}")
        return api_response(
            data=DepartmentRequestSerializer(approved, many=True).data,
            message=f"Approved {len(approved)} request(s).",
            errors=errors or None,
        )

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        dept_request = self.get_object()
        line_quantities = request.data.get("lines")
        partial = bool(request.data.get("partial", False))
        try:
            dept_request = issue_department_request(
                dept_request,
                request.user,
                line_quantities=line_quantities,
                partial=partial,
            )
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=DepartmentRequestSerializer(dept_request).data,
            message="Stock issued",
        )

    @action(detail=True, methods=["post"], url_path="partial-issue")
    def partial_issue(self, request, pk=None):
        dept_request = self.get_object()
        line_quantities = request.data.get("lines")
        try:
            dept_request = issue_department_request(
                dept_request,
                request.user,
                line_quantities=line_quantities,
                partial=True,
            )
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=DepartmentRequestSerializer(dept_request).data,
            message="Partial stock issued",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        dept_request = self.get_object()
        reason = request.data.get("reason", "")
        try:
            dept_request = reject_department_request(dept_request, request.user, reason=reason)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=DepartmentRequestSerializer(dept_request).data,
            message="Request rejected",
        )


class GoodsIssueNoteViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    queryset = GoodsIssueNote.objects.select_related(
        "warehouse", "requested_by", "approved_by"
    ).prefetch_related("lines__item").all()
    serializer_class = GoodsIssueNoteSerializer
    filterset_class = GoodsIssueNoteFilter
    search_fields = ["gin_number", "reason"]
    ordering_fields = ["created_at", "status"]
    http_method_names = ["get", "post", "head", "options"]

    def get_create_message(self):
        return "Goods issue note created"

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        gin = self.get_object()
        try:
            gin = approve_goods_issue(gin, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=GoodsIssueNoteSerializer(gin).data,
            message="GIN approved and stock issued",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        gin = self.get_object()
        try:
            gin = reject_goods_issue(gin, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=GoodsIssueNoteSerializer(gin).data,
            message="GIN rejected",
        )


class StockTakeViewSet(InventoryViewSetMixin, viewsets.ModelViewSet):
    queryset = StockTake.objects.select_related(
        "warehouse", "conducted_by", "approved_by"
    ).prefetch_related("lines__item").all()
    serializer_class = StockTakeSerializer
    filterset_class = StockTakeFilter
    search_fields = ["take_number", "notes"]
    ordering_fields = ["created_at", "status"]
    http_method_names = ["get", "post", "head", "options"]

    def get_create_message(self):
        return "Stock take submitted"

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        stock_take = self.get_object()
        try:
            stock_take = approve_stock_take(stock_take, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=StockTakeSerializer(stock_take).data,
            message="Stock take approved and variances applied",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        stock_take = self.get_object()
        try:
            stock_take = reject_stock_take(stock_take, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data=StockTakeSerializer(stock_take).data,
            message="Stock take rejected",
        )
