"""
DRF Serializers for Merchant and MerchantPolicy.

MerchantSerializer       — used for list / create endpoints.
MerchantDetailSerializer — used for the single-merchant detail endpoint;
                           embeds policy and exposes an annotated product_count.
MerchantPolicySerializer — used for policy retrieve/update endpoints.
"""

from rest_framework import serializers

from .models import Merchant, MerchantPolicy


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = [
            "id",
            "business_name",
            "email",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MerchantPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantPolicy
        fields = [
            "id",
            "merchant",
            "minimum_margin_percent",
            "maximum_discount_percent",
            "maximum_negotiation_rounds",
            "auto_approval_limit",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "merchant", "created_at", "updated_at"]

    def validate_minimum_margin_percent(self, value):
        if value < 0:
            raise serializers.ValidationError("Minimum margin cannot be negative.")
        if value > 100:
            raise serializers.ValidationError("Minimum margin cannot exceed 100 %.")
        return value

    def validate_maximum_discount_percent(self, value):
        if value < 0:
            raise serializers.ValidationError("Discount percentage cannot be negative.")
        if value > 100:
            raise serializers.ValidationError(
                "Discount percentage cannot exceed 100 %."
            )
        return value

    def validate_maximum_negotiation_rounds(self, value):
        if value < 1:
            raise serializers.ValidationError(
                "Negotiation rounds must be at least 1."
            )
        return value

    def validate_auto_approval_limit(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Auto-approval limit cannot be negative."
            )
        return value


class MerchantPolicyInlineSerializer(serializers.ModelSerializer):
    """Compact policy representation embedded inside MerchantDetailSerializer."""

    class Meta:
        model = MerchantPolicy
        fields = [
            "minimum_margin_percent",
            "maximum_discount_percent",
            "maximum_negotiation_rounds",
            "auto_approval_limit",
        ]


class MerchantDetailSerializer(serializers.ModelSerializer):
    """
    Rich merchant detail — used by GET /api/merchants/<id>/.

    Expects the queryset to have been annotated with `product_count`
    (via django.db.models.Count) so no extra database query is needed.

    Also expects select_related("policy") so the nested policy data
    is fetched in the same SQL join.
    """

    policy = MerchantPolicyInlineSerializer(read_only=True)
    # Reads from the `product_count` annotation added in the view's queryset.
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Merchant
        fields = [
            "id",
            "business_name",
            "email",
            "description",
            "policy",
            "product_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
