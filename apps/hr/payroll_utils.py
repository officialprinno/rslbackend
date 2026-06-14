"""Tanzania payroll calculation utilities."""

from decimal import Decimal


def calculate_paye(gross_monthly):
    """TRA PAYE bands (monthly TZS)."""
    gross = float(gross_monthly)
    if gross <= 270_000:
        paye = 0
    elif gross <= 520_000:
        paye = (gross - 270_000) * 0.08
    elif gross <= 760_000:
        paye = 20_000 + (gross - 520_000) * 0.20
    elif gross <= 1_000_000:
        paye = 68_000 + (gross - 760_000) * 0.25
    else:
        paye = 128_000 + (gross - 1_000_000) * 0.30
    return int(round(paye))


def calculate_nssf(basic_salary):
    basic = float(basic_salary)
    amount = int(round(basic * 0.10))
    return {"employee": amount, "employer": amount}


def calculate_nhif(gross_salary):
    gross = float(gross_salary)
    if gross <= 100_000:
        return 3_000
    if gross <= 200_000:
        return 5_000
    if gross <= 400_000:
        return 8_000
    if gross <= 600_000:
        return 10_000
    if gross <= 800_000:
        return 15_000
    if gross <= 1_000_000:
        return 18_000
    if gross <= 1_500_000:
        return 25_000
    if gross <= 2_000_000:
        return 30_000
    if gross <= 2_500_000:
        return 35_000
    return 40_000


def appraisal_rating(score):
    if score is None:
        return None
    if score >= 90:
        return "EXCELLENT"
    if score >= 75:
        return "GOOD"
    if score >= 60:
        return "SATISFACTORY"
    return "NEEDS_IMPROVEMENT"


def count_working_days(start_date, end_date, holidays=None):
    """Count weekdays between dates excluding holidays."""
    holidays = holidays or set()
    days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in holidays:
            days += 1
        current += __import__("datetime").timedelta(days=1)
    return days
