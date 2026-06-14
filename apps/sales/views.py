"""Sales API viewsets."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import api_error, api_response
from apps.sales.filters import (
    CreditNoteFilter,
    CustomerFilter,
    InvoiceFilter,
    PaymentFilter,
    QuotationFilter,
    SalesOrderFilter,
)
from apps.sales.mixins import SalesViewSetMixin
from apps.sales.models import (
    CreditNote,
    Customer,
    CustomerPayment,
    SalesInvoice,
    SalesInvoiceItem,
    SalesOrder,
    SalesOrderItem,
    SalesQuotation,
    SalesQuotationItem,
)
from apps.sales.serializers import (
    CancelOrderSerializer,
    CreditNoteSerializer,
    CustomerSerializer,
    InvoiceSerializer,
    PaymentSerializer,
    QuotationSerializer,
    SalesOrderSerializer,
)
from apps.sales.services import SalesService
from apps.sales.utils import generate_document_number
from apps.sales.workflow import SalesOrderWorkflow
from apps.sales.workflow_serializers import (
    DeliveryConfirmSerializer,
    DeliveryCostSerializer,
    DeliveryMethodSerializer,
    PartialStockSerializer,
    PaymentProofSubmitSerializer,
    PaymentVerifySerializer,
    PickupConfirmSerializer,
    ProcurementRequestSerializer,
    RejectQuotationSerializer,
    ThirdPartyAssignmentSerializer,
    VehicleAssignmentSerializer,
)


class CustomerViewSet(SalesViewSetMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.select_related("currency").all()
    serializer_class = CustomerSerializer
    filterset_class = CustomerFilter
    search_fields = ["name", "tin_number", "email", "mine_name"]
    ordering_fields = ["name", "created_at", "credit_limit"]

    def get_create_message(self):
        return "Customer created"

    def get_update_message(self):
        return "Customer updated"

    def get_destroy_message(self):
        return "Customer deactivated"

    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        customer = self.get_object()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        lines = SalesService.customer_statement(customer, date_from, date_to)
        aging = SalesService.invoice_aging(customer)
        return api_response(
            data={
                "customer": CustomerSerializer(customer).data,
                "lines": lines,
                "aging": aging,
                "outstanding_balance": str(SalesService.customer_outstanding(customer)),
            }
        )


class QuotationViewSet(SalesViewSetMixin, viewsets.ModelViewSet):
    queryset = SalesQuotation.objects.select_related(
        "customer", "currency", "created_by"
    ).prefetch_related("items__item")
    serializer_class = QuotationSerializer
    filterset_class = QuotationFilter
    search_fields = ["quotation_number", "customer__name"]
    ordering_fields = ["created_at", "valid_until", "total_amount"]

    def get_create_message(self):
        return "Quotation created"

    def get_update_message(self):
        return "Quotation updated"

    def get_destroy_message(self):
        return "Quotation deleted"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not SalesService.quotation_is_deletable(instance):
            return api_error(
                message="This quotation cannot be deleted (converted to sales order)."
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        qt = self.get_object()
        if qt.status != SalesQuotation.STATUS_DRAFT:
            return api_error(message="Only draft quotations can be sent.")
        if not qt.items.exists():
            return api_error(message="Add at least one item before sending.")
        qt.status = SalesQuotation.STATUS_SENT
        qt.save(update_fields=["status", "updated_at"])
        return api_response(data=QuotationSerializer(qt).data, message="Quotation sent")

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        qt = self.get_object()
        if qt.status != SalesQuotation.STATUS_SENT:
            return api_error(message="Only sent quotations can be accepted.")
        qt.status = SalesQuotation.STATUS_ACCEPTED
        qt.save(update_fields=["status", "updated_at"])
        return api_response(data=QuotationSerializer(qt).data, message="Quotation accepted")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        qt = self.get_object()
        if qt.status != SalesQuotation.STATUS_SENT:
            return api_error(message="Only sent quotations can be rejected.")
        qt.status = SalesQuotation.STATUS_REJECTED
        qt.save(update_fields=["status", "updated_at"])
        return api_response(data=QuotationSerializer(qt).data, message="Quotation rejected")

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        qt = self.get_object()
        if qt.status not in (SalesQuotation.STATUS_SENT, SalesQuotation.STATUS_ACCEPTED):
            return api_error(message="Only sent or accepted quotations can be converted.")
        with transaction.atomic():
            order = SalesOrder.objects.create(
                so_number=generate_document_number("SO", SalesOrder, "so_number"),
                customer=qt.customer,
                quotation=qt,
                currency=qt.currency,
                exchange_rate=qt.exchange_rate,
                delivery_date=timezone.now().date() + timedelta(days=14),
                delivery_address=qt.customer.address,
                delivery_cost=qt.delivery_cost or Decimal("0"),
                apply_vat=qt.apply_vat,
                notes=qt.notes,
                created_by=request.user,
            )
            for line in qt.items.all():
                SalesOrderItem.objects.create(
                    sales_order=order,
                    item=line.item,
                    quantity_ordered=line.quantity,
                    unit_price=line.unit_price,
                    discount_percent=line.discount_percent,
                )
            SalesService.recalculate_order(order)
            SalesService.log_activity(
                order, "Converted from quotation", request.user, qt.quotation_number
            )
        return api_response(
            data=SalesOrderSerializer(order).data,
            message="Sales order created from quotation",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        qt = self.get_object()
        with transaction.atomic():
            from apps.sales.utils import generate_document_number

            new_qt = SalesQuotation.objects.create(
                quotation_number=generate_document_number("QT", SalesQuotation, "quotation_number"),
                customer=qt.customer,
                currency=qt.currency,
                exchange_rate=qt.exchange_rate,
                valid_until=timezone.now().date() + timedelta(days=30),
                status=SalesQuotation.STATUS_DRAFT,
                apply_vat=qt.apply_vat,
                notes=qt.notes,
                terms_conditions=qt.terms_conditions,
                created_by=request.user,
            )
            for line in qt.items.all():
                SalesQuotationItem.objects.create(
                    quotation=new_qt,
                    item=line.item,
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    discount_percent=line.discount_percent,
                )
            SalesService.recalculate_quotation(new_qt)
        return api_response(
            data=QuotationSerializer(new_qt).data,
            message="Quotation duplicated",
            status=status.HTTP_201_CREATED,
        )


class SalesOrderViewSet(SalesViewSetMixin, viewsets.ModelViewSet):
    queryset = SalesOrder.objects.select_related(
        "customer",
        "currency",
        "quotation",
        "created_by",
        "approved_by",
        "fulfillment_warehouse",
        "linked_pr",
        "delivery_cost_detail",
        "dispatch_assignment__vehicle",
        "dispatch_assignment__driver__user",
        "pickup_detail",
    ).prefetch_related("items__item", "activities__user", "payment_proofs")
    serializer_class = SalesOrderSerializer
    filterset_class = SalesOrderFilter
    search_fields = ["so_number", "lpo_number", "customer__name"]
    ordering_fields = ["created_at", "delivery_date", "total_amount"]

    def get_create_message(self):
        return "Sales order created"

    def get_update_message(self):
        return "Sales order updated"

    def get_destroy_message(self):
        return "Sales order deleted"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status not in SalesOrderWorkflow.EDITABLE_STATUSES:
            return api_error(message="Only new/draft orders can be deleted.")
        return super().destroy(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        if order.status in (
            SalesOrder.STATUS_DISPATCHED,
            SalesOrder.STATUS_IN_TRANSIT,
            SalesOrder.STATUS_DELIVERED,
            SalesOrder.STATUS_DELIVERY_CONFIRMED,
        ):
            SalesOrderWorkflow.ensure_fleet_matches_order(order)
            order.refresh_from_db()
        return super().retrieve(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def stock_check(self, request, pk=None):
        order = self.get_object()
        return api_response(data=SalesOrderWorkflow.stock_check(order))

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        order = self.get_object()
        try:
            SalesOrderWorkflow.submit_order(order, request.user)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data=SalesOrderSerializer(order).data,
            message="Order submitted — stock verification started",
        )

    @action(detail=True, methods=["post"])
    def verify_stock(self, request, pk=None):
        order = self.get_object()
        ser = PartialStockSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            result = SalesOrderWorkflow.verify_stock(
                order, request.user, partial=ser.validated_data.get("partial", False)
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data={"order": SalesOrderSerializer(order).data, **result},
            message=f"Stock check: {result['result']}",
        )

    @action(detail=True, methods=["post"])
    def create_procurement(self, request, pk=None):
        order = self.get_object()
        ser = ProcurementRequestSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            pr = SalesOrderWorkflow.create_procurement_request(
                order,
                request.user,
                department_id=ser.validated_data.get("department_id"),
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data={"order": SalesOrderSerializer(order).data, "pr_number": pr.pr_number},
            message="Purchase requisition created",
        )

    @action(detail=True, methods=["post"])
    def send_to_logistics(self, request, pk=None):
        order = self.get_object()
        try:
            SalesOrderWorkflow.send_to_logistics_for_delivery_cost(order, request.user)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data=SalesOrderSerializer(order).data,
            message="Order sent to Logistics for delivery cost calculation",
        )

    @action(detail=True, methods=["post"])
    def delivery_cost(self, request, pk=None):
        order = self.get_object()
        ser = DeliveryCostSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.calculate_delivery_cost(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data=SalesOrderSerializer(order).data,
            message="Delivery cost calculated",
        )

    @action(detail=True, methods=["post"])
    def send_quotation(self, request, pk=None):
        order = self.get_object()
        try:
            SalesOrderWorkflow.send_quotation(order, request.user)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Quotation sent")

    @action(detail=True, methods=["post"])
    def accept_quotation(self, request, pk=None):
        order = self.get_object()
        try:
            SalesOrderWorkflow.accept_quotation(order, request.user)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Quotation accepted")

    @action(detail=True, methods=["post"])
    def reject_quotation(self, request, pk=None):
        order = self.get_object()
        ser = RejectQuotationSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.reject_quotation(
                order, request.user, ser.validated_data.get("reason", "")
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Quotation rejected")

    @action(detail=True, methods=["post"])
    def generate_invoice(self, request, pk=None):
        order = self.get_object()
        try:
            invoice = SalesOrderWorkflow.generate_invoice(order, request.user)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data={
                "order": SalesOrderSerializer(order).data,
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
            },
            message="Invoice generated",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def submit_payment(self, request, pk=None):
        order = self.get_object()
        ser = PaymentProofSubmitSerializer(data=request.data, context={"order": order})
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            proof = SalesOrderWorkflow.submit_payment_proof(
                order, request.user, ser.validated_data
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data={"order": SalesOrderSerializer(order).data, "proof_id": proof.id},
            message="Payment proof submitted",
        )

    @action(detail=True, methods=["post"])
    def verify_payment(self, request, pk=None):
        order = self.get_object()
        ser = PaymentVerifySerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.verify_payment(
                order,
                request.user,
                proof_id=ser.validated_data.get("proof_id"),
                approved=ser.validated_data["approved"],
                reason=ser.validated_data.get("reason", ""),
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Payment processed")

    @action(detail=True, methods=["post"])
    def set_delivery_method(self, request, pk=None):
        order = self.get_object()
        ser = DeliveryMethodSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.set_delivery_method(
                order, request.user, ser.validated_data["delivery_method"]
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Delivery method set")

    @action(detail=True, methods=["post"])
    def assign_vehicle(self, request, pk=None):
        order = self.get_object()
        ser = VehicleAssignmentSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.assign_vehicle(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Vehicle assigned")

    @action(detail=True, methods=["post"])
    def assign_third_party(self, request, pk=None):
        order = self.get_object()
        ser = ThirdPartyAssignmentSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.assign_third_party(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Third party assigned")

    @action(detail=True, methods=["post"], url_path="dispatch-order")
    def dispatch_order(self, request, pk=None):
        order = self.get_object()
        try:
            SalesOrderWorkflow.dispatch_order(order, request.user)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Order dispatched")

    @action(detail=True, methods=["post"])
    def confirm_pickup(self, request, pk=None):
        order = self.get_object()
        ser = PickupConfirmSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.confirm_pickup(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Pickup completed")

    @action(detail=True, methods=["post"])
    def confirm_delivery(self, request, pk=None):
        order = self.get_object()
        ser = DeliveryConfirmSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.confirm_delivery(order, request.user, ser.validated_data)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Delivery confirmed")

    @action(detail=True, methods=["post"])
    def logistics_confirm(self, request, pk=None):
        order = self.get_object()
        try:
            SalesOrderWorkflow.logistics_confirm(
                order, request.user, request.data.get("remarks", "")
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Logistics confirmed")

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        order = self.get_object()
        try:
            SalesOrderWorkflow.close_order(order, request.user)
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(data=SalesOrderSerializer(order).data, message="Order closed")

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """Legacy alias — submits order into enterprise workflow."""
        return self.submit(request, pk=pk)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        ser = CancelOrderSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            SalesOrderWorkflow.cancel_order(
                order, request.user, ser.validated_data["reason"]
            )
        except Exception as exc:
            return api_error(message=str(exc))
        order.refresh_from_db()
        return api_response(
            data=SalesOrderSerializer(order).data,
            message="Sales order cancelled",
        )


class InvoiceViewSet(SalesViewSetMixin, viewsets.ModelViewSet):
    queryset = SalesInvoice.objects.select_related(
        "customer", "currency", "sales_order", "created_by"
    ).prefetch_related("items__item")
    serializer_class = InvoiceSerializer
    filterset_class = InvoiceFilter
    search_fields = ["invoice_number", "customer__name", "tra_receipt_number"]
    ordering_fields = ["invoice_date", "due_date", "total_amount"]

    def get_create_message(self):
        return "Invoice created"

    def get_update_message(self):
        return "Invoice updated"

    def get_destroy_message(self):
        return "Invoice deleted"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != SalesInvoice.STATUS_DRAFT:
            return api_error(message="Only draft invoices can be deleted.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        inv = self.get_object()
        if inv.status != SalesInvoice.STATUS_DRAFT:
            return api_error(message="Only draft invoices can be issued.")
        inv.status = SalesInvoice.STATUS_SENT
        inv.save(update_fields=["status", "updated_at"])
        return api_response(data=InvoiceSerializer(inv).data, message="Invoice issued")

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        inv = self.get_object()
        if inv.status not in (SalesInvoice.STATUS_SENT, SalesInvoice.STATUS_PARTIAL):
            return api_error(message="Invoice must be issued before sending.")
        return api_response(data=InvoiceSerializer(inv).data, message="Invoice sent to customer")


class PaymentViewSet(SalesViewSetMixin, viewsets.ModelViewSet):
    queryset = CustomerPayment.objects.select_related(
        "customer", "invoice", "currency", "received_by"
    ).all()
    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter
    search_fields = ["payment_number", "reference_number", "customer__name"]
    ordering_fields = ["payment_date", "amount"]
    http_method_names = ["get", "post", "head", "options"]

    def get_create_message(self):
        return "Payment recorded"


class CreditNoteViewSet(SalesViewSetMixin, viewsets.ModelViewSet):
    queryset = CreditNote.objects.select_related(
        "invoice", "customer", "created_by", "approved_by"
    ).all()
    serializer_class = CreditNoteSerializer
    filterset_class = CreditNoteFilter
    search_fields = ["cn_number", "customer__name", "invoice__invoice_number"]
    ordering_fields = ["created_at", "amount"]
    http_method_names = ["get", "post", "head", "options"]

    def get_create_message(self):
        return "Credit note created"

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        cn = self.get_object()
        if cn.status != CreditNote.STATUS_DRAFT:
            return api_error(message="Only draft credit notes can be approved.")
        cn.status = CreditNote.STATUS_APPROVED
        cn.approved_by = request.user
        cn.approved_at = timezone.now()
        cn.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return api_response(
            data=CreditNoteSerializer(cn).data,
            message="Credit note approved",
        )

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        cn = self.get_object()
        if cn.status != CreditNote.STATUS_APPROVED:
            return api_error(message="Only approved credit notes can be applied.")
        SalesService.apply_credit_note(cn)
        return api_response(
            data=CreditNoteSerializer(cn).data,
            message="Credit note applied",
        )


class SalesDashboardViewSet(viewsets.ViewSet):
    """Sales dashboard summary widgets."""

    permission_classes = [IsAuthenticated]

    def list(self, request):
        from django.db.models import Count, Sum
        from django.db.models.functions import TruncWeek

        today = timezone.now().date()
        month_start = today.replace(day=1)

        orders = SalesOrder.objects.filter(
            is_active=True,
            created_at__date__gte=month_start,
            status__in=[
                SalesOrder.STATUS_CONFIRMED,
                SalesOrder.STATUS_PROCESSING,
                SalesOrder.STATUS_PARTIAL,
                SalesOrder.STATUS_DELIVERED,
            ],
        )
        weekly = (
            orders.annotate(week=TruncWeek("created_at"))
            .values("week")
            .annotate(total=Sum("total_amount"))
            .order_by("week")
        )
        top_customers = (
            SalesInvoice.objects.filter(is_active=True, invoice_date__gte=month_start)
            .values("customer__name")
            .annotate(revenue=Sum("total_amount"))
            .order_by("-revenue")[:5]
        )
        quotations_sent = SalesQuotation.objects.filter(
            is_active=True, created_at__date__gte=month_start, status=SalesQuotation.STATUS_SENT
        ).count()
        quotations_accepted = SalesQuotation.objects.filter(
            is_active=True,
            created_at__date__gte=month_start,
            status=SalesQuotation.STATUS_ACCEPTED,
        ).count()
        conversion = (
            round(quotations_accepted / quotations_sent * 100, 1) if quotations_sent else 0
        )
        overdue_count = SalesInvoice.objects.filter(
            is_active=True,
            status__in=[SalesInvoice.STATUS_OVERDUE, SalesInvoice.STATUS_PARTIAL],
            due_date__lt=today,
        ).count()
        new_orders = SalesOrder.objects.filter(
            is_active=True, status=SalesOrder.STATUS_NEW_ORDER
        ).count()
        pending_quotations = SalesOrder.objects.filter(
            is_active=True,
            status__in=[
                SalesOrder.STATUS_QUOTATION_PREP,
                SalesOrder.STATUS_QUOTATION_SENT,
                SalesOrder.STATUS_WAITING_CUSTOMER,
            ],
        ).count()
        accepted_quotations = SalesOrder.objects.filter(
            is_active=True, status=SalesOrder.STATUS_QUOTATION_ACCEPTED
        ).count()
        awaiting_payment = SalesOrder.objects.filter(
            is_active=True, status=SalesOrder.STATUS_AWAITING_PAYMENT
        ).count()
        monthly_revenue = SalesInvoice.objects.filter(
            is_active=True,
            invoice_date__gte=month_start,
            status__in=[
                SalesInvoice.STATUS_SENT,
                SalesInvoice.STATUS_PARTIAL,
                SalesInvoice.STATUS_PAID,
            ],
        ).aggregate(total=Sum("total_amount"))["total"] or 0

        return api_response(
            data={
                "weekly_sales": [
                    {"week": w["week"].isoformat() if w["week"] else "", "total": str(w["total"] or 0)}
                    for w in weekly
                ],
                "top_customers": [
                    {"name": c["customer__name"], "revenue": str(c["revenue"] or 0)}
                    for c in top_customers
                ],
                "quotation_conversion_rate": conversion,
                "overdue_invoices_count": overdue_count,
                "pending_so_approvals": new_orders,
                "new_orders_count": new_orders,
                "pending_quotations_count": pending_quotations,
                "accepted_quotations_count": accepted_quotations,
                "awaiting_payment_count": awaiting_payment,
                "monthly_revenue": str(monthly_revenue),
            }
        )
