# Generated manually for finance module

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0002_initial"),
        ("users", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("account_code", models.CharField(max_length=20, unique=True)),
                ("account_name", models.CharField(max_length=255)),
                ("account_type", models.CharField(max_length=20)),
                ("description", models.TextField(blank=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="finance.account")),
            ],
            options={"ordering": ["account_code"]},
        ),
        migrations.CreateModel(
            name="JournalEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("je_number", models.CharField(editable=False, max_length=30, unique=True)),
                ("date", models.DateField(default=django.utils.timezone.now)),
                ("reference_type", models.CharField(default="MANUAL", max_length=20)),
                ("reference_id", models.CharField(blank=True, max_length=100)),
                ("description", models.TextField()),
                ("exchange_rate", models.DecimalField(decimal_places=6, default=Decimal("1"), max_digits=18)),
                ("status", models.CharField(default="DRAFT", max_length=20)),
                ("posted_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="journal_entries_created", to=settings.AUTH_USER_MODEL)),
                ("currency", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="journal_entries", to="core.currency")),
                ("posted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="journal_entries_posted", to=settings.AUTH_USER_MODEL)),
                ("reversed_entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reversals", to="finance.journalentry")),
            ],
            options={"ordering": ["-date", "-created_at"], "verbose_name_plural": "journal entries"},
        ),
        migrations.CreateModel(
            name="BankAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("bank_name", models.CharField(max_length=100)),
                ("account_number", models.CharField(max_length=50)),
                ("account_name", models.CharField(max_length=255)),
                ("opening_balance", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("current_balance", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("last_reconciled", models.DateField(blank=True, null=True)),
                ("currency", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bank_accounts", to="core.currency")),
                ("gl_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bank_accounts", to="finance.account")),
            ],
            options={"ordering": ["bank_name", "account_number"]},
        ),
        migrations.CreateModel(
            name="BankReconciliation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("period_month", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])),
                ("period_year", models.PositiveIntegerField()),
                ("opening_balance", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("closing_balance", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("status", models.CharField(default="DRAFT", max_length=20)),
                ("reconciled_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("bank_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reconciliations", to="finance.bankaccount")),
                ("reconciled_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="bank_reconciliations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-period_year", "-period_month"], "unique_together": {("bank_account", "period_month", "period_year")}},
        ),
        migrations.CreateModel(
            name="Budget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("name", models.CharField(blank=True, max_length=255)),
                ("financial_year", models.PositiveIntegerField()),
                ("period", models.CharField(default="ANNUAL", max_length=20)),
                ("amount_budgeted", models.DecimalField(decimal_places=2, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("notes", models.TextField(blank=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="budgets", to="finance.account")),
                ("department", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="budgets", to="users.department")),
            ],
            options={"ordering": ["-financial_year", "department__name"]},
        ),
        migrations.CreateModel(
            name="TaxSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("name", models.CharField(max_length=100)),
                ("rate", models.DecimalField(decimal_places=4, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("applicable_to", models.CharField(max_length=20)),
                ("description", models.TextField(blank=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="VATPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("month", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)])),
                ("year", models.PositiveIntegerField()),
                ("is_locked", models.BooleanField(default=False)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("submitted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="vat_periods_submitted", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-year", "-month"], "unique_together": {("month", "year")}},
        ),
        migrations.CreateModel(
            name="JournalLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(blank=True, max_length=255)),
                ("debit_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("credit_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("is_reconciled", models.BooleanField(default=False)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="journal_lines", to="finance.account")),
                ("department", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="journal_lines", to="users.department")),
                ("journal_entry", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="finance.journalentry")),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="BankStatementLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("description", models.CharField(blank=True, max_length=255)),
                ("deposit", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("withdrawal", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("is_matched", models.BooleanField(default=False)),
                ("reconciliation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="statement_lines", to="finance.bankreconciliation")),
            ],
            options={"ordering": ["date", "id"]},
        ),
        migrations.CreateModel(
            name="ReconciliationMatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_matched", models.BooleanField(default=True)),
                ("journal_line", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reconciliation_matches", to="finance.journalline")),
                ("reconciliation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="matches", to="finance.bankreconciliation")),
            ],
            options={"unique_together": {("reconciliation", "journal_line")}},
        ),
    ]
