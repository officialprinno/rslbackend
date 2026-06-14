"""Finance module utilities."""

from django.utils import timezone

from apps.finance.models import Account

# Chart of accounts ranges: 1xxx Assets, 2xxx Liabilities, etc.
ACCOUNT_TYPE_PREFIX = {
    Account.TYPE_ASSET: 1,
    Account.TYPE_LIABILITY: 2,
    Account.TYPE_EQUITY: 3,
    Account.TYPE_REVENUE: 4,
    Account.TYPE_EXPENSE: 5,
}


def generate_account_code(account_type, parent=None):
    """
    Generate the next account code for a type (and optional parent).

    ASSET → 1000–1999, LIABILITY → 2000–2999, EQUITY → 3000–3999,
    REVENUE → 4000–4999, EXPENSE → 5000–5999.
    """
    prefix = ACCOUNT_TYPE_PREFIX.get(account_type)
    if prefix is None:
        raise ValueError(f"Invalid account type: {account_type}")

    range_min = prefix * 1000
    range_max = prefix * 1000 + 999

    def numeric_codes(qs):
        codes = []
        for code in qs.values_list("account_code", flat=True):
            if code and str(code).isdigit():
                val = int(code)
                if range_min <= val <= range_max:
                    codes.append(val)
        return codes

    if parent:
        if parent.account_type != account_type:
            raise ValueError("Parent account must be the same account type.")
        parent_code = int(parent.account_code)
        sibling_codes = numeric_codes(Account.objects.filter(parent=parent))
        if sibling_codes:
            return str(max(sibling_codes) + 1)
        if parent_code % 1000 == 0:
            return str(parent_code + 100)
        return str(parent_code + 1)

    top_codes = numeric_codes(
        Account.objects.filter(account_type=account_type, parent__isnull=True)
    )
    if not top_codes:
        return str(range_min)

    all_type_codes = set(numeric_codes(Account.objects.filter(account_type=account_type)))
    max_code = max(top_codes)
    if max_code % 1000 == 0:
        candidate = max_code + 100
    elif max_code % 100 == 0:
        candidate = max_code + 100
    else:
        candidate = max_code + 1

    while candidate in all_type_codes and candidate <= range_max:
        candidate += 1
    if candidate > range_max:
        raise ValueError("No available account codes in this range.")
    return str(candidate)


def generate_je_number():
    """Generate sequential journal entry number JE-YYYY-NNN."""
    from apps.finance.models import JournalEntry

    year = timezone.now().year
    prefix = f"JE-{year}-"
    last = (
        JournalEntry.objects.filter(je_number__startswith=prefix)
        .order_by("-je_number")
        .values_list("je_number", flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:03d}"
