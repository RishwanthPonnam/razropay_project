"""
Merchant and MerchantPolicy models.

Merchant      — represents a business registered on the platform.
MerchantPolicy — stores the economic guardrails within which the future
                 AI Revenue Agent is permitted to operate (margins,
                 discounts, negotiation rounds, auto-approval ceiling).
"""

from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models


class Merchant(models.Model):
    business_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["business_name"]
        indexes = [
            models.Index(fields=["email"], name="merchant_email_idx"),
        ]

    def __str__(self) -> str:
        return self.business_name


class MerchantPolicy(models.Model):
    """
    One-to-one policy record per merchant.

    All percentage fields are stored as whole numbers (e.g. 18 means 18 %).
    auto_approval_limit is a monetary ceiling (INR) below which the AI
    agent may approve a deal without human review.
    """

    merchant = models.OneToOneField(
        Merchant,
        on_delete=models.CASCADE,
        related_name="policy",
    )

    # --- margin / discount guardrails -----------------------------------
    minimum_margin_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(0, message="Minimum margin cannot be negative."),
            MaxValueValidator(100, message="Minimum margin cannot exceed 100 %."),
        ],
        help_text="Minimum acceptable gross-margin % the AI must preserve.",
    )
    maximum_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[
            MinValueValidator(0, message="Discount percentage cannot be negative."),
            MaxValueValidator(100, message="Discount percentage cannot exceed 100 %."),
        ],
        help_text="Maximum discount % the AI is allowed to offer.",
    )

    # --- negotiation guardrails -----------------------------------------
    maximum_negotiation_rounds = models.PositiveIntegerField(
        validators=[
            MinValueValidator(1, message="Negotiation rounds must be at least 1."),
        ],
        help_text="Maximum number of back-and-forth negotiation turns allowed.",
    )

    # --- financial ceiling ----------------------------------------------
    auto_approval_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(0, message="Auto-approval limit cannot be negative."),
        ],
        help_text=(
            "Deal value (in INR) below which the AI may approve automatically "
            "without human intervention."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Merchant Policy"
        verbose_name_plural = "Merchant Policies"

    def __str__(self) -> str:
        return f"Policy for {self.merchant.business_name}"
