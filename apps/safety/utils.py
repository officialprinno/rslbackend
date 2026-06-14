"""Safety module utilities."""

from django.utils import timezone


def _next_number(prefix, model, field):
    year = timezone.now().year
    full_prefix = f"{prefix}-{year}-"
    last = (
        model.objects.filter(**{f"{field}__startswith": full_prefix})
        .order_by(f"-{field}")
        .values_list(field, flat=True)
        .first()
    )
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{full_prefix}{seq:03d}"


def generate_incident_number():
    from apps.safety.models import SafetyIncident

    return _next_number("INC", SafetyIncident, "incident_number")


def generate_inspection_number():
    from apps.safety.models import SafetyInspection

    return _next_number("INS", SafetyInspection, "inspection_number")


def generate_permit_number():
    from apps.safety.models import WorkPermit

    return _next_number("WP", WorkPermit, "permit_number")


def generate_ppe_request_number():
    from apps.safety.models import PPERequest

    return _next_number("PPR", PPERequest, "request_number")


def generate_visitor_number():
    from apps.safety.security_models import Visitor

    return _next_number("V", Visitor, "visitor_number")


def generate_vehicle_log_number():
    from apps.safety.security_models import VehicleLog

    return _next_number("VL", VehicleLog, "log_number")


def generate_movement_number():
    from apps.safety.security_models import InterLocationMovement

    return _next_number("ILM", InterLocationMovement, "movement_number")


def generate_security_incident_number():
    from apps.safety.security_models import SecurityIncidentRecord

    return _next_number("SEC", SecurityIncidentRecord, "incident_number")
