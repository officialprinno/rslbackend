"""Sync vehicle/driver availability with active sales order dispatch states."""

from django.core.management.base import BaseCommand

from apps.sales.models import SalesOrder
from apps.sales.workflow import SalesOrderWorkflow


class Command(BaseCommand):
    help = "Align vehicle ON_TRIP and driver availability with in-transit sales orders."

    def handle(self, *args, **options):
        active = SalesOrder.objects.filter(
            is_active=True,
            status__in=(
                SalesOrder.STATUS_DISPATCHED,
                SalesOrder.STATUS_IN_TRANSIT,
            ),
        ).select_related(
            "dispatch_assignment",
            "dispatch_assignment__vehicle",
            "dispatch_assignment__driver",
        ).prefetch_related(
            "delivery_orders__vehicle",
            "delivery_orders__driver",
        )

        synced = 0
        for order in active:
            SalesOrderWorkflow.ensure_fleet_matches_order(order)
            synced += 1

        self.stdout.write(
            self.style.SUCCESS(f"Synced fleet status for {synced} active dispatch order(s).")
        )
