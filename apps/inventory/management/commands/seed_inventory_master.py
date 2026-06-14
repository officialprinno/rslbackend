"""
Seed Rock Solutions master inventory catalogue (categories + items).

Prerequisites:
    python manage.py migrate
    python manage.py seed_fms

Usage:
    python manage.py seed_inventory_master
    python manage.py seed_inventory_master --update
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Currency
from apps.inventory.seeders.master_inventory import preview_master_inventory, seed_master_inventory


class Command(BaseCommand):
    help = "Seed master inventory categories and items for Rock Solutions Limited"

    def add_arguments(self, parser):
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing master categories/items from the catalogue",
        )
        parser.add_argument(
            "--preview",
            action="store_true",
            help="Show catalogue summary without writing to the database",
        )

    def handle(self, *args, **options):
        if options["preview"]:
            preview = preview_master_inventory()
            self.stdout.write("Master inventory catalogue preview:")
            self.stdout.write(f"  Categories: {preview['categories_total']} total, {preview['categories_existing']} in DB")
            self.stdout.write(f"  Items: {preview['items_total']} total, {preview['items_existing']} in DB")
            return

        tzs = Currency.objects.filter(code="TZS").first()
        if not tzs:
            self.stderr.write(self.style.ERROR("TZS currency not found — run seed_fms first."))
            return

        with transaction.atomic():
            stats = seed_master_inventory(currency=tzs, update=options["update"])

        self.stdout.write(self.style.SUCCESS("Master inventory seeded successfully."))
        self.stdout.write(f"  Categories created: {stats['categories_created']}")
        self.stdout.write(f"  Categories updated: {stats['categories_updated']}")
        self.stdout.write(f"  Items created: {stats['items_created']}")
        self.stdout.write(f"  Items updated: {stats['items_updated']}")
        self.stdout.write(f"  Items unchanged: {stats['items_unchanged']}")
