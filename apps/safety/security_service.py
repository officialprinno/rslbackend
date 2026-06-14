"""Security sub-department business logic."""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.safety.security_models import (
    AccessLog,
    InterLocationMovement,
    SecurityIncidentRecord,
    SecurityLocation,
    SecurityPersonnel,
    SecurityShift,
    SecurityShiftOfficer,
    VehicleLog,
    Visitor,
)

MINIMUM_STAFF = {
    "Main Office": {"MORNING": 2, "AFTERNOON": 2, "NIGHT": 1},
    "Stein": {"MORNING": 1, "AFTERNOON": 1, "NIGHT": 1},
}

CRITICAL_INCIDENT_TYPES = {
    SecurityIncidentRecord.TYPE_THEFT,
    SecurityIncidentRecord.TYPE_ASSAULT,
    SecurityIncidentRecord.TYPE_FRAUD,
    SecurityIncidentRecord.TYPE_UNAUTHORIZED,
}


class SecurityService:
    @staticmethod
    def get_locations():
        return SecurityLocation.objects.filter(is_active=True)

    @staticmethod
    def _location_ids():
        locs = list(SecurityLocation.objects.filter(is_active=True))
        main = next((l for l in locs if "Main" in l.name), None)
        stein = next((l for l in locs if "Stein" in l.name), None)
        return main, stein

    @staticmethod
    def refresh_visitor_statuses():
        now = timezone.now()
        threshold = now - timedelta(minutes=30)
        Visitor.objects.filter(
            status=Visitor.STATUS_SIGNED_IN,
            expected_time_out__lt=threshold,
        ).update(status=Visitor.STATUS_OVERSTAYING)

    @staticmethod
    def refresh_movement_statuses():
        now = timezone.now()
        threshold = now - timedelta(minutes=10)
        InterLocationMovement.objects.filter(
            status=InterLocationMovement.STATUS_TRANSIT,
            expected_arrival__lt=threshold,
        ).update(status=InterLocationMovement.STATUS_OVERDUE)

    @staticmethod
    def dashboard(location_id=None):
        SecurityService.refresh_visitor_statuses()
        SecurityService.refresh_movement_statuses()
        main, stein = SecurityService._location_ids()
        today = timezone.now().date()

        def visitors_qs(loc=None):
            qs = Visitor.objects.filter(status=Visitor.STATUS_SIGNED_IN, is_active=True)
            if loc:
                qs = qs.filter(location=loc)
            return qs.count()

        def vehicles_qs(loc=None):
            qs = VehicleLog.objects.filter(status=VehicleLog.STATUS_ON, is_active=True)
            if loc:
                qs = qs.filter(location=loc)
            return qs.count()

        def officers_qs(loc=None):
            qs = SecurityPersonnel.objects.filter(is_on_duty=True, is_active=True)
            if loc:
                qs = qs.filter(
                    Q(primary_location=loc)
                    | Q(assignment_scope=SecurityPersonnel.SCOPE_BOTH)
                )
            return qs.count()

        def incidents_today(loc=None):
            qs = SecurityIncidentRecord.objects.filter(
                date_occurred__date=today, is_active=True
            )
            if loc:
                qs = qs.filter(location=loc)
            return qs.count()

        visitors_main = visitors_qs(main) if main else 0
        visitors_stein = visitors_qs(stein) if stein else 0
        vehicles_main = vehicles_qs(main) if main else 0
        vehicles_stein = vehicles_qs(stein) if stein else 0
        officers_main = officers_qs(main) if main else 0
        officers_stein = officers_qs(stein) if stein else 0
        inc_main = incidents_today(main) if main else 0
        inc_stein = incidents_today(stein) if stein else 0

        in_transit = InterLocationMovement.objects.filter(
            status__in=[
                InterLocationMovement.STATUS_TRANSIT,
                InterLocationMovement.STATUS_OVERDUE,
            ],
            is_active=True,
        )
        if location_id:
            in_transit = in_transit.filter(
                Q(from_location_id=location_id) | Q(to_location_id=location_id)
            )

        month_start = today.replace(day=1)
        violations = AccessLog.objects.filter(
            action__in=[AccessLog.ACTION_DENIED, AccessLog.ACTION_FORCED],
            created_at__date__gte=month_start,
            is_active=True,
        ).count()

        shift_status = SecurityService._shift_status(main, stein)
        alerts = SecurityService._build_alerts(main, stein)
        activity = SecurityService._live_activity(location_id)

        return {
            "location_filter": location_id,
            "visitors_on_site": visitors_main + visitors_stein,
            "visitors_main": visitors_main,
            "visitors_stein": visitors_stein,
            "vehicles_on_premises": vehicles_main + vehicles_stein,
            "vehicles_main": vehicles_main,
            "vehicles_stein": vehicles_stein,
            "officers_on_duty": officers_main + officers_stein,
            "officers_main": officers_main,
            "officers_stein": officers_stein,
            "incidents_today": inc_main + inc_stein,
            "incidents_main": inc_main,
            "incidents_stein": inc_stein,
            "in_transit_count": in_transit.count(),
            "access_violations_month": violations,
            "live_activity": activity,
            "in_transit": list(
                in_transit.select_related(
                    "from_location", "to_location", "employee"
                )[:10]
            ),
            "shift_status": shift_status,
            "alerts": alerts,
        }

    @staticmethod
    def _shift_status(main, stein):
        today = timezone.now().date()
        result = []
        for loc in [main, stein]:
            if not loc:
                continue
            shift = (
                SecurityShift.objects.filter(
                    location=loc, date=today, status=SecurityShift.STATUS_ACTIVE
                )
                .prefetch_related("officers__officer")
                .first()
            )
            if not shift:
                shift = (
                    SecurityShift.objects.filter(location=loc, date=today)
                    .order_by("shift_type")
                    .first()
                )
            officers_count = shift.officers.count() if shift else 0
            minimum = MINIMUM_STAFF.get(loc.name, {}).get(
                shift.shift_type if shift else "MORNING", 1
            )
            supervisor = SecurityPersonnel.objects.filter(
                primary_location=loc,
                rank=SecurityPersonnel.RANK_SUPERVISOR,
                is_active=True,
            ).first()
            result.append(
                {
                    "location_id": loc.id,
                    "location_name": loc.name,
                    "current_shift": shift.shift_type if shift else "—",
                    "officers_count": officers_count,
                    "supervisor_name": supervisor.employee.full_name
                    if supervisor
                    else "—",
                    "next_shift_time": "14:00",
                    "is_understaffed": officers_count < minimum,
                }
            )
        return result

    @staticmethod
    def _build_alerts(main, stein):
        alerts = []
        for v in Visitor.objects.filter(
            status=Visitor.STATUS_OVERSTAYING, is_active=True
        )[:5]:
            alerts.append(
                {
                    "type": "OVERSTAYING_VISITOR",
                    "severity": "HIGH",
                    "location_id": v.location_id,
                    "location_name": v.location.name,
                    "message": f"Visitor {v.full_name} is overstaying at {v.location.name}",
                    "reference_id": v.id,
                    "created_at": timezone.now().isoformat(),
                }
            )
        for m in InterLocationMovement.objects.filter(
            status=InterLocationMovement.STATUS_OVERDUE, is_active=True
        )[:5]:
            name = m.employee.full_name if m.employee else m.movement_number
            alerts.append(
                {
                    "type": "OVERDUE_MOVEMENT",
                    "severity": "CRITICAL",
                    "location_id": m.to_location_id,
                    "location_name": m.to_location.name,
                    "message": f"OVERDUE: {name} from {m.from_location.name} to {m.to_location.name}",
                    "reference_id": m.id,
                    "created_at": timezone.now().isoformat(),
                }
            )
        return alerts

    @staticmethod
    def _live_activity(location_id=None, limit=20):
        events = []
        visitors = Visitor.objects.filter(is_active=True).order_by("-updated_at")[:10]
        for v in visitors:
            if v.actual_time_in:
                events.append(
                    {
                        "id": v.id,
                        "time": v.actual_time_in.isoformat(),
                        "location_id": v.location_id,
                        "location_name": v.location.name,
                        "location_color": v.location.color,
                        "type": "ENTRY",
                        "person_name": v.full_name,
                        "description": f"Visitor — {v.get_status_display()}",
                        "severity": "WARNING"
                        if v.status == Visitor.STATUS_OVERSTAYING
                        else "NORMAL",
                    }
                )
        vehicles = VehicleLog.objects.filter(is_active=True).order_by("-time_in")[:10]
        for vl in vehicles:
            events.append(
                {
                    "id": vl.id + 10000,
                    "time": vl.time_in.isoformat(),
                    "location_id": vl.location_id,
                    "location_name": vl.location.name,
                    "location_color": vl.location.color,
                    "type": "VEHICLE_IN",
                    "person_name": vl.registration_number,
                    "description": f"{vl.driver_name} — {vl.get_status_display()}",
                    "severity": "NORMAL",
                }
            )
        if location_id:
            events = [e for e in events if e["location_id"] == location_id]
        events.sort(key=lambda x: x["time"], reverse=True)
        return events[:limit]

    @staticmethod
    def sign_in_visitor(visitor, user):
        visitor.status = Visitor.STATUS_SIGNED_IN
        visitor.actual_time_in = timezone.now()
        if not visitor.badge_number:
            visitor.badge_number = visitor.visitor_number
        visitor.save()
        AccessLog.objects.create(
            location=visitor.location,
            person_name=visitor.full_name,
            person_type=AccessLog.PERSON_VISITOR,
            action=AccessLog.ACTION_GRANTED,
            method=AccessLog.METHOD_MANUAL,
            security_officer=user,
            notes=f"Visitor sign-in {visitor.visitor_number}",
        )
        return visitor

    @staticmethod
    def sign_out_visitor(visitor, user, items_returned=None):
        visitor.status = Visitor.STATUS_SIGNED_OUT
        visitor.actual_time_out = timezone.now()
        if items_returned is not None:
            visitor.items_brought = items_returned
        visitor.save()
        AccessLog.objects.create(
            location=visitor.location,
            person_name=visitor.full_name,
            person_type=AccessLog.PERSON_VISITOR,
            action=AccessLog.ACTION_GRANTED,
            method=AccessLog.METHOD_MANUAL,
            security_officer=user,
            notes=f"Visitor sign-out {visitor.visitor_number}",
        )
        return visitor

    @staticmethod
    def log_movement(data, user):
        from apps.safety.utils import generate_movement_number

        movement = InterLocationMovement.objects.create(
            movement_number=generate_movement_number(),
            logged_by=user,
            **data,
        )
        return movement

    @staticmethod
    def mark_movement_arrived(movement, user, actual_arrival=None):
        arrival = actual_arrival or timezone.now()
        movement.actual_arrival = arrival
        movement.status = InterLocationMovement.STATUS_ARRIVED
        movement.travel_time_minutes = max(
            1,
            int((arrival - movement.departure_time).total_seconds() / 60),
        )
        movement.arrived_confirmed_by = user
        movement.save()
        return movement

    @staticmethod
    def shift_minimum(location_name, shift_type):
        return MINIMUM_STAFF.get(location_name, {}).get(shift_type, 1)

    @staticmethod
    def user_security_scope(user):
        """Return location id filter for guards, or None for full access."""
        if user.is_superuser:
            return None
        role_name = getattr(getattr(user, "role", None), "name", "") or ""
        if role_name in (
            "Chief Security Officer",
            "Security Supervisor",
            "Safety Officer",
            "General Manager",
            "Super Admin",
        ):
            return None
        profile = SecurityPersonnel.objects.filter(
            employee__user=user, is_active=True
        ).first()
        if not profile:
            return None
        if profile.assignment_scope == SecurityPersonnel.SCOPE_BOTH:
            return None
        if profile.primary_location_id:
            return profile.primary_location_id
        return None
