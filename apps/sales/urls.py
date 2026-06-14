"""Sales API URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.sales.views import (
    CreditNoteViewSet,
    CustomerViewSet,
    InvoiceViewSet,
    PaymentViewSet,
    QuotationViewSet,
    SalesDashboardViewSet,
    SalesOrderViewSet,
)

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("quotations", QuotationViewSet, basename="quotation")
router.register("orders", SalesOrderViewSet, basename="sales-order")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")
router.register("credit-notes", CreditNoteViewSet, basename="credit-note")
router.register("dashboard", SalesDashboardViewSet, basename="sales-dashboard")

urlpatterns = [
    path("", include(router.urls)),
]
