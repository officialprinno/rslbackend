"""
Finance models for Rock Solutions FMS.

Chart of Accounts → Journal Entries → Bank Reconciliation → Budgets → Tax
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Account(BaseModel):
    """General ledger account in hierarchical chart of accounts."""

    TYPE_ASSET = "ASSET"
    TYPE_LIABILITY = "LIABILITY"
    TYPE_EQUITY = "EQUITY"
    TYPE_REVENUE = "REVENUE"
    TYPE_EXPENSE = "EXPENSE"
    TYPE_CHOICES = [
        (TYPE_ASSET, "Asset"),
        (TYPE_LIABILITY, "Liability"),
        (TYPE_EQUITY, "Equity"),
        (TYPE_REVENUE, "Revenue"),
        (TYPE_EXPENSE, "Expense"),
    ]

    account_code = models.CharField(max_length=20, unique=True)
    account_name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["account_code"]

    def __str__(self):
        return f"{self.account_code} — {self.account_name}"


class JournalEntry(BaseModel):
    """Double-entry journal entry."""

    REF_INVOICE = "INVOICE"
    REF_PAYMENT = "PAYMENT"
    REF_PAYROLL = "PAYROLL"
    REF_MANUAL = "MANUAL"
    REF_CHOICES = [
        (REF_INVOICE, "Invoice"),
        (REF_PAYMENT, "Payment"),
        (REF_PAYROLL, "Payroll"),
        (REF_MANUAL, "Manual"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_POSTED = "POSTED"
    STATUS_REVERSED = "REVERSED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_POSTED, "Posted"),
        (STATUS_REVERSED, "Reversed"),
    ]

    je_number = models.CharField(max_length=30, unique=True, editable=False)
    date = models.DateField(default=timezone.now)
    reference_type = models.CharField(
        max_length=20, choices=REF_CHOICES, default=REF_MANUAL
    )
    reference_id = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="journal_entries",
    )
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1"),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_entries_posted",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_entry = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversals",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="journal_entries_created",
    )

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name_plural = "journal entries"

    def __str__(self):
        return self.je_number


class JournalLine(models.Model):
    """Debit/credit line on a journal entry."""

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="journal_lines",
    )
    description = models.CharField(max_length=255, blank=True)
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_lines",
    )
    debit_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    credit_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_reconciled = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.account.account_code}: Dr {self.debit_amount} Cr {self.credit_amount}"


class BankAccount(BaseModel):
    """Company bank account linked to GL."""

    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    account_name = models.CharField(max_length=255)
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="bank_accounts",
    )
    gl_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="bank_accounts",
    )
    opening_balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    current_balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
    )
    last_reconciled = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["bank_name", "account_number"]

    def __str__(self):
        return f"{self.bank_name} — {self.account_number}"


class BankReconciliation(BaseModel):
    """Bank reconciliation session."""

    STATUS_DRAFT = "DRAFT"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_COMPLETED, "Completed"),
    ]

    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.PROTECT,
        related_name="reconciliations",
    )
    period_month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    period_year = models.PositiveIntegerField()
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    closing_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_reconciliations",
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-period_year", "-period_month"]
        unique_together = [("bank_account", "period_month", "period_year")]

    def __str__(self):
        return f"{self.bank_account} — {self.period_month}/{self.period_year}"


class BankStatementLine(models.Model):
    """Bank statement line entered during reconciliation."""

    reconciliation = models.ForeignKey(
        BankReconciliation,
        on_delete=models.CASCADE,
        related_name="statement_lines",
    )
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    deposit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    withdrawal = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_matched = models.BooleanField(default=False)

    class Meta:
        ordering = ["date", "id"]


class ReconciliationMatch(models.Model):
    """Links a journal line to a reconciliation."""

    reconciliation = models.ForeignKey(
        BankReconciliation,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    journal_line = models.ForeignKey(
        JournalLine,
        on_delete=models.CASCADE,
        related_name="reconciliation_matches",
    )
    is_matched = models.BooleanField(default=True)

    class Meta:
        unique_together = [("reconciliation", "journal_line")]


class Budget(BaseModel):
    """Departmental budget line."""

    PERIOD_MONTHLY = "MONTHLY"
    PERIOD_QUARTERLY = "QUARTERLY"
    PERIOD_ANNUAL = "ANNUAL"
    PERIOD_CHOICES = [
        (PERIOD_MONTHLY, "Monthly"),
        (PERIOD_QUARTERLY, "Quarterly"),
        (PERIOD_ANNUAL, "Annual"),
    ]

    name = models.CharField(max_length=255, blank=True)
    department = models.ForeignKey(
        "users.Department",
        on_delete=models.PROTECT,
        related_name="budgets",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="budgets",
    )
    financial_year = models.PositiveIntegerField()
    period = models.CharField(max_length=20, choices=PERIOD_CHOICES, default=PERIOD_ANNUAL)
    amount_budgeted = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-financial_year", "department__name"]

    def __str__(self):
        return self.name or f"{self.department} — {self.account.account_code}"


class TaxSetting(BaseModel):
    """Configurable tax rates."""

    APPLICABLE_SALES = "SALES"
    APPLICABLE_PURCHASE = "PURCHASE"
    APPLICABLE_PAYROLL = "PAYROLL"
    APPLICABLE_CHOICES = [
        (APPLICABLE_SALES, "Sales"),
        (APPLICABLE_PURCHASE, "Purchase"),
        (APPLICABLE_PAYROLL, "Payroll"),
    ]

    name = models.CharField(max_length=100)
    rate = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))],
    )
    applicable_to = models.CharField(max_length=20, choices=APPLICABLE_CHOICES)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class VATPeriod(BaseModel):
    """VAT return period — locked after submission."""

    month = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    year = models.PositiveIntegerField()
    is_locked = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vat_periods_submitted",
    )

    class Meta:
        unique_together = [("month", "year")]
        ordering = ["-year", "-month"]
