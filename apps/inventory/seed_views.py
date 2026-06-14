"""API endpoints for master inventory seeding."""

from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.views import APIView

from apps.core.responses import api_error, api_response
from apps.inventory.seeders.master_inventory import preview_master_inventory, seed_master_inventory


class InventoryMasterSeedView(APIView):
    """
    GET  — preview master catalogue vs database
    POST — seed categories and items (staff only)
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        return api_response(data=preview_master_inventory())

    def post(self, request):
        update = bool(request.data.get("update", False))
        try:
            stats = seed_master_inventory(update=update)
        except ValueError as exc:
            return api_error(message=str(exc))
        return api_response(
            data=stats,
            message="Master inventory catalogue seeded successfully",
        )
