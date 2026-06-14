"""Procurement API viewsets."""

from decimal import Decimal

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import api_error, api_response
from apps.procurement.filters import (
    GRNFilter,
    PurchaseOrderFilter,
    PurchaseRequisitionFilter,
    QuotationFilter,
    RFQFilter,
    SupplierFilter,
    SupplierInvoiceFilter,
)
from apps.procurement.mixins import ProcurementViewSetMixin
from apps.procurement.models import (
    GoodsReceivedNote,
    InvoicePayment,
    PurchaseOrder,
    PurchaseRequisition,
    RequestForQuotation,
    Supplier,
    SupplierInvoice,
    SupplierQuotation,
)
from apps.procurement.serializers import (
    GRNSerializer,
    PaymentSerializer,
    PurchaseOrderSerializer,
    PurchaseRequisitionSerializer,
    QuotationSerializer,
    RejectSerializer,
    RFQSerializer,
    SupplierInvoiceSerializer,
    SupplierSerializer,
)
from apps.procurement.services import ProcurementService


class SupplierViewSet(ProcurementViewSetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.select_related("currency").all()
    serializer_class = SupplierSerializer
    filterset_class = SupplierFilter
    search_fields = ["name", "tin_number", "email", "phone"]
    ordering_fields = ["name", "rating", "created_at"]

    def get_create_message(self):
        return "Supplier created"

    def get_update_message(self):
        return "Supplier updated"

    def get_destroy_message(self):
        return "Supplier deactivated"


class PurchaseRequisitionViewSet(ProcurementViewSetMixin, viewsets.ModelViewSet):
    queryset = PurchaseRequisition.objects.select_related(
        "department", "requested_by", "approved_by"
    ).prefetch_related("items__item")
    serializer_class = PurchaseRequisitionSerializer
    filterset_class = PurchaseRequisitionFilter
    search_fields = ["pr_number", "notes"]
    ordering_fields = ["created_at", "priority", "total_estimated"]

    def get_create_message(self):
        return "Purchase requisition created"

    def get_update_message(self):
        return "Purchase requisition updated"

    def get_destroy_message(self):
        return "Purchase requisition deleted"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != PurchaseRequisition.STATUS_DRAFT:
            return api_error(message="Only draft requisitions can be deleted.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        pr = self.get_object()
        if pr.status != PurchaseRequisition.STATUS_DRAFT:
            return api_error(message="Only draft requisitions can be submitted.")
        if not pr.items.exists():
            return api_error(message="Add at least one item before submitting.")
        pr.status = PurchaseRequisition.STATUS_PENDING
        pr.save(update_fields=["status", "updated_at"])
        return api_response(
            data=PurchaseRequisitionSerializer(pr).data,
            message="Requisition submitted for approval",
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        pr = self.get_object()
        if pr.status != PurchaseRequisition.STATUS_PENDING:
            return api_error(message="Only pending requisitions can be approved.")
        pr.status = PurchaseRequisition.STATUS_APPROVED
        pr.approved_by = request.user
        pr.approved_at = timezone.now()
        pr.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return api_response(
            data=PurchaseRequisitionSerializer(pr).data,
            message="Requisition approved",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        pr = self.get_object()
        if pr.status != PurchaseRequisition.STATUS_PENDING:
            return api_error(message="Only pending requisitions can be rejected.")
        serializer = RejectSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        pr.status = PurchaseRequisition.STATUS_REJECTED
        pr.rejection_reason = serializer.validated_data["reason"]
        pr.approved_by = request.user
        pr.approved_at = timezone.now()
        pr.save(
            update_fields=[
                "status",
                "rejection_reason",
                "approved_by",
                "approved_at",
                "updated_at",
            ]
        )
        return api_response(
            data=PurchaseRequisitionSerializer(pr).data,
            message="Requisition rejected",
        )


class RFQViewSet(ProcurementViewSetMixin, viewsets.ModelViewSet):
    queryset = RequestForQuotation.objects.select_related(
        "requisition", "created_by"
    ).prefetch_related("suppliers", "requisition__items__item")
    serializer_class = RFQSerializer
    filterset_class = RFQFilter
    search_fields = ["rfq_number", "requisition__pr_number"]
    ordering_fields = ["created_at", "deadline"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_create_message(self):
        return "RFQ created"

    def get_update_message(self):
        return "RFQ updated"

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        rfq = self.get_object()
        if rfq.status != RequestForQuotation.STATUS_OPEN:
            return api_error(message="Only open RFQs can be closed.")
        rfq.status = RequestForQuotation.STATUS_CLOSED
        rfq.save(update_fields=["status", "updated_at"])
        return api_response(
            data=RFQSerializer(rfq).data,
            message="RFQ closed",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        rfq = self.get_object()
        if rfq.status == RequestForQuotation.STATUS_CANCELLED:
            return api_error(message="RFQ is already cancelled.")
        rfq.status = RequestForQuotation.STATUS_CANCELLED
        rfq.save(update_fields=["status", "updated_at"])
        return api_response(
            data=RFQSerializer(rfq).data,
            message="RFQ cancelled",
        )


class QuotationViewSet(ProcurementViewSetMixin, viewsets.ModelViewSet):
    queryset = SupplierQuotation.objects.select_related(
        "rfq", "supplier", "currency"
    ).prefetch_related("items__item")
    serializer_class = QuotationSerializer
    filterset_class = QuotationFilter
    search_fields = ["quotation_number", "supplier__name"]
    ordering_fields = ["quotation_date", "total_amount"]
    http_method_names = ["get", "post", "head", "options"]

    def get_create_message(self):
        return "Quotation recorded"

    @action(detail=True, methods=["post"])
    def select(self, request, pk=None):
        quotation = self.get_object()
        if quotation.status != SupplierQuotation.STATUS_PENDING:
            return api_error(message="Only pending quotations can be selected.")
        try:
            po = ProcurementService.select_quotation(quotation, request.user)
        except DRFValidationError as exc:
            return api_error(message=str(exc.detail))
        return api_response(
            data={
                "quotation": QuotationSerializer(quotation).data,
                "purchase_order": PurchaseOrderSerializer(po).data,
            },
            message="Quotation selected — draft PO created",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        quotation = self.get_object()
        quotation.status = SupplierQuotation.STATUS_REJECTED
        quotation.save(update_fields=["status", "updated_at"])
        return api_response(
            data=QuotationSerializer(quotation).data,
            message="Quotation rejected",
        )


class PurchaseOrderViewSet(ProcurementViewSetMixin, viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related(
        "supplier", "currency", "created_by", "approved_by", "requisition", "quotation"
    ).prefetch_related("items__item", "grns")
    serializer_class = PurchaseOrderSerializer
    filterset_class = PurchaseOrderFilter
    search_fields = ["po_number", "supplier__name"]
    ordering_fields = ["order_date", "total_amount", "created_at"]

    def get_create_message(self):
        return "Purchase order created"

    def get_update_message(self):
        return "Purchase order updated"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != PurchaseOrder.STATUS_DRAFT:
            return api_error(message="Only draft POs can be deleted.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        po = self.get_object()
        if po.status != PurchaseOrder.STATUS_DRAFT:
            return api_error(message="Only draft POs can be submitted.")
        if not po.items.exists():
            return api_error(message="Add at least one item before submitting.")
        po.status = PurchaseOrder.STATUS_PENDING
        po.save(update_fields=["status", "updated_at"])
        return api_response(
            data=PurchaseOrderSerializer(po).data,
            message="Purchase order submitted for approval",
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        po = self.get_object()
        if po.status != PurchaseOrder.STATUS_PENDING:
            return api_error(message="Only pending POs can be approved.")
        po.status = PurchaseOrder.STATUS_APPROVED
        po.approved_by = request.user
        po.approved_at = timezone.now()
        po.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return api_response(
            data=PurchaseOrderSerializer(po).data,
            message="Purchase order approved",
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        po = self.get_object()
        if po.status != PurchaseOrder.STATUS_PENDING:
            return api_error(message="Only pending POs can be rejected.")
        serializer = RejectSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        po.status = PurchaseOrder.STATUS_CANCELLED
        po.rejection_reason = serializer.validated_data["reason"]
        po.approved_by = request.user
        po.approved_at = timezone.now()
        po.save(
            update_fields=[
                "status",
                "rejection_reason",
                "approved_by",
                "approved_at",
                "updated_at",
            ]
        )
        return api_response(
            data=PurchaseOrderSerializer(po).data,
            message="Purchase order rejected",
        )

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        po = self.get_object()
        if po.status != PurchaseOrder.STATUS_APPROVED:
            return api_error(message="Only approved POs can be sent to supplier.")
        po.status = PurchaseOrder.STATUS_SENT
        po.save(update_fields=["status", "updated_at"])
        return api_response(
            data=PurchaseOrderSerializer(po).data,
            message="Purchase order sent to supplier",
        )


class GRNViewSet(ProcurementViewSetMixin, viewsets.ModelViewSet):
    queryset = GoodsReceivedNote.objects.select_related(
        "purchase_order__supplier", "warehouse", "received_by"
    ).prefetch_related("items__item", "items__po_item")
    serializer_class = GRNSerializer
    filterset_class = GRNFilter
    search_fields = ["grn_number", "purchase_order__po_number"]
    ordering_fields = ["received_date", "created_at"]

    def get_create_message(self):
        return "GRN created"

    def get_update_message(self):
        return "GRN updated"

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        grn = self.get_object()
        try:
            result = ProcurementService.confirm_grn(grn)
        except DRFValidationError as exc:
            detail = exc.detail
            message = detail[0] if isinstance(detail, list) else str(detail)
            return api_error(message=message)
        grn = result["grn"]
        return api_response(
            data={
                "grn": GRNSerializer(grn).data,
                "stock_updates": result["stock_updates"],
                "po_status": result["po_status"],
            },
            message="GRN confirmed — stock updated",
        )


class SupplierInvoiceViewSet(ProcurementViewSetMixin, viewsets.ModelViewSet):
    queryset = SupplierInvoice.objects.select_related(
        "supplier", "purchase_order", "grn", "currency"
    )
    serializer_class = SupplierInvoiceSerializer
    filterset_class = SupplierInvoiceFilter
    search_fields = ["invoice_number", "supplier__name", "purchase_order__po_number"]
    ordering_fields = ["invoice_date", "due_date", "total_amount"]
    http_method_names = ["get", "post", "head", "options"]

    def get_create_message(self):
        return "Supplier invoice recorded"

    @action(detail=True, methods=["post"])
    def match(self, request, pk=None):
        invoice = self.get_object()
        invoice = ProcurementService.match_invoice(invoice)
        return api_response(
            data=SupplierInvoiceSerializer(invoice).data,
            message="3-way match completed" if invoice.three_way_matched else "Discrepancy found",
        )

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        invoice = self.get_object()
        if not invoice.three_way_matched:
            return api_error(message="Invoice must be 3-way matched before payment.")
        serializer = PaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        amount = serializer.validated_data["amount"]
        if amount <= 0:
            return api_error(message="Payment amount must be positive.")
        if amount > invoice.balance:
            return api_error(message="Payment exceeds invoice balance.")
        InvoicePayment.objects.create(
            invoice=invoice,
            recorded_by=request.user,
            **serializer.validated_data,
        )
        invoice.paid_amount += amount
        if invoice.paid_amount >= invoice.total_amount:
            invoice.status = SupplierInvoice.STATUS_PAID
        else:
            invoice.status = SupplierInvoice.STATUS_PARTIAL
        invoice.save(update_fields=["paid_amount", "status", "updated_at"])
        return api_response(
            data=SupplierInvoiceSerializer(invoice).data,
            message="Payment recorded",
        )


class ProcurementDashboardViewSet(ViewSet):
    """Procurement dashboard summary widgets."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        from apps.procurement.dashboard import build_procurement_dashboard

        data = build_procurement_dashboard()
        payload = {
            **data,
            "monthly_spend": str(data["monthly_spend"]),
            "monthly_chart": [
                {
                    "month": row["month"],
                    "spend": str(row["spend"]),
                    "po_count": row["po_count"],
                }
                for row in data["monthly_chart"]
            ],
            "top_suppliers": [
                {
                    "name": row["name"],
                    "total": str(row["total"]),
                    "order_count": row["order_count"],
                }
                for row in data["top_suppliers"]
            ],
            "recent_activities": [
                {
                    **row,
                    "amount": str(row["amount"]) if row["amount"] is not None else None,
                    "created_at": row["created_at"].isoformat(),
                }
                for row in data["recent_activities"]
            ],
        }
        return api_response(data=payload)
