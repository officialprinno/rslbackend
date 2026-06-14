"""Finance API viewsets."""

from datetime import datetime

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.core.responses import api_error, api_response
from apps.finance.filters import (
    AccountFilter,
    BankAccountFilter,
    BankReconciliationFilter,
    BudgetFilter,
    JournalEntryFilter,
    TaxSettingFilter,
)
from apps.finance.mixins import FinanceViewSetMixin
from apps.finance.models import (
    Account,
    BankAccount,
    BankReconciliation,
    Budget,
    JournalEntry,
    TaxSetting,
)
from apps.finance.serializers import (
    AccountSerializer,
    BankAccountSerializer,
    BankReconciliationSerializer,
    BudgetSerializer,
    JournalEntrySerializer,
    SupplierPaymentSerializer,
    TaxSettingSerializer,
)
from apps.finance.services import FinanceService
from apps.finance.utils import generate_account_code
from apps.procurement.models import InvoicePayment, SupplierInvoice
from apps.sales.models import Customer, SalesInvoice


class AccountViewSet(FinanceViewSetMixin, viewsets.ModelViewSet):
    queryset = Account.objects.select_related("parent").all()
    serializer_class = AccountSerializer
    filterset_class = AccountFilter
    search_fields = ["account_code", "account_name"]
    ordering_fields = ["account_code", "account_name"]

    def get_create_message(self):
        return "Account created"

    def get_update_message(self):
        return "Account updated"

    @action(detail=False, methods=["get"], url_path="next-code")
    def next_code(self, request):
        account_type = request.query_params.get("account_type")
        if not account_type:
            return api_error(message="account_type is required.")
        parent_id = request.query_params.get("parent")
        parent = None
        if parent_id:
            parent = Account.objects.filter(pk=parent_id).first()
            if not parent:
                return api_error(message="Parent account not found.")
        try:
            code = generate_account_code(account_type, parent)
        except ValueError as exc:
            return api_error(message=str(exc))
        return api_response(data={"account_code": code, "account_type": account_type})

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        account = self.get_object()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        entries = FinanceService.account_ledger(account.id, date_from, date_to)
        return api_response(data=entries)

    def list(self, request, *args, **kwargs):
        tree = request.query_params.get("tree")
        if tree == "true":
            accounts = Account.objects.filter(is_active=True).select_related("parent")
            account_type = request.query_params.get("account_type")
            if account_type:
                accounts = accounts.filter(account_type=account_type)
            data = FinanceService.build_account_tree(accounts)
            return api_response(data=data)
        return super().list(request, *args, **kwargs)


class JournalEntryViewSet(FinanceViewSetMixin, viewsets.ModelViewSet):
    queryset = JournalEntry.objects.select_related(
        "currency", "posted_by", "created_by"
    ).prefetch_related("lines__account", "lines__department")
    serializer_class = JournalEntrySerializer
    filterset_class = JournalEntryFilter
    search_fields = ["je_number", "description", "reference_id"]
    ordering_fields = ["date", "je_number", "created_at"]

    def get_create_message(self):
        return "Journal entry created"

    def get_update_message(self):
        return "Journal entry updated"

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status != JournalEntry.STATUS_DRAFT:
            return api_error(message="Only draft entries can be deleted.")
        instance.delete()
        return api_response(message="Journal entry deleted")

    @action(detail=True, methods=["post"], url_path="post")
    def post_entry(self, request, pk=None):
        entry = self.get_object()
        try:
            FinanceService.post_journal_entry(entry, request.user)
        except ValueError as exc:
            return api_error(message=str(exc))
        return api_response(
            data=JournalEntrySerializer(entry).data,
            message="Journal entry posted",
        )

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        entry = self.get_object()
        try:
            reversal = FinanceService.reverse_journal_entry(entry, request.user)
        except ValueError as exc:
            return api_error(message=str(exc))
        return api_response(
            data=JournalEntrySerializer(reversal).data,
            message="Reversing entry created",
            status=status.HTTP_201_CREATED,
        )


