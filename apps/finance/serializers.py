"""Serializers for the finance module."""

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

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
)
from apps.finance.services import FinanceService
from apps.finance.utils import generate_account_code, generate_je_number


class AccountSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(required=False, allow_blank=True)
    parent_id = serializers.IntegerField(source="parent.id", read_only=True, allow_null=True)
    parent_name = serializers.CharField(source="parent.account_name", read_only=True, allow_null=True)
    balance = serializers.SerializerMethodField()
    balance_type = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = [
            "id",
            "account_code",
            "account_name",
            "account_type",
            "parent",
            "parent_id",
            "parent_name",
            "description",
            "balance",
            "balance_type",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_balance(self, obj):
        bal, _ = FinanceService.account_balance(obj)
        return str(bal)

    def get_balance_type(self, obj):
        _, bt = FinanceService.account_balance(obj)
        return bt

    def validate(self, attrs):
        parent = attrs.get("parent")
        account_type = attrs.get("account_type") or (
            self.instance.account_type if self.instance else None
        )
        if parent and account_type and parent.account_type != account_type:
            raise serializers.ValidationError(
                {"parent": "Parent account must be the same account type."}
            )
        code = (attrs.get("account_code") or "").strip()
        if code:
            qs = Account.objects.filter(account_code=code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"account_code": "This account code is already in use."}
                )
        return attrs

    def create(self, validated_data):
        code = (validated_data.get("account_code") or "").strip()
        if not code:
            validated_data["account_code"] = generate_account_code(
                validated_data["account_type"],
                validated_data.get("parent"),
            )
        return super().create(validated_data)


