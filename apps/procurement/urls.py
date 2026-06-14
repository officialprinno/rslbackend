"""Procurement API URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.procurement.views import (
    GRNViewSet,
    ProcurementDashboardViewSet,
    PurchaseOrderViewSet,
    PurchaseRequisitionViewSet,
    QuotationViewSet,
    RFQViewSet,
    SupplierInvoiceViewSet,
    SupplierViewSet,
)

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("requisitions", PurchaseRequisitionViewSet, basename="purchase-requisition")
router.register("rfq", RFQViewSet, basename="rfq")
router.register("quotations", QuotationViewSet, basename="quotation")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("grn", GRNViewSet, basename="grn")
router.register("supplier-invoices", SupplierInvoiceViewSet, basename="supplier-invoice")
router.register("dashboard", ProcurementDashboardViewSet, basename="procurement-dashboard")

urlpatterns = [
    path("", include(router.urls)),
]