class BankAccountViewSet(FinanceViewSetMixin, viewsets.ModelViewSet):
    queryset = BankAccount.objects.select_related("currency", "gl_account").all()
    serializer_class = BankAccountSerializer
    filterset_class = BankAccountFilter
    search_fields = ["bank_name", "account_number", "account_name"]
    ordering_fields = ["bank_name"]

    def get_create_message(self):
        return "Bank account created"

    def get_update_message(self):
        return "Bank account updated"


class BankReconciliationViewSet(FinanceViewSetMixin, viewsets.ModelViewSet):
    queryset = BankReconciliation.objects.select_related(
        "bank_account", "reconciled_by"
    ).prefetch_related("statement_lines", "matches__journal_line__account")
    serializer_class = BankReconciliationSerializer
    filterset_class = BankReconciliationFilter
    ordering_fields = ["period_year", "period_month"]

    def get_create_message(self):
        return "Reconciliation created"

    def get_update_message(self):
        return "Reconciliation updated"

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        recon = self.get_object()
        try:
            FinanceService.complete_reconciliation(recon, request.user)
        except ValueError as exc:
            return api_error(message=str(exc))
        return api_response(
            data=BankReconciliationSerializer(recon).data,
            message="Reconciliation completed",
        )


class BudgetViewSet(FinanceViewSetMixin, viewsets.ModelViewSet):
    queryset = Budget.objects.select_related("department", "account").all()
    serializer_class = BudgetSerializer
    filterset_class = BudgetFilter
    search_fields = ["name", "department__name", "account__account_name"]
    ordering_fields = ["financial_year", "department__name"]

    def get_create_message(self):
        return "Budget created"

    def get_update_message(self):
        return "Budget updated"

    @action(detail=False, methods=["get"], url_path="summary")
    def budget_summary(self, request):
        from django.db.models import Sum

        year = int(request.query_params.get("financial_year", timezone.now().year))
        budgets = Budget.objects.filter(is_active=True, financial_year=year).select_related(
            "department", "account"
        )
        dept_map = {}
        for b in budgets:
            actual = FinanceService.budget_actual(b.account_id, b.department_id, year)
            did = b.department_id
            if did not in dept_map:
                dept_map[did] = {
                    "department_id": did,
                    "department_name": b.department.name,
                    "total_budgeted": 0,
                    "total_actual": 0,
                    "top_expenses": [],
                }
            dept_map[did]["total_budgeted"] += float(b.amount_budgeted)
            dept_map[did]["total_actual"] += float(actual)
            dept_map[did]["top_expenses"].append(
                {"account": b.account.account_name, "amount": str(actual)}
            )
        result = []
        for row in dept_map.values():
            row["top_expenses"] = sorted(
                row["top_expenses"], key=lambda x: float(x["amount"]), reverse=True
            )[:3]
            row["total_budgeted"] = str(row["total_budgeted"])
            row["total_actual"] = str(row["total_actual"])
            result.append(row)
        return api_response(data=result)


class TaxSettingViewSet(FinanceViewSetMixin, viewsets.ModelViewSet):
    queryset = TaxSetting.objects.all()
    serializer_class = TaxSettingSerializer
    filterset_class = TaxSettingFilter
    search_fields = ["name"]
    ordering_fields = ["name"]

    def get_update_message(self):
        return "Tax setting updated"