class JournalLineSerializer(serializers.ModelSerializer):
    account_id = serializers.IntegerField(source="account.id", read_only=True)
    account_code = serializers.CharField(source="account.account_code", read_only=True)
    account_name = serializers.CharField(source="account.account_name", read_only=True)
    department_id = serializers.IntegerField(source="department.id", read_only=True, allow_null=True)
    department_name = serializers.CharField(source="department.name", read_only=True, allow_null=True)

    class Meta:
        model = JournalLine
        fields = [
            "id",
            "account",
            "account_id",
            "account_code",
            "account_name",
            "description",
            "department",
            "department_id",
            "department_name",
            "debit_amount",
            "credit_amount",
        ]


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    total_debit = serializers.SerializerMethodField()
    total_credit = serializers.SerializerMethodField()
    posted_by_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    is_balanced = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "je_number",
            "date",
            "reference_type",
            "reference_id",
            "description",
            "currency",
            "currency_id",
            "currency_code",
            "exchange_rate",
            "total_debit",
            "total_credit",
            "is_balanced",
            "status",
            "lines",
            "posted_by",
            "posted_by_name",
            "posted_at",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "je_number",
            "status",
            "posted_by",
            "posted_at",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_total_debit(self, obj):
        debits, _ = FinanceService.je_totals(obj)
        return str(debits)

    def get_total_credit(self, obj):
        _, credits = FinanceService.je_totals(obj)
        return str(credits)

    def get_is_balanced(self, obj):
        return FinanceService.validate_balanced(obj)

    def get_posted_by_name(self, obj):
        if obj.posted_by:
            return obj.posted_by.get_full_name() or obj.posted_by.email
        return None

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None

    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        user = self.context["request"].user
        entry = JournalEntry.objects.create(
            je_number=generate_je_number(),
            created_by=user,
            **validated_data,
        )
        for line_data in lines_data:
            JournalLine.objects.create(journal_entry=entry, **line_data)
        return entry

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status != JournalEntry.STATUS_DRAFT:
            raise serializers.ValidationError("Only draft entries can be edited.")
        lines_data = validated_data.pop("lines", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                JournalLine.objects.create(journal_entry=instance, **line_data)
        return instance


class BankAccountSerializer(serializers.ModelSerializer):
    currency_id = serializers.IntegerField(source="currency.id", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    gl_account_id = serializers.IntegerField(source="gl_account.id", read_only=True)
    gl_account_name = serializers.CharField(source="gl_account.account_name", read_only=True)

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "bank_name",
            "account_number",
            "account_name",
            "currency",
            "currency_id",
            "currency_code",
            "gl_account",
            "gl_account_id",
            "gl_account_name",
            "opening_balance",
            "current_balance",
            "last_reconciled",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["current_balance", "last_reconciled", "created_at", "updated_at"]


class BankStatementLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatementLine
        fields = ["id", "date", "description", "deposit", "withdrawal", "is_matched"]


class ReconciliationMatchSerializer(serializers.ModelSerializer):
    journal_line = JournalLineSerializer(read_only=True)
    journal_line_id = serializers.PrimaryKeyRelatedField(
        queryset=JournalLine.objects.all(),
        source="journal_line",
        write_only=True,
    )

    class Meta:
        model = ReconciliationMatch
        fields = ["id", "journal_line", "journal_line_id", "is_matched"]


class BankReconciliationSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source="bank_account.bank_name", read_only=True)
    bank_account_number = serializers.CharField(source="bank_account.account_number", read_only=True)
    statement_lines = BankStatementLineSerializer(many=True, required=False)
    matches = ReconciliationMatchSerializer(many=True, required=False)
    reconciled_by_name = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    period_label = serializers.SerializerMethodField()

    class Meta:
        model = BankReconciliation
        fields = [
            "id",
            "bank_account",
            "bank_account_name",
            "bank_account_number",
            "period_month",
            "period_year",
            "period_label",
            "opening_balance",
            "closing_balance",
            "status",
            "statement_lines",
            "matches",
            "summary",
            "reconciled_by",
            "reconciled_by_name",
            "reconciled_at",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "reconciled_by", "reconciled_at", "created_at", "updated_at"]

    def get_reconciled_by_name(self, obj):
        if obj.reconciled_by:
            return obj.reconciled_by.get_full_name() or obj.reconciled_by.email
        return None

    def get_summary(self, obj):
        return FinanceService.reconciliation_summary(obj)

    def get_period_label(self, obj):
        months = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        return f"{months[obj.period_month]} {obj.period_year}"

    @transaction.atomic
    def create(self, validated_data):
        lines_data = validated_data.pop("statement_lines", [])
        matches_data = validated_data.pop("matches", [])
        recon = BankReconciliation.objects.create(**validated_data)
        for line_data in lines_data:
            BankStatementLine.objects.create(reconciliation=recon, **line_data)
        for match_data in matches_data:
            ReconciliationMatch.objects.create(reconciliation=recon, **match_data)
        return recon

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status == BankReconciliation.STATUS_COMPLETED:
            raise serializers.ValidationError("Completed reconciliations cannot be edited.")
        lines_data = validated_data.pop("statement_lines", None)
        matches_data = validated_data.pop("matches", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.statement_lines.all().delete()
            for line_data in lines_data:
                BankStatementLine.objects.create(reconciliation=instance, **line_data)
        if matches_data is not None:
            instance.matches.all().delete()
            for match_data in matches_data:
                ReconciliationMatch.objects.create(reconciliation=instance, **match_data)
        return instance


class BudgetSerializer(serializers.ModelSerializer):
    department_id = serializers.IntegerField(source="department.id", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    account_id = serializers.IntegerField(source="account.id", read_only=True)
    account_name = serializers.CharField(source="account.account_name", read_only=True)
    amount_actual = serializers.SerializerMethodField()
    variance = serializers.SerializerMethodField()
    variance_percent = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            "id",
            "name",
            "department",
            "department_id",
            "department_name",
            "account",
            "account_id",
            "account_name",
            "financial_year",
            "period",
            "amount_budgeted",
            "amount_actual",
            "variance",
            "variance_percent",
            "status",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_amount_actual(self, obj):
        actual = FinanceService.budget_actual(obj.account_id, obj.department_id, obj.financial_year)
        return str(actual)

    def get_variance(self, obj):
        actual = FinanceService.budget_actual(obj.account_id, obj.department_id, obj.financial_year)
        return str(obj.amount_budgeted - actual)

    def get_variance_percent(self, obj):
        actual = FinanceService.budget_actual(obj.account_id, obj.department_id, obj.financial_year)
        if obj.amount_budgeted <= 0:
            return "0"
        pct = (actual / obj.amount_budgeted) * 100
        return str(round(float(pct), 1))

    def get_status(self, obj):
        actual = FinanceService.budget_actual(obj.account_id, obj.department_id, obj.financial_year)
        return FinanceService.budget_status(obj.amount_budgeted, actual)


class TaxSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxSetting
        fields = [
            "id",
            "name",
            "rate",
            "applicable_to",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class SupplierPaymentSerializer(serializers.Serializer):
    invoice = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    payment_date = serializers.DateField()
    payment_method = serializers.CharField(max_length=50)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bank_account = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, attrs):
        from apps.procurement.models import SupplierInvoice

        try:
            invoice = SupplierInvoice.objects.get(pk=attrs["invoice"])
        except SupplierInvoice.DoesNotExist:
            raise serializers.ValidationError({"invoice": "Invoice not found."})
        if not invoice.three_way_matched:
            raise serializers.ValidationError(
                {"invoice": "Payment requires 3-way matched invoice (PO + GRN + Invoice)."}
            )
        if attrs["amount"] > invoice.balance:
            raise serializers.ValidationError({"amount": "Amount exceeds invoice balance."})
        attrs["invoice_obj"] = invoice
        return attrs
