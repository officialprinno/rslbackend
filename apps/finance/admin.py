from django.contrib import admin

from apps.finance.models import (
    Account,
    BankAccount,
    BankReconciliation,
    Budget,
    JournalEntry,
    TaxSetting,
)

admin.site.register(Account)
admin.site.register(JournalEntry)
admin.site.register(BankAccount)
admin.site.register(BankReconciliation)
admin.site.register(Budget)
admin.site.register(TaxSetting)