class ReceivableViewSet(FinanceViewSetMixin, viewsets.ViewSet):
    """Accounts receivable aging and statements."""

    def list(self, request):
        as_of = request.query_params.get("as_of")
        search = request.query_params.get("search")
        as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else None
        aging = FinanceService.ar_aging(as_of_date, search)
        totals = {
            "total_outstanding": str(sum(r["total_outstanding"] for r in aging)),
            "current": str(sum(r["current"] for r in aging)),
            "days_1_30": str(sum(r["days_1_30"] for r in aging)),
            "days_31_60": str(sum(r["days_31_60"] for r in aging)),
            "days_61_90": str(sum(r["days_61_90"] for r in aging)),
            "days_90_plus": str(sum(r["days_90_plus"] for r in aging)),
        }
        serialized = []
        for row in aging:
            serialized.append({k: str(v) if hasattr(v, "quantize") else v for k, v in row.items()})
        return api_response(data={"summary": totals, "aging": serialized})

    @action(detail=False, methods=["get"], url_path="aging")
    def aging(self, request):
        return self.list(request)

    @action(detail=True, methods=["get"], url_path="statement")
    def statement(self, request, pk=None):
        customer = Customer.objects.filter(pk=pk).first()
        if not customer:
            return api_error(message="Customer not found.", status=status.HTTP_404_NOT_FOUND)
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        invoices = SalesInvoice.objects.filter(
            customer=customer, is_active=True
        ).order_by("invoice_date")
        if date_from:
            invoices = invoices.filter(invoice_date__gte=date_from)
        if date_to:
            invoices = invoices.filter(invoice_date__lte=date_to)

        from decimal import Decimal

        opening = Decimal("0")
        transactions = []
        balance = opening
        for inv in invoices:
            balance += inv.total_amount
            transactions.append(
                {
                    "date": inv.invoice_date.isoformat(),
                    "reference": inv.invoice_number,
                    "description": f"Invoice {inv.invoice_number}",
                    "debit": str(inv.total_amount),
                    "credit": "0",
                    "balance": str(balance),
                }
            )
            if inv.paid_amount > 0:
                balance -= inv.paid_amount
                transactions.append(
                    {
                        "date": inv.invoice_date.isoformat(),
                        "reference": inv.invoice_number,
                        "description": f"Payment — {inv.invoice_number}",
                        "debit": "0",
                        "credit": str(inv.paid_amount),
                        "balance": str(balance),
                    }
                )
        return api_response(
            data={
                "customer_id": customer.id,
                "customer_name": customer.name,
                "date_from": date_from,
                "date_to": date_to,
                "opening_balance": str(opening),
                "closing_balance": str(balance),
                "transactions": transactions,
            }
        )


class PayableViewSet(FinanceViewSetMixin, viewsets.ViewSet):
    """Accounts payable aging and payments."""

    def list(self, request):
        as_of = request.query_params.get("as_of")
        search = request.query_params.get("search")
        as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date() if as_of else None
        aging = FinanceService.ap_aging(as_of_date, search)
        totals = {
            "total_outstanding": str(sum(r["total_outstanding"] for r in aging)),
            "current": str(sum(r["current"] for r in aging)),
            "days_1_30": str(sum(r["days_1_30"] for r in aging)),
            "days_31_60": str(sum(r["days_31_60"] for r in aging)),
            "days_61_90": str(sum(r["days_61_90"] for r in aging)),
            "days_90_plus": str(sum(r["days_90_plus"] for r in aging)),
        }
        serialized = []
        for row in aging:
            serialized.append({k: str(v) if hasattr(v, "quantize") else v for k, v in row.items()})
        return api_response(data={"summary": totals, "aging": serialized})

    @action(detail=False, methods=["get"], url_path="aging")
    def aging(self, request):
        return self.list(request)

    @action(detail=False, methods=["get"], url_path="upcoming")
    def upcoming(self, request):
        days = int(request.query_params.get("days", 14))
        data = FinanceService.upcoming_payments(days)
        return api_response(data=data)

    @action(detail=False, methods=["post"], url_path="payments")
    def make_payment(self, request):
        serializer = SupplierPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        data = serializer.validated_data
        invoice = data["invoice_obj"]
        payment = InvoicePayment.objects.create(
            invoice=invoice,
            amount=data["amount"],
            payment_date=data["payment_date"],
            payment_method=data["payment_method"],
            reference=data.get("reference", ""),
            bank=str(data.get("bank_account", "")),
            recorded_by=request.user,
        )
        invoice.paid_amount += data["amount"]
        if invoice.paid_amount >= invoice.total_amount:
            invoice.status = SupplierInvoice.STATUS_PAID
        else:
            invoice.status = SupplierInvoice.STATUS_PARTIAL
        invoice.save()
        return api_response(
            data={"id": payment.id, "invoice_id": invoice.id, "amount": str(payment.amount)},
            message="Payment recorded",
            status=status.HTTP_201_CREATED,
        )


