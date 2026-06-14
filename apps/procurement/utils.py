"""Procurement utilities — document number generation."""

from django.utils import timezone


def generate_document_number(prefix: str, model_class, number_field: str) -> str:
    """
    Generate sequential document numbers: PR-2026-001, PO-2026-001, etc.
    """
    year = timezone.now().year
    stem = f"{prefix}-{year}-"
    filter_kw = {f"{number_field}__startswith": stem}
    last = (
        model_class.objects.filter(**filter_kw)
        .order_by(f"-{number_field}")
        .values_list(number_field, flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{stem}{seq:03d}"
