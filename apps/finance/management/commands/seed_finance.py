"""
Seed chart of accounts, bank accounts, tax settings, and sample journal entries.

Prerequisites:
    python manage.py migrate
    python manage.py seed_fms
    python manage.py seed_sales
    python manage.py seed_procurement
    python manage.py seed_finance
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Currency
from apps.finance.models import (
    Account,
    BankAccount,
    Budget,
    JournalEntry,
    JournalLine,
    TaxSetting,
)
from apps.finance.utils import generate_je_number
from apps.users.models import Department, User

COA = [
    ("1000", "ASSETS", "ASSET", None),
    ("1100", "Current Assets", "ASSET", "1000"),
    ("1101", "Cash", "ASSET", "1100"),
    ("1102", "Bank Account — CRDB", "ASSET", "1100"),
    ("1103", "Bank Account — NMB", "ASSET", "1100"),
    ("1200", "Accounts Receivable", "ASSET", "1100"),
    ("1300", "Inventory", "ASSET", "1100"),
    ("1400", "Fixed Assets", "ASSET", "1000"),
    ("1401", "Machinery", "ASSET", "1400"),
    ("1402", "Vehicles", "ASSET", "1400"),
    ("2000", "LIABILITIES", "LIABILITY", None),
    ("2100", "Current Liabilities", "LIABILITY", "2000"),
    ("2101", "Accounts Payable", "LIABILITY", "2100"),
    ("2200", "VAT Payable", "LIABILITY", "2100"),
    ("2300", "Long Term Liabilities", "LIABILITY", "2000"),
    ("3000", "EQUITY", "EQUITY", None),
    ("3001", "Retained Earnings", "EQUITY", "3000"),
    ("4000", "REVENUE", "REVENUE", None),
    ("4001", "Trading Revenue", "REVENUE", "4000"),
    ("4002", "Manufacturing Revenue", "REVENUE", "4000"),
    ("5000", "EXPENSES", "EXPENSE", None),
    ("5001", "Cost of Goods Sold", "EXPENSE", "5000"),
    ("5100", "Salaries", "EXPENSE", "5000"),
    ("5200", "Fuel & Transport", "EXPENSE", "5000"),
    ("5300", "Other Expenses", "EXPENSE", "5000"),
]

TAX_SETTINGS = [
    ("VAT", Decimal("18"), TaxSetting.APPLICABLE_SALES, "Value Added Tax — 18%"),
    ("NSSF Employee", Decimal("10"), TaxSetting.APPLICABLE_PAYROLL, "NSSF employee contribution"),
    ("NSSF Employer", Decimal("10"), TaxSetting.APPLICABLE_PAYROLL, "NSSF employer contribution"),
    ("WHT", Decimal("5"), TaxSetting.APPLICABLE_PURCHASE, "Withholding tax on services"),
]


class Command(BaseCommand):
    help = "Seed finance chart of accounts, banks, tax settings, and sample JEs"

    @transaction.atomic
    def handle(self, *args, **options):
        admin = User.objects.filter(email="admin@rocksolutions.co.tz").first()
        if not admin:
            self.stdout.write(self.style.ERROR("Run seed_fms first."))
            return

        currency = Currency.objects.filter(is_default=True).first()
        if not currency:
            currency = Currency.objects.first()
        if not currency:
            self.stdout.write(self.style.ERROR("No currency found."))
            return

        account_map = {}
        for code, name, acc_type, parent_code in COA:
            parent = account_map.get(parent_code) if parent_code else None
            acc, _ = Account.objects.update_or_create(
                account_code=code,
                defaults={
                    "account_name": name,
                    "account_type": acc_type,
                    "parent": parent,
                    "description": f"Rock Solutions — {name}",
                },
            )
            account_map[code] = acc
            self.stdout.write(f"  Account: {code} — {name}")

        for bank_name, code, number in [
            ("CRDB Bank", "1102", "0150123456789"),
            ("NMB Bank", "1103", "2040123456789"),
        ]:
            gl = account_map[code]
            ba, _ = BankAccount.objects.update_or_create(
                account_number=number,
                defaults={
                    "bank_name": bank_name,
                    "account_name": "Rock Solutions Ltd — Operating",
                    "currency": currency,
                    "gl_account": gl,
                    "opening_balance": Decimal("50000000"),
                    "current_balance": Decimal("50000000"),
                },
            )
            self.stdout.write(f"  Bank: {bank_name}")

        for name, rate, applicable, desc in TAX_SETTINGS:
            TaxSetting.objects.update_or_create(
                name=name,
                defaults={"rate": rate, "applicable_to": applicable, "description": desc},
            )

        finance_dept = Department.objects.filter(name="Finance").first()
        if finance_dept:
            Budget.objects.update_or_create(
                department=finance_dept,
                account=account_map["5300"],
                financial_year=timezone.now().year,
                period=Budget.PERIOD_ANNUAL,
                defaults={
                    "name": "Finance Admin Expenses",
                    "amount_budgeted": Decimal("12000000"),
                },
            )

        if not JournalEntry.objects.exists():
            today = timezone.now().date()
            je = JournalEntry.objects.create(
                je_number=generate_je_number(),
                date=today,
                reference_type=JournalEntry.REF_MANUAL,
                description="Opening balances — seed data",
                currency=currency,
                exchange_rate=Decimal("1"),
                status=JournalEntry.STATUS_POSTED,
                posted_by=admin,
                posted_at=timezone.now(),
                created_by=admin,
            )
            lines = [
                (account_map["1102"], Decimal("50000000"), Decimal("0")),
                (account_map["3001"], Decimal("0"), Decimal("50000000")),
            ]
            for acc, dr, cr in lines:
                JournalLine.objects.create(
                    journal_entry=je,
                    account=acc,
                    description="Opening balance",
                    debit_amount=dr,
                    credit_amount=cr,
                )
            self.stdout.write(f"  Journal Entry: {je.je_number}")

            je2 = JournalEntry.objects.create(
                je_number=generate_je_number(),
                date=today,
                reference_type=JournalEntry.REF_INVOICE,
                reference_id="SEED-REV-001",
                description="Sample trading revenue — mining equipment sale",
                currency=currency,
                exchange_rate=Decimal("1"),
                status=JournalEntry.STATUS_POSTED,
                posted_by=admin,
                posted_at=timezone.now(),
                created_by=admin,
            )
            JournalLine.objects.create(
                journal_entry=je2,
                account=account_map["1200"],
                description="Customer invoice",
                debit_amount=Decimal("8500000"),
                credit_amount=Decimal("0"),
            )
            JournalLine.objects.create(
                journal_entry=je2,
                account=account_map["4001"],
                description="Trading revenue",
                debit_amount=Decimal("0"),
                credit_amount=Decimal("7200000"),
            )
            JournalLine.objects.create(
                journal_entry=je2,
                account=account_map["2200"],
                description="Output VAT 18%",
                debit_amount=Decimal("0"),
                credit_amount=Decimal("1300000"),
            )
            self.stdout.write(f"  Journal Entry: {je2.je_number}")

        self.stdout.write(self.style.SUCCESS("Finance seed complete."))
