"""Inventory URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.inventory.seed_views import InventoryMasterSeedView
from apps.inventory.production_receipt_views import (
    ProductionReceiptQueueView,
    ProductionReceiptReceiveView,
)
from apps.inventory.extended_views import (
    CostAllocationReportView,
    DepartmentRequestViewSet,
    GoodsIssueNoteViewSet,
    InternalConsumptionReportView,
    InventoryDashboardView,
    InventoryValuationView,
    ReorderSuggestionsView,
    StockBatchViewSet,
    StockTakeViewSet,
    StockTransferViewSet,
)
from apps.inventory.views import (
    ItemCategoryViewSet,
    ItemSerialNumberViewSet,
    ItemViewSet,
    StockAdjustmentViewSet,
    StockAlertViewSet,
    StockMovementViewSet,
    StockViewSet,
    WarehouseViewSet,
)

router = DefaultRouter()
router.register("categories", ItemCategoryViewSet, basename="item-category")
router.register("items", ItemViewSet, basename="item")
router.register("warehouses", WarehouseViewSet, basename="warehouse")
router.register("stock", StockViewSet, basename="stock")
router.register("movements", StockMovementViewSet, basename="stock-movement")
router.register("adjustments", StockAdjustmentViewSet, basename="stock-adjustment")
router.register("serial-numbers", ItemSerialNumberViewSet, basename="item-serial-number")
router.register("alerts", StockAlertViewSet, basename="stock-alert")
router.register("batches", StockBatchViewSet, basename="stock-batch")
router.register("transfers", StockTransferViewSet, basename="stock-transfer")
router.register("department-requests", DepartmentRequestViewSet, basename="department-request")
router.register("gins", GoodsIssueNoteViewSet, basename="goods-issue-note")
router.register("stock-takes", StockTakeViewSet, basename="stock-take")

urlpatterns = [
    path("seed/master/", InventoryMasterSeedView.as_view(), name="inventory-master-seed"),
    path("dashboard/", InventoryDashboardView.as_view(), name="inventory-dashboard"),
    path("valuation/", InventoryValuationView.as_view(), name="inventory-valuation"),
    path("reorder-suggestions/", ReorderSuggestionsView.as_view(), name="reorder-suggestions"),
    path(
        "reports/internal-consumption/",
        InternalConsumptionReportView.as_view(),
        name="internal-consumption-report",
    ),
    path(
        "reports/cost-allocation/",
        CostAllocationReportView.as_view(),
        name="cost-allocation-report",
    ),
    path(
        "production-receipts/",
        ProductionReceiptQueueView.as_view(),
        name="production-receipt-queue",
    ),
    path(
        "production-receipts/<int:wo_id>/receive/",
        ProductionReceiptReceiveView.as_view(),
        name="production-receipt-receive",
    ),
    path("", include(router.urls)),
]
