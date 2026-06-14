"""Serializers for sales order workflow actions."""

from decimal import Decimal

from rest_framework import serializers

from apps.sales.models import (
    SalesOrderDeliveryCost,
    SalesOrderDispatchAssignment,
    SalesOrderPaymentProof,
    SalesOrderPickupDetail,
)


class DeliveryCostSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrderDeliveryCost
        fields = [
            "delivery_distance_km",
            "transport_method",
            "vehicle_type",
            "fuel_cost",
            "loading_cost",
            "offloading_cost",
            "additional_charges",
            "total_delivery_cost",
            "notes",
        ]
        read_only_fields = ["total_delivery_cost"]


class PaymentProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrderPaymentProof
        fields = [
            "id",
            "amount",
            "payment_method",
            "reference_number",
            "proof_notes",
            "status",
            "verified_at",
            "failure_reason",
            "created_at",
        ]
        read_only_fields = ["id", "status", "verified_at", "failure_reason", "created_at"]


class OptionalDecimalField(serializers.DecimalField):
    """Accept blank/null and normalize to 2 decimal places."""

    def to_internal_value(self, data):
        if data in (None, ""):
            return None
        try:
            return Decimal(str(data)).quantize(Decimal("0.01"))
        except Exception as exc:
            raise serializers.ValidationError("A valid number is required.") from exc


class PaymentProofSubmitSerializer(serializers.Serializer):
    amount = OptionalDecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
    )
    payment_method = serializers.ChoiceField(
        choices=SalesOrderPaymentProof.METHOD_CHOICES
    )
    reference_number = serializers.CharField(max_length=100)
    proof_notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        order = self.context.get("order")
        amount = attrs.get("amount")
        if amount is None and order is not None:
            amount = (order.total_amount + order.delivery_cost).quantize(Decimal("0.01"))
            attrs["amount"] = amount
        if amount is None or amount <= 0:
            raise serializers.ValidationError(
                {"amount": "Enter a valid payment amount greater than zero."}
            )
        return attrs


class PaymentVerifySerializer(serializers.Serializer):
    proof_id = serializers.IntegerField(required=False)
    approved = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class DeliveryMethodSerializer(serializers.Serializer):
    delivery_method = serializers.ChoiceField(
        choices=[("PICKUP", "Pickup"), ("COMPANY", "Company"), ("THIRD_PARTY", "Third Party")]
    )


class VehicleAssignmentSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField()
    driver_id = serializers.IntegerField()
    driver_phone = serializers.CharField(required=False, allow_blank=True)
    dispatch_date = serializers.DateField(required=False)


class ThirdPartyAssignmentSerializer(serializers.Serializer):
    transport_company = serializers.CharField(max_length=255)
    tracking_number = serializers.CharField(required=False, allow_blank=True)
    contact_person = serializers.CharField(required=False, allow_blank=True)
    contact_phone = serializers.CharField(required=False, allow_blank=True)
    dispatch_date = serializers.DateField(required=False)


class PickupConfirmSerializer(serializers.Serializer):
    pickup_date = serializers.DateField()
    receiver_name = serializers.CharField(max_length=150)
    receiver_phone = serializers.CharField(max_length=30)
    signature_data = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class DeliveryConfirmSerializer(serializers.Serializer):
    receiver_name = serializers.CharField(max_length=150)
    receiver_phone = serializers.CharField(max_length=30)
    delivery_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    signature_data = serializers.CharField(required=False, allow_blank=True)


class RejectQuotationSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)


class PartialStockSerializer(serializers.Serializer):
    partial = serializers.BooleanField(default=False)


class ProcurementRequestSerializer(serializers.Serializer):
    department_id = serializers.IntegerField(required=False)


class DispatchAssignmentSerializer(serializers.ModelSerializer):
    vehicle_registration = serializers.CharField(
        source="vehicle.registration_number", read_only=True, allow_null=True
    )
    vehicle_make = serializers.CharField(source="vehicle.make", read_only=True, allow_null=True)
    vehicle_model = serializers.CharField(source="vehicle.model", read_only=True, allow_null=True)
    vehicle_type = serializers.CharField(source="vehicle.vehicle_type", read_only=True, allow_null=True)
    driver_name = serializers.CharField(
        source="driver.user.get_full_name", read_only=True, allow_null=True
    )
    driver_license = serializers.CharField(
        source="driver.license_number", read_only=True, allow_null=True
    )

    class Meta:
        model = SalesOrderDispatchAssignment
        fields = [
            "assignment_type",
            "vehicle",
            "vehicle_registration",
            "vehicle_make",
            "vehicle_model",
            "vehicle_type",
            "driver",
            "driver_name",
            "driver_license",
            "driver_phone",
            "dispatch_date",
            "transport_company",
            "tracking_number",
            "contact_person",
            "contact_phone",
        ]


class PickupDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrderPickupDetail
        fields = [
            "pickup_date",
            "receiver_name",
            "receiver_phone",
            "signature_data",
            "notes",
        ]
