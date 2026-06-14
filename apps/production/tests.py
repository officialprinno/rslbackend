from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.production.models import Machine
from apps.users.models import Department, Role

User = get_user_model()


class MachineHistoryTests(TestCase):
    def setUp(self):
        dept, _ = Department.objects.get_or_create(
            name="Production",
            defaults={"description": "Production", "is_active": True},
        )
        role, _ = Role.objects.get_or_create(
            name="Machine Operator",
            department=dept,
            defaults={"is_active": True},
        )
        self.user = User.objects.create_user(
            email="history-test-operator@rocksolutions.co.tz",
            password="Operator@2024",
            first_name="Test",
            last_name="Operator",
            department=dept,
            role=role,
        )
        self.machine = Machine.objects.create(
            machine_code="TEST-MCH-01",
            name="Test Machine",
            machine_type=Machine.TYPE_OTHER,
            status=Machine.STATUS_ACTIVE,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_machine_history_returns_200(self):
        response = self.client.get(f"/api/v1/production/machines/{self.machine.id}/history/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertIn("usage", body["data"])
        self.assertIn("services", body["data"])
        self.assertIn("breakdowns", body["data"])
        self.assertIn("hours_this_month", body["data"])
