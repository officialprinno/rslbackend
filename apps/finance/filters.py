"""django-filter FilterSets for finance endpoints."""

import django_filters

from apps.finance.models import (
    Account,
    BankAccount,
    BankReconciliation,
    Budget,
    JournalEntry,
    TaxSetting,
)


class AccountFilter(django_filters.FilterSet):
    account_type = django_filters.CharFilter()
    parent = django_filters.NumberFilter(field_name="parent_id")
    parent__isnull = django_filters.BooleanFilter(field_name="parent", lookup_expr="isnull")

    class Meta:
        model = Account
        fields = ["is_active", "account_type", "parent"]


class JournalEntryFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = JournalEntry
        fields = ["status", "reference_type", "date_from", "date_to"]


class BankAccountFilter(django_filters.FilterSet):
    class Meta:
        model = BankAccount
        fields = ["is_active", "currency"]


class BankReconciliationFilter(django_filters.FilterSet):
    bank_account = django_filters.NumberFilter(field_name="bank_account_id")
    period_year = django_filters.NumberFilter()

    class Meta:
        model = BankReconciliation
        fields = ["status", "bank_account", "period_year", "period_month"]


class BudgetFilter(django_filters.FilterSet):
    department = django_filters.NumberFilter(field_name="department_id")
    account = django_filters.NumberFilter(field_name="account_id")

    class Meta:
        model = Budget
        fields = ["financial_year", "period", "department", "account", "is_active"]


class TaxSettingFilter(django_filters.FilterSet):
    class Meta:
        model = TaxSetting
        fields = ["is_active", "applicable_to"]
