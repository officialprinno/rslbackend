"""Finance API URL configuration."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.views import (
    AccountViewSet,
    BankAccountViewSet,
    BankReconciliationViewSet,
    BudgetViewSet,
    FinanceDashboardViewSet,
    FinanceReportViewSet,
    JournalEntryViewSet,
    PayableViewSet,
    ReceivableViewSet,
    TaxSettingViewSet,
    TaxViewSet,
)

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="account")
router.register("journal-entries", JournalEntryViewSet, basename="journal-entry")
router.register("bank-accounts", BankAccountViewSet, basename="bank-account")
router.register("reconciliations", BankReconciliationViewSet, basename="reconciliation")
router.register("budgets", BudgetViewSet, basename="budget")
router.register("tax-settings", TaxSettingViewSet, basename="tax-setting")
router.register("receivables", ReceivableViewSet, basename="receivable")
router.register("payables", PayableViewSet, basename="payable")
router.register("dashboard", FinanceDashboardViewSet, basename="finance-dashboard")
router.register("reports", FinanceReportViewSet, basename="finance-report")
router.register("tax", TaxViewSet, basename="tax")

urlpatterns = [
    path("", include(router.urls)),
]
