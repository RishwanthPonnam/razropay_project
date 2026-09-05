"""
Django Admin registration for Product.
"""

from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "merchant",
        "category",
        "price",
        "cost_price",
        "inventory_quantity",
        "is_active",
    )
    list_filter = ("is_active", "category", "merchant")
    search_fields = ("name", "merchant__business_name", "category")
    ordering = ("merchant", "name")
    list_select_related = ("merchant",)
    readonly_fields = ("created_at", "updated_at")
