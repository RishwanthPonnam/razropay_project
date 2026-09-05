"""
Django Admin registration for Merchant and MerchantPolicy.
"""

from django.contrib import admin

from .models import Merchant, MerchantPolicy


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("id", "business_name", "email", "created_at")
    search_fields = ("business_name", "email")
    ordering = ("business_name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(MerchantPolicy)
class MerchantPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "merchant",
        "minimum_margin_percent",
        "maximum_discount_percent",
        "maximum_negotiation_rounds",
        "auto_approval_limit",
    )
    search_fields = ("merchant__business_name",)
    list_select_related = ("merchant",)
    readonly_fields = ("created_at", "updated_at")