class FinanceDashboardViewSet(FinanceViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        data = FinanceService.dashboard()
        recent = data.pop("recent_transactions")
        data["recent_transactions"] = JournalEntrySerializer(recent, many=True).data
        for key in [
            "revenue_month",
            "expenses_month",
            "net_profit_month",
            "accounts_receivable",
            "accounts_payable",
            "cash_and_bank",
            "overdue_receivables_amount",
            "overdue_payables_amount",
        ]:
            if key in data:
                data[key] = str(data[key])
        return api_response(data=data)


class FinanceReportViewSet(FinanceViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="income-statement")
    def income_statement(self, request):
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if not date_from or not date_to:
            return api_error(message="date_from and date_to are required.")
        data = FinanceService.income_statement(
            datetime.strptime(date_from, "%Y-%m-%d").date(),
            datetime.strptime(date_to, "%Y-%m-%d").date(),
        )
        return api_response(data=data)

    @action(detail=False, methods=["get"], url_path="balance-sheet")
    def balance_sheet(self, request):
        as_of = request.query_params.get("as_of_date")
        if not as_of:
            return api_error(message="as_of_date is required.")
        data = FinanceService.balance_sheet(datetime.strptime(as_of, "%Y-%m-%d").date())
        return api_response(data=data)

    @action(detail=False, methods=["get"], url_path="cash-flow")
    def cash_flow(self, request):
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if not date_from or not date_to:
            return api_error(message="date_from and date_to are required.")
        cash_codes = ["1101", "1102", "1103"]
        inflows = "0"
        outflows = "0"
        return api_response(
            data={
                "period_from": date_from,
                "period_to": date_to,
                "operating_inflows": inflows,
                "operating_outflows": outflows,
                "net_cash_flow": "0",
            }
        )

    @action(detail=False, methods=["get"], url_path="general-ledger")
    def general_ledger(self, request):
        account_id = request.query_params.get("account")
        if not account_id:
            return api_error(message="account is required.")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        entries = FinanceService.account_ledger(account_id, date_from, date_to)
        return api_response(data=entries)


class TaxViewSet(FinanceViewSetMixin, viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"], url_path="vat")
    def vat(self, request):
        month = int(request.query_params.get("month", timezone.now().month))
        year = int(request.query_params.get("year", timezone.now().year))
        return api_response(data=FinanceService.vat_summary(month, year))

    @action(detail=False, methods=["get"], url_path="paye")
    def paye(self, request):
        month = int(request.query_params.get("month", timezone.now().month))
        year = int(request.query_params.get("year", timezone.now().year))
        return api_response(data=FinanceService.paye_summary(month, year))

    @action(detail=False, methods=["get"], url_path="nssf")
    def nssf(self, request):
        month = int(request.query_params.get("month", timezone.now().month))
        year = int(request.query_params.get("year", timezone.now().year))
        return api_response(data=FinanceService.nssf_summary(month, year))

    @action(detail=False, methods=["get", "patch"], url_path="settings")
    def tax_settings(self, request):
        if request.method == "GET":
            qs = TaxSetting.objects.filter(is_active=True)
            return api_response(data=TaxSettingSerializer(qs, many=True).data)
        setting_id = request.data.get("id")
        if not setting_id:
            return api_error(message="id is required.")
        setting = TaxSetting.objects.filter(pk=setting_id).first()
        if not setting:
            return api_error(message="Tax setting not found.")
        serializer = TaxSettingSerializer(setting, data=request.data, partial=True)
        if not serializer.is_valid():
            return api_error(errors=serializer.errors)
        serializer.save()
        return api_response(data=serializer.data, message="Tax setting updated")
