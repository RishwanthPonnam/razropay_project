"""
Management command: seed_demo

Creates (or safely updates) a demo merchant, its policy, and a set of
realistic products so developers and future AI agents have data to work with
immediately after cloning the project.

Usage:
    python manage.py seed_demo

Idempotency guarantee:
    Uses update_or_create / get_or_create throughout, so running the command
    multiple times produces exactly one merchant, one policy, and one copy of
    each product — no duplicates ever.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from merchants.models import Merchant, MerchantPolicy
from products.models import Product


# ---------------------------------------------------------------------------
# Demo data definitions
# ---------------------------------------------------------------------------

DEMO_MERCHANT = {
    "business_name": "NovaTech Store",
    "email": "demo@novatech.test",
    "description": (
        "NovaTech Store is a premium consumer-electronics retailer "
        "specialising in audio, gaming peripherals, displays and laptops."
    ),
}

DEMO_POLICY = {
    "minimum_margin_percent": Decimal("18.00"),
    "maximum_discount_percent": Decimal("10.00"),
    "maximum_negotiation_rounds": 3,
    "auto_approval_limit": Decimal("25000.00"),
}

DEMO_PRODUCTS = [
    {
        "name": "Wireless ANC Headphones",
        "description": (
            "Premium over-ear headphones with active noise cancellation, "
            "30-hour battery life, and Hi-Res Audio certification. "
            "Features Bluetooth 5.3, multipoint pairing, and a foldable "
            "design for easy portability."
        ),
        "category": "Audio",
        "price": Decimal("5499.00"),
        "cost_price": Decimal("3800.00"),
        "inventory_quantity": 42,
    },
    {
        "name": "Mechanical Gaming Keyboard",
        "description": (
            "Tenkeyless mechanical keyboard with Cherry MX Red switches, "
            "per-key RGB lighting, anti-ghosting, and a detachable USB-C "
            "braided cable. Aluminum top frame for durability."
        ),
        "category": "Gaming",
        "price": Decimal("3999.00"),
        "cost_price": Decimal("2700.00"),
        "inventory_quantity": 25,
    },
    {
        "name": "Gaming Mouse",
        "description": (
            "Lightweight ergonomic gaming mouse with a 25K DPI optical sensor, "
            "6 programmable buttons, and ultra-fast 1000 Hz polling rate. "
            "RGB lighting and ambidextrous design."
        ),
        "category": "Gaming",
        "price": Decimal("1999.00"),
        "cost_price": Decimal("1200.00"),
        "inventory_quantity": 50,
    },
    {
        "name": "27-inch Gaming Monitor",
        "description": (
            "27-inch IPS gaming monitor with 2560×1440 QHD resolution, "
            "165 Hz refresh rate, 1ms GtG response time, and AMD FreeSync "
            "Premium Pro. HDR400 with 95 % DCI-P3 colour coverage."
        ),
        "category": "Monitors",
        "price": Decimal("24999.00"),
        "cost_price": Decimal("19000.00"),
        "inventory_quantity": 12,
    },
    {
        "name": "Performance Laptop",
        "description": (
            "14-inch professional laptop powered by the latest Intel Core "
            "Ultra 9 processor, 32 GB LPDDR5X RAM, 1 TB NVMe SSD, and a "
            "dedicated GPU. Thin-and-light chassis with a 2.8K OLED display "
            "and all-day battery life."
        ),
        "category": "Laptops",
        "price": Decimal("64999.00"),
        "cost_price": Decimal("45000.00"),
        "inventory_quantity": 8,
    },
]


class Command(BaseCommand):
    help = "Seed the database with NovaTech Store demo data (idempotent)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== Seeding demo data ==="))

        # ----------------------------------------------------------------
        # 1. Merchant
        # ----------------------------------------------------------------
        merchant, created = Merchant.objects.update_or_create(
            email=DEMO_MERCHANT["email"],
            defaults={
                "business_name": DEMO_MERCHANT["business_name"],
                "description": DEMO_MERCHANT["description"],
            },
        )
        status_label = "CREATED" if created else "EXISTS "
        self.stdout.write(
            self.style.SUCCESS(f"  [{status_label}] Merchant: {merchant.business_name}")
        )

        # ----------------------------------------------------------------
        # 2. Policy
        # ----------------------------------------------------------------
        policy, policy_created = MerchantPolicy.objects.update_or_create(
            merchant=merchant,
            defaults=DEMO_POLICY,
        )
        policy_label = "CREATED" if policy_created else "EXISTS "
        self.stdout.write(
            self.style.SUCCESS(f"  [{policy_label}] MerchantPolicy for {merchant.business_name}")
        )

        # ----------------------------------------------------------------
        # 3. Products  (keyed on merchant + name for idempotency)
        # ----------------------------------------------------------------
        for product_data in DEMO_PRODUCTS:
            product, prod_created = Product.objects.update_or_create(
                merchant=merchant,
                name=product_data["name"],
                defaults={k: v for k, v in product_data.items() if k != "name"},
            )
            prod_label = "CREATED" if prod_created else "EXISTS "
            self.stdout.write(
                self.style.SUCCESS(
                    f"  [{prod_label}] Product: {product.name} "
                    f"(INR {product.price}, qty {product.inventory_quantity})"
                )
            )

        self.stdout.write(self.style.SUCCESS("\nDemo data seeded successfully [OK]"))
