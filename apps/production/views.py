"""Production API viewsets."""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.responses import api_error, api_response
from apps.production.execution_service import ProductionExecutionService
from apps.production.filters import (
    BOMFilter,
    MachineFilter,
    MachineUsageFilter,
    OutputRecordFilter,
    ProductFilter,
    WorkOrderFilter,
)
from apps.production.mixins import ProductionViewSetMixin
from apps.production.models import (
    BillOfMaterials,
    BOMItem,
    Machine,
    MachineServiceRecord,
    MachineUsage,
    OutputRecord,
    Product,
    WorkOrder,
)
from apps.production.production_permissions import (
    can_assign_operator,
    can_manage_work_orders,
    can_use_legacy_production_start,
    is_machine_operator,
)
from apps.production.reports import (
    build_completed_work_orders_report,
    build_downtime_report,
    build_machine_utilization_report,
    build_operator_performance_report,
    build_production_reports_bundle,
)
from apps.production.serializers import (
    AssignOperatorSerializer,
    BOMSerializer,
    ConsumptionSerializer,
    MachineRuntimeSerializer,
    MachineSerializer,
    MachineServiceRecordSerializer,
    MachineUsageSerializer,
    MaterialCheckSerializer,
    OperatorStartSerializer,
    OutputRecordSerializer,
    PauseSerializer,
    ProductSerializer,
    ProgressSerializer,
    QCCheckSerializer,
    StoreReceiptSerializer,
    SubmitCompletionSerializer,
    WorkOrderSerializer,
)
from apps.production.services import ProductionService


def _absolute_media_url(request, file_field) -> str | None:
    if not file_field or not getattr(file_field, "name", None):
        return None
    try:
        url = file_field.url
    except (ValueError, AttributeError):
        return None
    if url.startswith("http"):
        return url
    return request.build_absolute_uri(url)


class ProductViewSet(ProductionViewSetMixin, viewsets.ModelViewSet):
    queryset = Product.objects.select_related("item").all()
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    search_fields = ["name", "item__code", "item__name"]
    ordering_fields = ["name", "created_at"]

    def get_create_message(self):
        return "Product created"

    def get_update_message(self):
        return "Product updated"


