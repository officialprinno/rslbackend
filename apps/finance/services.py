"""Finance business logic and report generation."""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.finance.models import (
    Account,
    BankAccount,
    BankReconciliation,
    BankStatementLine,
    Budget,
    JournalEntry,
    JournalLine,
    ReconciliationMatch,
    TaxSetting,
    VATPeriod,
)
from apps.finance.utils import generate_je_number
from apps.procurement.models import SupplierInvoice
from apps.sales.models import SalesInvoice


class FinanceService:
    """Core finance operations."""

    NORMAL_DEBIT_TYPES = {
        Account.TYPE_ASSET,
        Account.TYPE_EXPENSE,
    }

    @staticmethod
    def account_balance(account, as_of=None):
        """Net balance for an account from posted journal lines."""
        qs = JournalLine.objects.filter(
            journal_entry__status=JournalEntry.STATUS_POSTED,
            account=account,
        )
        if as_of:
            qs = qs.filter(journal_entry__date__lte=as_of)
        totals = qs.aggregate(
            debits=Sum("debit_amount"),
            credits=Sum("credit_amount"),
        )
        debits = totals["debits"] or Decimal("0")
        credits = totals["credits"] or Decimal("0")
        if account.account_type in FinanceService.NORMAL_DEBIT_TYPES:
            balance = debits - credits
            balance_type = "DEBIT" if balance >= 0 else "CREDIT"
        else:
            balance = credits - debits
            balance_type = "CREDIT" if balance >= 0 else "DEBIT"
        return abs(balance), balance_type

    @staticmethod
    def build_account_tree(accounts=None):
        """Return flat accounts with balance for tree rendering."""
        if accounts is None:
            accounts = Account.objects.filter(is_active=True).select_related("parent")
        result = []
        for acc in accounts:
            balance, balance_type = FinanceService.account_balance(acc)
            result.append(
                {
                    "id": acc.id,
                    "account_code": acc.account_code,
                    "account_name": acc.account_name,
                    "account_type": acc.account_type,
                    "parent_id": acc.parent_id,
                    "parent_name": acc.parent.account_name if acc.parent else None,
                    "description": acc.description,
                    "balance": str(balance),
                    "balance_type": balance_type,
                    "is_active": acc.is_active,
                }
            )
        return result

    @staticmethod
    def je_totals(entry):
        debits = sum((l.debit_amount for l in entry.lines.all()), Decimal("0"))
        credits = sum((l.credit_amount for l in entry.lines.all()), Decimal("0"))
        return debits, credits

    @staticmethod
    def validate_balanced(entry):
        debits, credits = FinanceService.je_totals(entry)
        return debits == credits and debits > 0

    @staticmethod
    @transaction.atomic
    def post_journal_entry(entry, user):
        if entry.status != JournalEntry.STATUS_DRAFT:
            raise ValueError("Only draft entries can be posted.")
        if not FinanceService.validate_balanced(entry):
            raise ValueError("Journal entry is not balanced.")
        entry.status = JournalEntry.STATUS_POSTED
        entry.posted_by = user
        entry.posted_at = timezone.now()
        entry.save()
        FinanceService._update_bank_balances(entry)
        return entry

    @staticmethod
    @transaction.atomic
    def reverse_journal_entry(entry, user):
        if entry.status != JournalEntry.STATUS_POSTED:
            raise ValueError("Only posted entries can be reversed.")
        reversal = JournalEntry.objects.create(
            je_number=generate_je_number(),
            date=timezone.now().date(),
            reference_type=JournalEntry.REF_MANUAL,
            reference_id=entry.je_number,
            description=f"Reversal of {entry.je_number}: {entry.description}",
            currency=entry.currency,
            exchange_rate=entry.exchange_rate,
            status=JournalEntry.STATUS_POSTED,
            posted_by=user,
            posted_at=timezone.now(),
            reversed_entry=entry,
            created_by=user,
        )
        for line in entry.lines.all():
            JournalLine.objects.create(
                journal_entry=reversal,
                account=line.account,
                description=f"Reversal: {line.description}",
                department=line.department,
                debit_amount=line.credit_amount,
                credit_amount=line.debit_amount,
            )
        entry.status = JournalEntry.STATUS_REVERSED
        entry.save()
        FinanceService._update_bank_balances(reversal)
        return reversal

    @staticmethod
    def _update_bank_balances(entry):
        for bank in BankAccount.objects.filter(gl_account__in=entry.lines.values_list("account_id", flat=True)):
            balance, _ = FinanceService.account_balance(bank.gl_account)
            bank.current_balance = balance
            bank.save(update_fields=["current_balance", "updated_at"])

    @staticmethod
    def _aging_bucket(days_overdue):
        if days_overdue <= 0:
            return "current"
        if days_overdue <= 30:
            return "days_1_30"
        if days_overdue <= 60:
            return "days_31_60"
        if days_overdue <= 90:
            return "days_61_90"
        return "days_90_plus"

    @staticmethod
    def ar_aging(as_of=None, search=None):
        as_of = as_of or timezone.now().date()
        invoices = SalesInvoice.objects.filter(
            is_active=True,
            status__in=[
                SalesInvoice.STATUS_SENT,
                SalesInvoice.STATUS_PARTIAL,
                SalesInvoice.STATUS_OVERDUE,
            ],
        ).select_related("customer")
        if search:
            invoices = invoices.filter(customer__name__icontains=search)

        customers = {}
        for inv in invoices:
            balance = inv.balance
            if balance <= 0:
                continue
            cid = inv.customer_id
            if cid not in customers:
                customers[cid] = {
                    "customer_id": cid,
                    "customer_name": inv.customer.name,
                    "total_invoiced": Decimal("0"),
                    "total_paid": Decimal("0"),
                    "current": Decimal("0"),
                    "days_1_30": Decimal("0"),
                    "days_31_60": Decimal("0"),
                    "days_61_90": Decimal("0"),
                    "days_90_plus": Decimal("0"),
                    "total_outstanding": Decimal("0"),
                }
            row = customers[cid]
            row["total_invoiced"] += inv.total_amount
            row["total_paid"] += inv.paid_amount
            days = (as_of - inv.due_date).days
            bucket = FinanceService._aging_bucket(days)
            row[bucket] += balance
            row["total_outstanding"] += balance

        return list(customers.values())

    @staticmethod
    def ap_aging(as_of=None, search=None):
        as_of = as_of or timezone.now().date()
        invoices = SupplierInvoice.objects.filter(
            is_active=True,
            status__in=[
                SupplierInvoice.STATUS_PENDING,
                SupplierInvoice.STATUS_PARTIAL,
                SupplierInvoice.STATUS_OVERDUE,
            ],
        ).select_related("supplier")
        if search:
            invoices = invoices.filter(supplier__name__icontains=search)

        suppliers = {}
        for inv in invoices:
            balance = inv.balance
            if balance <= 0:
                continue
            sid = inv.supplier_id
            if sid not in suppliers:
                suppliers[sid] = {
                    "supplier_id": sid,
                    "supplier_name": inv.supplier.name,
                    "total_invoiced": Decimal("0"),
                    "total_paid": Decimal("0"),
                    "current": Decimal("0"),
                    "days_1_30": Decimal("0"),
                    "days_31_60": Decimal("0"),
                    "days_61_90": Decimal("0"),
                    "days_90_plus": Decimal("0"),
                    "total_outstanding": Decimal("0"),
                }
            row = suppliers[sid]
            row["total_invoiced"] += inv.total_amount
            row["total_paid"] += inv.paid_amount
            days = (as_of - inv.due_date).days
            bucket = FinanceService._aging_bucket(days)
            row[bucket] += balance
            row["total_outstanding"] += balance

        return list(suppliers.values())

    @staticmethod
    def upcoming_payments(days=14):
        today = timezone.now().date()
        end = today + timedelta(days=days)
        invoices = SupplierInvoice.objects.filter(
            is_active=True,
            three_way_matched=True,
            status__in=[
                SupplierInvoice.STATUS_PENDING,
                SupplierInvoice.STATUS_PARTIAL,
                SupplierInvoice.STATUS_OVERDUE,
            ],
            due_date__gte=today,
            due_date__lte=end,
        ).select_related("supplier")
        return [
            {
                "invoice_id": inv.id,
                "invoice_number": inv.invoice_number,
                "supplier_id": inv.supplier_id,
                "supplier_name": inv.supplier.name,
                "due_date": inv.due_date.isoformat(),
                "amount": str(inv.balance),
                "payment_method": "BANK_TRANSFER",
                "three_way_matched": inv.three_way_matched,
            }
            for inv in invoices
            if inv.balance > 0
        ]

    @staticmethod
    def account_ledger(account_id, date_from=None, date_to=None):
        qs = JournalLine.objects.filter(
            account_id=account_id,
            journal_entry__status=JournalEntry.STATUS_POSTED,
        ).select_related("journal_entry", "account")
        if date_from:
            qs = qs.filter(journal_entry__date__gte=date_from)
        if date_to:
            qs = qs.filter(journal_entry__date__lte=date_to)
        qs = qs.order_by("journal_entry__date", "id")
        running = Decimal("0")
        entries = []
        for line in qs:
            running += line.debit_amount - line.credit_amount
            entries.append(
                {
                    "date": line.journal_entry.date.isoformat(),
                    "je_number": line.journal_entry.je_number,
                    "description": line.description or line.journal_entry.description,
                    "debit": str(line.debit_amount),
                    "credit": str(line.credit_amount),
                    "balance": str(running),
                }
            )
        return entries

    @staticmethod
    def budget_actual(account_id, department_id, financial_year):
        qs = JournalLine.objects.filter(
            account_id=account_id,
            department_id=department_id,
            journal_entry__status=JournalEntry.STATUS_POSTED,
            journal_entry__date__year=financial_year,
        )
        return qs.aggregate(total=Sum("debit_amount"))["total"] or Decimal("0")

    @staticmethod
    def budget_status(budgeted, actual):
        if budgeted <= 0:
            return "UNDER"
        pct = (actual / budgeted) * 100
        if pct > 100:
            return "EXCEEDED"
        if pct >= 80:
            return "NEAR_LIMIT"
        return "UNDER"

    @staticmethod
    def dashboard():
        today = timezone.now().date()
        month_start = today.replace(day=1)

        revenue_accounts = Account.objects.filter(
            account_type=Account.TYPE_REVENUE, is_active=True
        )
        expense_accounts = Account.objects.filter(
            account_type=Account.TYPE_EXPENSE, is_active=True
        )

        def period_total(accounts, start, end):
            total = Decimal("0")
            for acc in accounts:
                qs = JournalLine.objects.filter(
                    account=acc,
                    journal_entry__status=JournalEntry.STATUS_POSTED,
                    journal_entry__date__gte=start,
                    journal_entry__date__lte=end,
                )
                credits = qs.aggregate(t=Sum("credit_amount"))["t"] or Decimal("0")
                debits = qs.aggregate(t=Sum("debit_amount"))["t"] or Decimal("0")
                if acc.account_type == Account.TYPE_REVENUE:
                    total += credits - debits
                else:
                    total += debits - credits
            return total

        revenue_month = period_total(revenue_accounts, month_start, today)
        expenses_month = period_total(expense_accounts, month_start, today)

        ar_account = Account.objects.filter(account_code="1200").first()
        ap_account = Account.objects.filter(account_code="2101").first()
        ar_balance = FinanceService.account_balance(ar_account)[0] if ar_account else Decimal("0")
        ap_balance = FinanceService.account_balance(ap_account)[0] if ap_account else Decimal("0")

        cash_codes = ["1101", "1102", "1103"]
        cash_and_bank = Decimal("0")
        for code in cash_codes:
            acc = Account.objects.filter(account_code=code).first()
            if acc:
                cash_and_bank += FinanceService.account_balance(acc)[0]

        ar_aging = FinanceService.ar_aging(today)
        ap_aging = FinanceService.ap_aging(today)
        overdue_ar = [r for r in ar_aging if r["days_31_60"] + r["days_61_90"] + r["days_90_plus"] > 0]
        overdue_ap = [r for r in ap_aging if r["days_1_30"] + r["days_31_60"] + r["days_61_90"] + r["days_90_plus"] > 0]

        budgets_exceeded = 0
        for budget in Budget.objects.filter(is_active=True, financial_year=today.year):
            actual = FinanceService.budget_actual(budget.account_id, budget.department_id, budget.financial_year)
            if FinanceService.budget_status(budget.amount_budgeted, actual) == "EXCEEDED":
                budgets_exceeded += 1

        monthly_chart = []
        for i in range(5, -1, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            start = date(y, m, 1)
            if m == 12:
                end = date(y, 12, 31)
            else:
                end = date(y, m + 1, 1) - timedelta(days=1)
            monthly_chart.append(
                {
                    "month": start.strftime("%b %Y"),
                    "revenue": str(period_total(revenue_accounts, start, end)),
                    "expenses": str(period_total(expense_accounts, start, end)),
                }
            )

        revenue_breakdown = []
        for code, label in [("4001", "Trading"), ("4002", "Manufacturing")]:
            acc = Account.objects.filter(account_code=code).first()
            if acc:
                bal, _ = FinanceService.account_balance(acc)
                revenue_breakdown.append({"category": label, "amount": str(bal)})

        recent = JournalEntry.objects.filter(
            status=JournalEntry.STATUS_POSTED
        ).select_related("posted_by").prefetch_related("lines")[:10]

        unreconciled = JournalLine.objects.filter(
            account__bank_accounts__isnull=False,
            journal_entry__status=JournalEntry.STATUS_POSTED,
            is_reconciled=False,
        ).count()

        return {
            "revenue_month": str(revenue_month),
            "expenses_month": str(expenses_month),
            "net_profit_month": str(revenue_month - expenses_month),
            "accounts_receivable": str(ar_balance),
            "accounts_payable": str(ap_balance),
            "cash_and_bank": str(cash_and_bank),
            "overdue_receivables_count": len(overdue_ar),
            "overdue_receivables_amount": str(sum(r["total_outstanding"] for r in overdue_ar)),
            "overdue_payables_count": len(overdue_ap),
            "overdue_payables_amount": str(sum(r["total_outstanding"] for r in overdue_ap)),
            "budgets_exceeded": budgets_exceeded,
            "unreconciled_transactions": unreconciled,
            "monthly_chart": monthly_chart,
            "revenue_breakdown": revenue_breakdown,
            "recent_transactions": recent,
        }

    @staticmethod
    def income_statement(date_from, date_to):
        def lines_for_codes(codes):
            result = []
            total = Decimal("0")
            for code in codes:
                acc = Account.objects.filter(account_code=code).first()
                if not acc:
                    continue
                qs = JournalLine.objects.filter(
                    account=acc,
                    journal_entry__status=JournalEntry.STATUS_POSTED,
                    journal_entry__date__gte=date_from,
                    journal_entry__date__lte=date_to,
                )
                credits = qs.aggregate(t=Sum("credit_amount"))["t"] or Decimal("0")
                debits = qs.aggregate(t=Sum("debit_amount"))["t"] or Decimal("0")
                amount = credits - debits if acc.account_type == Account.TYPE_REVENUE else debits - credits
                result.append({"code": code, "name": acc.account_name, "amount": str(abs(amount))})
                total += abs(amount)
            return result, total

        trading_rev, _ = lines_for_codes(["4001"])
        mfg_rev, _ = lines_for_codes(["4002"])
        trading = Decimal(trading_rev[0]["amount"]) if trading_rev else Decimal("0")
        manufacturing = Decimal(mfg_rev[0]["amount"]) if mfg_rev else Decimal("0")
        total_revenue = trading + manufacturing

        expense_codes = ["5001", "5100", "5200", "5300"]
        expenses = []
        total_expenses = Decimal("0")
        for code in expense_codes:
            acc = Account.objects.filter(account_code=code).first()
            if not acc:
                continue
            qs = JournalLine.objects.filter(
                account=acc,
                journal_entry__status=JournalEntry.STATUS_POSTED,
                journal_entry__date__gte=date_from,
                journal_entry__date__lte=date_to,
            )
            debits = qs.aggregate(t=Sum("debit_amount"))["t"] or Decimal("0")
            credits = qs.aggregate(t=Sum("credit_amount"))["t"] or Decimal("0")
            amount = debits - credits
            expenses.append({"code": code, "name": acc.account_name, "amount": str(amount)})
            total_expenses += amount

        cogs = Decimal(expenses[0]["amount"]) if expenses else Decimal("0")
        gross_profit = total_revenue - cogs
        net_profit = total_revenue - total_expenses

        return {
            "period_from": date_from.isoformat(),
            "period_to": date_to.isoformat(),
            "trading_revenue": str(trading),
            "manufacturing_revenue": str(manufacturing),
            "total_revenue": str(total_revenue),
            "opening_inventory": "0",
            "purchases": str(cogs),
            "closing_inventory": "0",
            "total_cogs": str(cogs),
            "gross_profit": str(gross_profit),
            "gross_margin_percent": str(round(float(gross_profit / total_revenue * 100), 1)) if total_revenue else "0",
            "expenses": expenses[1:] if len(expenses) > 1 else expenses,
            "total_expenses": str(total_expenses),
            "net_profit": str(net_profit),
            "net_margin_percent": str(round(float(net_profit / total_revenue * 100), 1)) if total_revenue else "0",
        }

    @staticmethod
    def balance_sheet(as_of_date):
        def asset_lines(codes):
            lines = []
            total = Decimal("0")
            for code in codes:
                acc = Account.objects.filter(account_code=code).first()
                if not acc:
                    continue
                bal, _ = FinanceService.account_balance(acc, as_of_date)
                lines.append({"code": code, "name": acc.account_name, "amount": str(bal)})
                total += bal
            return lines, total

        current_assets, total_current = asset_lines(
            ["1101", "1102", "1103", "1200", "1300"]
        )
        fixed_assets, total_fixed = asset_lines(["1401", "1402"])
        total_assets = total_current + total_fixed

        current_liabilities, total_liabilities = asset_lines(["2101", "2200"])
        equity_lines, total_equity = asset_lines(["3001"])

        return {
            "as_of_date": as_of_date.isoformat(),
            "current_assets": current_assets,
            "total_current_assets": str(total_current),
            "fixed_assets": fixed_assets,
            "total_fixed_assets": str(total_fixed),
            "total_assets": str(total_assets),
            "current_liabilities": current_liabilities,
            "total_liabilities": str(total_liabilities),
            "equity": equity_lines,
            "total_equity": str(total_equity),
            "total_liabilities_equity": str(total_liabilities + total_equity),
            "is_balanced": abs(total_assets - (total_liabilities + total_equity)) < Decimal("0.01"),
        }

    @staticmethod
    def vat_summary(month, year):
        from apps.sales.models import SalesInvoice as SI
        from apps.procurement.models import SupplierInvoice as PI

        output_vat = SI.objects.filter(
            is_active=True,
            invoice_date__month=month,
            invoice_date__year=year,
            status__in=[SI.STATUS_SENT, SI.STATUS_PARTIAL, SI.STATUS_PAID, SI.STATUS_OVERDUE],
        ).aggregate(t=Sum("tax_amount"))["t"] or Decimal("0")

        input_vat = PI.objects.filter(
            is_active=True,
            invoice_date__month=month,
            invoice_date__year=year,
        ).aggregate(t=Sum("tax_amount"))["t"] or Decimal("0")

        transactions = []
        for inv in SI.objects.filter(
            is_active=True,
            invoice_date__month=month,
            invoice_date__year=year,
            status__in=[SI.STATUS_SENT, SI.STATUS_PARTIAL, SI.STATUS_PAID, SI.STATUS_OVERDUE],
        ).order_by("-invoice_date")[:50]:
            transactions.append(
                {
                    "date": inv.invoice_date.isoformat(),
                    "type": "OUTPUT",
                    "reference": inv.invoice_number,
                    "net_amount": str(inv.subtotal),
                    "vat_amount": str(inv.tax_amount),
                    "rate": "18",
                }
            )
        for inv in PI.objects.filter(
            is_active=True,
            invoice_date__month=month,
            invoice_date__year=year,
        ).order_by("-invoice_date")[:50]:
            transactions.append(
                {
                    "date": inv.invoice_date.isoformat(),
                    "type": "INPUT",
                    "reference": inv.invoice_number,
                    "net_amount": str(inv.subtotal),
                    "vat_amount": str(inv.tax_amount),
                    "rate": "18",
                }
            )

        period = VATPeriod.objects.filter(month=month, year=year).first()
        return {
            "month": month,
            "year": year,
            "output_vat": str(output_vat),
            "input_vat": str(input_vat),
            "net_vat_payable": str(output_vat - input_vat),
            "is_locked": period.is_locked if period else False,
            "transactions": transactions,
        }

    @staticmethod
    def paye_summary(month, year):
        """PAYE from posted payroll journal entries or placeholder."""
        entries = []
        payroll_jes = JournalLine.objects.filter(
            journal_entry__reference_type=JournalEntry.REF_PAYROLL,
            journal_entry__status=JournalEntry.STATUS_POSTED,
            journal_entry__date__month=month,
            journal_entry__date__year=year,
            description__icontains="PAYE",
        ).select_related("journal_entry")
        total = payroll_jes.aggregate(t=Sum("credit_amount"))["t"] or Decimal("0")
        for line in payroll_jes[:20]:
            entries.append(
                {
                    "employee": line.description or "Employee",
                    "gross": "0",
                    "taxable_income": "0",
                    "paye_amount": str(line.credit_amount),
                    "cumulative_ytd": str(line.credit_amount),
                }
            )
        return {"month": month, "year": year, "total_paye": str(total), "entries": entries}

    @staticmethod
    def nssf_summary(month, year):
        entries = []
        nssf_lines = JournalLine.objects.filter(
            Q(description__icontains="NSSF") | Q(description__icontains="nssf"),
            journal_entry__status=JournalEntry.STATUS_POSTED,
            journal_entry__date__month=month,
            journal_entry__date__year=year,
        )
        employee_total = nssf_lines.filter(description__icontains="employee").aggregate(
            t=Sum("credit_amount")
        )["t"] or Decimal("0")
        employer_total = nssf_lines.filter(description__icontains="employer").aggregate(
            t=Sum("debit_amount")
        )["t"] or Decimal("0")
        return {
            "month": month,
            "year": year,
            "total_employee": str(employee_total),
            "total_employer": str(employer_total),
            "total_nssf": str(employee_total + employer_total),
            "entries": entries,
        }

    @staticmethod
    @transaction.atomic
    def complete_reconciliation(reconciliation, user):
        if reconciliation.status == BankReconciliation.STATUS_COMPLETED:
            raise ValueError("Already completed.")

        summary = FinanceService.reconciliation_summary(reconciliation)
        if Decimal(summary["difference"]) != 0:
            raise ValueError("System and bank balances do not match.")

        reconciliation.status = BankReconciliation.STATUS_COMPLETED
        reconciliation.reconciled_by = user
        reconciliation.reconciled_at = timezone.now()
        reconciliation.closing_balance = Decimal(summary["bank_balance"])
        reconciliation.save()

        for match in reconciliation.matches.filter(is_matched=True):
            match.journal_line.is_reconciled = True
            match.journal_line.save(update_fields=["is_reconciled"])

        reconciliation.bank_account.last_reconciled = timezone.now().date()
        reconciliation.bank_account.save(update_fields=["last_reconciled", "updated_at"])
        return reconciliation

    @staticmethod
    def reconciliation_summary(reconciliation):
        system_balance = reconciliation.opening_balance
        matched_lines = reconciliation.matches.filter(is_matched=True).select_related("journal_line")
        for match in matched_lines:
            line = match.journal_line
            system_balance += line.debit_amount - line.credit_amount

        bank_balance = reconciliation.opening_balance
        for sl in reconciliation.statement_lines.all():
            bank_balance += sl.deposit - sl.withdrawal

        unmatched_system = reconciliation.matches.filter(is_matched=False).count()
        unmatched_bank = reconciliation.statement_lines.filter(is_matched=False).count()

        return {
            "system_balance": str(system_balance),
            "bank_balance": str(bank_balance),
            "difference": str(system_balance - bank_balance),
            "unmatched_system": unmatched_system,
            "unmatched_bank": unmatched_bank,
        }
