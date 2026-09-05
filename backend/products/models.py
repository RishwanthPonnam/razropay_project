"""
Product model.

Each Product belongs to a Merchant. Monetary values use DecimalField
(never FloatField) to avoid floating-point rounding errors in commerce
calculations.
"""

from django.core.validators import MinValueValidator
from django.db import models

from merchants.models import Merchant


class Product(models.Model):
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,  # Prevent silent orphan creation.
        related_name="products",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=100, blank=True, default="")

    # --- monetary fields (DecimalField — never FloatField for money) ----
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0, message="Price cannot be negative.")],
        help_text="Selling price in INR.",
    )
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0, message="Cost price cannot be negative.")],
        help_text="Internal cost / COGS in INR.",
    )

    # --- inventory ------------------------------------------------------
    inventory_quantity = models.IntegerField(
        default=0,
        validators=[
            MinValueValidator(0, message="Inventory quantity cannot be negative.")
        ],
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["merchant", "name"]
        indexes = [
            models.Index(fields=["merchant"], name="product_merchant_idx"),
            models.Index(fields=["category"], name="product_category_idx"),
            models.Index(fields=["is_active"], name="product_is_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.merchant.business_name})"
