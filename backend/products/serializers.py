"""
DRF Serializers for Product.
"""

from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id",
            "merchant",
            "name",
            "description",
            "category",
            "price",
            "cost_price",
            "inventory_quantity",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value

    def validate_cost_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Cost price cannot be negative.")
        return value

    def validate_inventory_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Inventory quantity cannot be negative."
            )
        return value