class BOMViewSet(ProductionViewSetMixin, viewsets.ModelViewSet):
    queryset = BillOfMaterials.objects.select_related("product", "created_by").prefetch_related(
        "items__item"
    )
    serializer_class = BOMSerializer
    filterset_class = BOMFilter
    search_fields = ["product__name", "version"]
    ordering_fields = ["created_at", "version"]

    def get_create_message(self):
        return "BOM created"

    def get_update_message(self):
        return "BOM updated"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == BillOfMaterials.STATUS_ACTIVE:
            return api_error(message="Cannot delete active BOM.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        bom = self.get_object()
        if bom.status == BillOfMaterials.STATUS_ACTIVE:
            return api_error(message="BOM is already active.")
        if not bom.items.exists():
            return api_error(message="Add at least one component before activating.")
        ProductionService.activate_bom(bom)
        return api_response(data=BOMSerializer(bom).data, message="BOM activated")

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        bom = self.get_object()
        last_version = (
            BillOfMaterials.objects.filter(product=bom.product)
            .order_by("-created_at")
            .values_list("version", flat=True)
            .first()
        )
        try:
            new_ver = str(float(last_version or "1.0") + 0.1)
        except ValueError:
            new_ver = f"{last_version}-copy"
        new_bom = BillOfMaterials.objects.create(
            product=bom.product,
            version=new_ver,
            status=BillOfMaterials.STATUS_DRAFT,
            notes=bom.notes,
            created_by=request.user,
        )
        for line in bom.items.all():
            BOMItem.objects.create(
                bom=new_bom,
                item=line.item,
                quantity_required=line.quantity_required,
                wastage_percent=line.wastage_percent,
                notes=line.notes,
            )
        ProductionService.recalculate_bom_cost(new_bom)
        return api_response(
            data=BOMSerializer(new_bom).data,
            message="BOM duplicated",
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="check-materials")
    def check(self, request):
        ser = MaterialCheckSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        bom = BillOfMaterials.objects.get(pk=ser.validated_data["bom_id"])
        reqs = ProductionService.check_material_availability(
            bom, ser.validated_data["quantity"]
        )
        return api_response(data=reqs)


class WorkOrderViewSet(ProductionViewSetMixin, viewsets.ModelViewSet):
    queryset = WorkOrder.objects.select_related(
        "product",
        "bom",
        "sales_order",
        "operator",
        "approved_by",
        "created_by",
        "machine",
    ).prefetch_related(
        "material_issues__item",
        "pending_materials__item",
        "progress_entries",
        "pause_records",
        "execution_events",
        "finished_goods_receipt",
        "output_records",
        "machine_usage",
    )
    serializer_class = WorkOrderSerializer
    filterset_class = WorkOrderFilter
    search_fields = ["wo_number", "product__name"]
    ordering_fields = ["planned_start", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and is_machine_operator(user) and not can_manage_work_orders(user):
            qs = qs.filter(operator=user)
        return qs

    def create(self, request, *args, **kwargs):
        if is_machine_operator(request.user) and not can_manage_work_orders(request.user):
            return api_error(message="Machine operators cannot create work orders.")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if is_machine_operator(request.user) and not can_manage_work_orders(request.user):
            return api_error(message="Machine operators cannot edit work orders.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if is_machine_operator(request.user):
            return api_error(message="Machine operators cannot delete work orders.")
        return super().destroy(request, *args, **kwargs)

    def get_create_message(self):
        return "Work order created"

    def get_update_message(self):
        return "Work order updated"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != WorkOrder.STATUS_DRAFT:
            return api_error(message="Only draft work orders can be deleted.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        wo = self.get_object()
        if wo.status != WorkOrder.STATUS_DRAFT:
            return api_error(message="Only draft work orders can be submitted.")
        ProductionService.approve_work_order(wo, request.user)
        return api_response(
            data=WorkOrderSerializer(wo).data,
            message="Work order submitted for approval",
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        wo = self.get_object()
        if wo.status != WorkOrder.STATUS_DRAFT:
            return api_error(message="Only draft work orders can be approved.")
        ProductionService.approve_work_order(wo, request.user)
        return api_response(
            data=WorkOrderSerializer(wo).data,
            message="Work order approved",
        )

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        wo = self.get_object()
        if wo.execution_workflow:
            return api_error(
                message="Use operator start for execution workflow work orders.",
            )
        if wo.status != WorkOrder.STATUS_APPROVED:
            return api_error(message="Only approved work orders can be started.")
        if not can_use_legacy_production_start(request.user, wo):
            return api_error(message="You do not have permission to start this work order.")
        try:
            ProductionService.start_production(wo, request.user)
        except ValueError as e:
            return api_error(message=str(e))
        return api_response(
            data=WorkOrderSerializer(wo).data,
            message="Production started — materials deducted from stock",
        )

    @action(detail=True, methods=["post"], url_path="assign-operator")
    def assign_operator(self, request, pk=None):
        wo = self.get_object()
        if not can_assign_operator(request.user):
            return api_error(message="Production supervisor permission required.")
        ser = AssignOperatorSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        from apps.users.models import User

        operator = User.objects.get(pk=ser.validated_data["operator"], is_active=True)
        try:
            ProductionExecutionService.assign_operator(wo, operator, request.user)
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Operator assigned",
        )

    @action(detail=True, methods=["post"], url_path="operator-start")
    def operator_start(self, request, pk=None):
        wo = self.get_object()
        ser = OperatorStartSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            ProductionExecutionService.operator_start(
                wo,
                request.user,
                machine_id=ser.validated_data.get("machine"),
            )
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        wo.refresh_from_db()
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Production started",
        )

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        wo = self.get_object()
        ser = PauseSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            ProductionExecutionService.pause(wo, request.user, ser.validated_data["reason"])
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        wo.refresh_from_db()
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Production paused",
        )

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        wo = self.get_object()
        try:
            ProductionExecutionService.resume(wo, request.user)
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        wo.refresh_from_db()
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Production resumed",
        )

    @action(detail=True, methods=["post"], url_path="record-progress")
    def record_progress(self, request, pk=None):
        wo = self.get_object()
        ser = ProgressSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            ProductionExecutionService.record_progress(wo, request.user, **ser.validated_data)
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        wo.refresh_from_db()
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Progress recorded",
        )

    @action(detail=True, methods=["post"], url_path="record-consumption")
    def record_consumption(self, request, pk=None):
        wo = self.get_object()
        ser = ConsumptionSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            ProductionExecutionService.record_consumption(
                wo, request.user, ser.validated_data["lines"]
            )
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        wo.refresh_from_db()
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Material consumption recorded (pending approval)",
        )

    @action(detail=True, methods=["post"], url_path="submit-completion")
    def submit_completion(self, request, pk=None):
        wo = self.get_object()
        ser = SubmitCompletionSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        try:
            ProductionExecutionService.submit_completion(wo, request.user, **ser.validated_data)
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        wo.refresh_from_db()
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Completion submitted for production approval",
        )

    @action(detail=True, methods=["post"], url_path="approve-production")
    def approve_production(self, request, pk=None):
        wo = self.get_object()
        try:
            ProductionExecutionService.approve_production(wo, request.user)
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        wo.refresh_from_db()
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Production approved — awaiting store receipt",
        )

    @action(detail=True, methods=["post"], url_path="store-receipt")
    def store_receipt(self, request, pk=None):
        wo = self.get_object()
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
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        wo.refresh_from_db()
        return api_response(
            data=WorkOrderSerializer(wo, context={"request": request}).data,
            message="Finished goods received into inventory",
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        wo = self.get_object()
        if wo.execution_workflow:
            return api_error(message="Use submit completion for execution workflow work orders.")
        if is_machine_operator(request.user):
            return api_error(message="Machine operators cannot complete work orders directly.")
        if wo.status != WorkOrder.STATUS_IN_PROGRESS:
            return api_error(message="Only in-progress work orders can be completed.")
        try:
            ProductionService.complete_work_order(wo)
        except ValueError as e:
            return api_error(message=str(e))
        return api_response(
            data=WorkOrderSerializer(wo).data,
            message="Work order completed",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        wo = self.get_object()
        if wo.status in (WorkOrder.STATUS_COMPLETED, WorkOrder.STATUS_CANCELLED):
            return api_error(message="This work order cannot be cancelled.")
        wo.status = WorkOrder.STATUS_CANCELLED
        wo.save(update_fields=["status", "updated_at"])
        return api_response(
            data=WorkOrderSerializer(wo).data,
            message="Work order cancelled",
        )


class OutputRecordViewSet(ProductionViewSetMixin, viewsets.ModelViewSet):
    queryset = OutputRecord.objects.select_related(
        "work_order__product", "operator", "supervisor", "quality_checked_by"
    ).all()
    serializer_class = OutputRecordSerializer
    filterset_class = OutputRecordFilter
    search_fields = ["batch_number", "work_order__wo_number"]
    ordering_fields = ["date", "created_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_create_message(self):
        return "Output recorded — finished goods added to inventory"

    def get_update_message(self):
        return "Output record updated"

    @action(detail=True, methods=["post"])
    def qc(self, request, pk=None):
        record = self.get_object()
        if record.quality_checked:
            return api_error(message="QC already performed.")
        ser = QCCheckSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        record.quality_checked = True
        record.qc_result = ser.validated_data["qc_result"]
        record.qc_notes = ser.validated_data.get("qc_notes", "")
        record.quality_checked_by = request.user
        record.save(
            update_fields=[
                "quality_checked",
                "qc_result",
                "qc_notes",
                "quality_checked_by",
                "updated_at",
            ]
        )
        return api_response(
            data=OutputRecordSerializer(record).data,
            message="QC check recorded",
        )


class MachineViewSet(ProductionViewSetMixin, viewsets.ModelViewSet):
    queryset = Machine.objects.all()
    serializer_class = MachineSerializer
    filterset_class = MachineFilter
    search_fields = ["machine_code", "name"]
    ordering_fields = ["machine_code", "next_service_date"]

    def get_create_message(self):
        return "Machine created"

    def get_update_message(self):
        return "Machine updated"

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        machine = self.get_object()
        data = ProductionService.machine_history_payload(
            machine,
            request,
            usage_serializer=MachineUsageSerializer,
            service_serializer=MachineServiceRecordSerializer,
        )
        return api_response(data=data)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser, JSONParser])
    def breakdown(self, request, pk=None):
        machine = self.get_object()
        notes = request.data.get("notes") or request.POST.get("notes", "")
        if not str(notes).strip():
            return api_error(message="Breakdown description is required.")
        photo = request.FILES.get("photo")
        if photo and photo.size > 10 * 1024 * 1024:
            return api_error(message="Photo must be 10 MB or smaller.")
        wo = None
        wo_id = request.data.get("work_order") or request.POST.get("work_order")
        if wo_id:
            wo = WorkOrder.objects.filter(pk=wo_id).first()
        record = ProductionExecutionService.report_machine_breakdown(
            machine,
            request.user,
            str(notes).strip(),
            photo=photo,
            work_order=wo,
        )
        return api_response(
            data={
                **MachineSerializer(machine).data,
                "breakdown_id": record.id,
                "photo_url": _absolute_media_url(request, record.photo),
            },
            message="Breakdown reported",
        )

    @action(detail=True, methods=["post"], url_path="runtime-status")
    def runtime_status(self, request, pk=None):
        machine = self.get_object()
        ser = MachineRuntimeSerializer(data=request.data)
        if not ser.is_valid():
            return api_error(errors=ser.errors)
        wo = None
        wo_id = ser.validated_data.get("work_order")
        if wo_id:
            wo = WorkOrder.objects.filter(pk=wo_id).first()
        try:
            ProductionExecutionService.update_machine_runtime(
                machine,
                request.user,
                condition=ser.validated_data["condition"],
                notes=ser.validated_data.get("notes", ""),
                work_order=wo,
            )
        except (ValueError, PermissionError) as e:
            return api_error(message=str(e))
        machine.refresh_from_db()
        return api_response(
            data=MachineSerializer(machine).data,
            message="Machine status updated",
        )


class MachineUsageViewSet(ProductionViewSetMixin, viewsets.ModelViewSet):
    queryset = MachineUsage.objects.select_related(
        "machine", "work_order", "operator"
    ).all()
    serializer_class = MachineUsageSerializer
    filterset_class = MachineUsageFilter
    ordering_fields = ["start_time", "hours_used"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_create_message(self):
        return "Machine usage logged"


class ProductionDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        if request.query_params.get("view") == "operator":
            return api_response(data=ProductionExecutionService.operator_dashboard(request.user))
        data = ProductionService.dashboard_data()
        wo_ids = data.pop("active_wo_ids", [])
        machine_ids = data.pop("machine_ids", [])
        data["active_wos"] = WorkOrderSerializer(
            WorkOrder.objects.filter(id__in=wo_ids).select_related(
                "product", "operator", "bom"
            ),
            many=True,
        ).data
        data["machine_status"] = MachineSerializer(
            Machine.objects.filter(id__in=machine_ids),
            many=True,
        ).data
        return api_response(data=data)


class ProductionReportsView(APIView):
    """Production analytics — operator performance, downtime, utilization."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.production.production_permissions import is_machine_operator

        if is_machine_operator(request.user) and not request.user.is_superuser:
            return api_error(message="Production reports require supervisor access.")
        month = request.query_params.get("month")
        report_type = request.query_params.get("type", "all")
        builders = {
            "operator": lambda: build_operator_performance_report(month=month),
            "downtime": lambda: build_downtime_report(month=month),
            "utilization": lambda: build_machine_utilization_report(month=month),
            "completed": lambda: build_completed_work_orders_report(month=month),
            "all": lambda: build_production_reports_bundle(month=month),
        }
        builder = builders.get(report_type)
        if not builder:
            return api_error(message="Invalid report type.")
        return api_response(data=builder())
