"""Core API views."""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.models import AuditLog, Currency
from apps.core.multi_dept_dashboard import build_multi_department_dashboard
from apps.core.responses import api_response
from apps.core.serializers import AuditLogSerializer, CurrencySerializer


class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return api_response(data=response.data)


class MultiDepartmentDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dept = request.query_params.get("department", "all")
        return api_response(data=build_multi_department_dashboard(request.user, dept))


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only audit trail for governance and internal audit."""

    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user").order_by("-created_at")
        module = self.request.query_params.get("module")
        if module:
            qs = qs.filter(module=module)
        record_id = self.request.query_params.get("record_id")
        if record_id:
            qs = qs.filter(record_id=record_id)
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return api_response(data=response.data)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return api_response(data=response.data)
