"""
Automated tests for Merchant OS AI — Steps 3 & 4.

Step 3 tests (27 existing):
    Model tests  1–7
    API tests    8–10

Step 4 tests (new):
    11. Seed command — creates demo merchant
    12. Seed command — creates exactly one policy
    13. Seed command — creates expected products
    14. Seed command — idempotent (no duplicates on second run)
    15. Product filter — merchant_id
    16. Product filter — category
    17. Product filter — search
    18. Product filter — min_price
    19. Product filter — max_price
    20. Product filter — in_stock=true
    21. Product filter — multiple filters combined
    22. Merchant detail — merchant information present
    23. Merchant detail — policy embedded
    24. Merchant detail — product_count correct
"""

from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from merchants.models import Merchant, MerchantPolicy
from products.models import Product


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_merchant(**kwargs):
    defaults = {"business_name": "Test Corp", "email": "test@corp.com"}
    defaults.update(kwargs)
    return Merchant.objects.create(**defaults)


def make_product(merchant, **kwargs):
    defaults = {
        "name": "Widget A",
        "price": Decimal("100.00"),
        "cost_price": Decimal("60.00"),
        "inventory_quantity": 10,
    }
    defaults.update(kwargs)
    return Product.objects.create(merchant=merchant, **defaults)


# ===========================================================================
# STEP 3 TESTS  (unchanged — must continue to pass)
# ===========================================================================


class MerchantModelTest(TestCase):
    """Test 1: Merchant creation"""

    def test_create_merchant(self):
        merchant = make_merchant()
        self.assertEqual(merchant.business_name, "Test Corp")
        self.assertEqual(merchant.email, "test@corp.com")
        self.assertIsNotNone(merchant.pk)
        self.assertIsNotNone(merchant.created_at)

    def test_merchant_str(self):
        merchant = make_merchant()
        self.assertEqual(str(merchant), "Test Corp")


class ProductModelTest(TestCase):
    """Tests 2, 3, 4, 5"""

    def setUp(self):
        self.merchant = make_merchant()

    def test_create_product(self):
        """Test 2: Product creation"""
        product = make_product(self.merchant)
        self.assertEqual(product.name, "Widget A")
        self.assertEqual(product.merchant, self.merchant)
        self.assertEqual(product.price, Decimal("100.00"))

    def test_product_belongs_to_merchant(self):
        """Test 3: Product must belong to a merchant"""
        product = make_product(self.merchant)
        self.assertEqual(product.merchant.pk, self.merchant.pk)
        self.assertIn(product, self.merchant.products.all())

    def test_negative_inventory_fails(self):
        """Test 4: Negative inventory should fail model validation"""
        product = Product(
            merchant=self.merchant,
            name="Bad Stock",
            price=Decimal("50.00"),
            cost_price=Decimal("30.00"),
            inventory_quantity=-1,
        )
        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_negative_price_fails(self):
        """Test 5a: Negative price should fail model validation"""
        product = Product(
            merchant=self.merchant,
            name="Negative Price",
            price=Decimal("-1.00"),
            cost_price=Decimal("10.00"),
            inventory_quantity=5,
        )
        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_negative_cost_price_fails(self):
        """Test 5b: Negative cost_price should fail model validation"""
        product = Product(
            merchant=self.merchant,
            name="Negative Cost",
            price=Decimal("10.00"),
            cost_price=Decimal("-5.00"),
            inventory_quantity=5,
        )
        with self.assertRaises(ValidationError):
            product.full_clean()


class MerchantPolicyModelTest(TestCase):
    """Tests 6, 7"""

    def setUp(self):
        self.merchant = make_merchant()

    def test_create_policy(self):
        """Test 6: MerchantPolicy creation"""
        policy = MerchantPolicy.objects.create(
            merchant=self.merchant,
            minimum_margin_percent=Decimal("18.00"),
            maximum_discount_percent=Decimal("10.00"),
            maximum_negotiation_rounds=3,
            auto_approval_limit=Decimal("25000.00"),
        )
        self.assertEqual(policy.merchant, self.merchant)
        self.assertEqual(policy.minimum_margin_percent, Decimal("18.00"))
        self.assertEqual(policy.maximum_negotiation_rounds, 3)

    def test_negative_margin_fails(self):
        """Test 7a: Negative minimum_margin_percent should fail"""
        policy = MerchantPolicy(
            merchant=self.merchant,
            minimum_margin_percent=Decimal("-1.00"),
            maximum_discount_percent=Decimal("10.00"),
            maximum_negotiation_rounds=3,
            auto_approval_limit=Decimal("25000.00"),
        )
        with self.assertRaises(ValidationError):
            policy.full_clean()

    def test_margin_over_100_fails(self):
        """Test 7b: minimum_margin_percent > 100 should fail"""
        policy = MerchantPolicy(
            merchant=self.merchant,
            minimum_margin_percent=Decimal("101.00"),
            maximum_discount_percent=Decimal("10.00"),
            maximum_negotiation_rounds=3,
            auto_approval_limit=Decimal("25000.00"),
        )
        with self.assertRaises(ValidationError):
            policy.full_clean()

    def test_discount_over_100_fails(self):
        """Test 7c: maximum_discount_percent > 100 should fail"""
        policy = MerchantPolicy(
            merchant=self.merchant,
            minimum_margin_percent=Decimal("18.00"),
            maximum_discount_percent=Decimal("110.00"),
            maximum_negotiation_rounds=3,
            auto_approval_limit=Decimal("25000.00"),
        )
        with self.assertRaises(ValidationError):
            policy.full_clean()

    def test_negative_auto_approval_limit_fails(self):
        """Test 7d: Negative auto_approval_limit should fail"""
        policy = MerchantPolicy(
            merchant=self.merchant,
            minimum_margin_percent=Decimal("18.00"),
            maximum_discount_percent=Decimal("10.00"),
            maximum_negotiation_rounds=3,
            auto_approval_limit=Decimal("-100.00"),
        )
        with self.assertRaises(ValidationError):
            policy.full_clean()


class MerchantAPITest(TestCase):
    """Test 8: Merchant API"""

    def setUp(self):
        self.client = APIClient()

    def test_list_merchants_empty(self):
        response = self.client.get("/api/merchants/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_create_merchant(self):
        payload = {
            "business_name": "Alpha Store",
            "email": "alpha@store.com",
            "description": "A test store.",
        }
        response = self.client.post("/api/merchants/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["business_name"], "Alpha Store")
        self.assertEqual(response.data["email"], "alpha@store.com")

    def test_create_merchant_duplicate_email_fails(self):
        make_merchant(email="dup@test.com")
        payload = {"business_name": "Dup Store", "email": "dup@test.com"}
        response = self.client.post("/api/merchants/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_merchant(self):
        merchant = make_merchant()
        response = self.client.get(f"/api/merchants/{merchant.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], merchant.pk)

    def test_retrieve_nonexistent_merchant_returns_404(self):
        response = self.client.get("/api/merchants/99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProductAPITest(TestCase):
    """Test 9: Product API"""

    def setUp(self):
        self.client = APIClient()
        self.merchant = make_merchant()

    def test_list_products_empty(self):
        response = self.client.get("/api/products/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_create_product(self):
        payload = {
            "merchant": self.merchant.pk,
            "name": "Gadget X",
            "price": "299.99",
            "cost_price": "150.00",
            "inventory_quantity": 25,
            "category": "Electronics",
        }
        response = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Gadget X")
        self.assertEqual(response.data["merchant"], self.merchant.pk)

    def test_create_product_negative_price_fails(self):
        payload = {
            "merchant": self.merchant.pk,
            "name": "Bad Price",
            "price": "-10.00",
            "cost_price": "5.00",
            "inventory_quantity": 1,
        }
        response = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_product_negative_inventory_fails(self):
        payload = {
            "merchant": self.merchant.pk,
            "name": "Bad Stock",
            "price": "50.00",
            "cost_price": "20.00",
            "inventory_quantity": -5,
        }
        response = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_product(self):
        product = make_product(self.merchant)
        response = self.client.get(f"/api/products/{product.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], product.pk)


class PolicyAPITest(TestCase):
    """Test 10: Policy API"""

    def setUp(self):
        self.client = APIClient()
        self.merchant = make_merchant()

    def test_get_policy_auto_creates_with_defaults(self):
        response = self.client.get(f"/api/policies/{self.merchant.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["merchant"], self.merchant.pk)

    def test_update_policy_put(self):
        payload = {
            "minimum_margin_percent": "18.00",
            "maximum_discount_percent": "10.00",
            "maximum_negotiation_rounds": 3,
            "auto_approval_limit": "25000.00",
        }
        response = self.client.put(
            f"/api/policies/{self.merchant.pk}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["minimum_margin_percent"], "18.00")
        self.assertEqual(response.data["maximum_negotiation_rounds"], 3)

    def test_update_policy_patch(self):
        payload = {"maximum_discount_percent": "15.00"}
        response = self.client.patch(
            f"/api/policies/{self.merchant.pk}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["maximum_discount_percent"], "15.00")

    def test_invalid_policy_discount_over_100_fails(self):
        payload = {
            "minimum_margin_percent": "18.00",
            "maximum_discount_percent": "150.00",
            "maximum_negotiation_rounds": 3,
            "auto_approval_limit": "25000.00",
        }
        response = self.client.put(
            f"/api/policies/{self.merchant.pk}/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_policy_for_nonexistent_merchant_returns_404(self):
        response = self.client.get("/api/policies/99999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ===========================================================================
# STEP 4 TESTS  (new)
# ===========================================================================


class SeedDemoCommandTest(TestCase):
    """Tests 11–14: seed_demo management command"""

    def _run_seed(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        return out.getvalue()

    def test_seed_creates_demo_merchant(self):
        """Test 11: seed_demo creates the NovaTech demo merchant"""
        self._run_seed()
        self.assertTrue(
            Merchant.objects.filter(email="demo@novatech.test").exists()
        )

    def test_seed_creates_exactly_one_policy(self):
        """Test 12: seed_demo creates exactly one policy for demo merchant"""
        self._run_seed()
        merchant = Merchant.objects.get(email="demo@novatech.test")
        policy_count = MerchantPolicy.objects.filter(merchant=merchant).count()
        self.assertEqual(policy_count, 1)
        policy = MerchantPolicy.objects.get(merchant=merchant)
        self.assertEqual(policy.minimum_margin_percent, Decimal("18.00"))
        self.assertEqual(policy.maximum_discount_percent, Decimal("10.00"))
        self.assertEqual(policy.maximum_negotiation_rounds, 3)
        self.assertEqual(policy.auto_approval_limit, Decimal("25000.00"))

    def test_seed_creates_expected_products(self):
        """Test 13: seed_demo creates all 5 expected products"""
        self._run_seed()
        merchant = Merchant.objects.get(email="demo@novatech.test")
        product_count = Product.objects.filter(merchant=merchant).count()
        self.assertEqual(product_count, 5)

        expected_names = {
            "Wireless ANC Headphones",
            "Mechanical Gaming Keyboard",
            "Gaming Mouse",
            "27-inch Gaming Monitor",
            "Performance Laptop",
        }
        actual_names = set(
            Product.objects.filter(merchant=merchant).values_list("name", flat=True)
        )
        self.assertEqual(expected_names, actual_names)

    def test_seed_is_idempotent(self):
        """Test 14: running seed_demo twice does not create duplicate records"""
        self._run_seed()
        self._run_seed()  # second run

        merchant_count = Merchant.objects.filter(email="demo@novatech.test").count()
        self.assertEqual(merchant_count, 1)

        merchant = Merchant.objects.get(email="demo@novatech.test")
        policy_count = MerchantPolicy.objects.filter(merchant=merchant).count()
        self.assertEqual(policy_count, 1)

        product_count = Product.objects.filter(merchant=merchant).count()
        self.assertEqual(product_count, 5)


class ProductFilterTest(TestCase):
    """Tests 15–21: Product list API filtering"""

    def setUp(self):
        self.client = APIClient()
        self.merchant_a = make_merchant(
            business_name="Store A", email="a@store.com"
        )
        self.merchant_b = make_merchant(
            business_name="Store B", email="b@store.com"
        )
        # merchant_a products
        self.headphones = make_product(
            self.merchant_a,
            name="Wireless ANC Headphones",
            category="Audio",
            price=Decimal("5499.00"),
            cost_price=Decimal("3800.00"),
            inventory_quantity=10,
        )
        self.keyboard = make_product(
            self.merchant_a,
            name="Mechanical Gaming Keyboard",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            inventory_quantity=0,  # out of stock
        )
        self.mouse = make_product(
            self.merchant_a,
            name="Gaming Mouse",
            category="Gaming",
            price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"),
            inventory_quantity=50,
        )
        # merchant_b product
        self.laptop = make_product(
            self.merchant_b,
            name="Performance Laptop",
            category="Laptops",
            price=Decimal("64999.00"),
            cost_price=Decimal("52000.00"),
            inventory_quantity=5,
        )

    def test_filter_by_merchant_id(self):
        """Test 15"""
        response = self.client.get(
            f"/api/products/?merchant_id={self.merchant_a.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {p["id"] for p in response.data}
        self.assertIn(self.headphones.pk, returned_ids)
        self.assertIn(self.keyboard.pk, returned_ids)
        self.assertIn(self.mouse.pk, returned_ids)
        self.assertNotIn(self.laptop.pk, returned_ids)

    def test_filter_by_category(self):
        """Test 16"""
        response = self.client.get("/api/products/?category=Gaming")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in response.data]
        self.assertIn("Mechanical Gaming Keyboard", names)
        self.assertIn("Gaming Mouse", names)
        self.assertNotIn("Wireless ANC Headphones", names)

    def test_filter_by_search(self):
        """Test 17"""
        response = self.client.get("/api/products/?search=headphones")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in response.data]
        self.assertIn("Wireless ANC Headphones", names)
        self.assertNotIn("Gaming Mouse", names)

    def test_filter_by_min_price(self):
        """Test 18"""
        response = self.client.get("/api/products/?min_price=4000")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prices = [Decimal(p["price"]) for p in response.data]
        for price in prices:
            self.assertGreaterEqual(price, Decimal("4000"))
        returned_ids = {p["id"] for p in response.data}
        self.assertNotIn(self.mouse.pk, returned_ids)  # 1999

    def test_filter_by_max_price(self):
        """Test 19"""
        response = self.client.get("/api/products/?max_price=5000")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        prices = [Decimal(p["price"]) for p in response.data]
        for price in prices:
            self.assertLessEqual(price, Decimal("5000"))
        returned_ids = {p["id"] for p in response.data}
        self.assertNotIn(self.laptop.pk, returned_ids)  # 64999

    def test_filter_in_stock_true(self):
        """Test 20: in_stock=true excludes zero-inventory items"""
        response = self.client.get("/api/products/?in_stock=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {p["id"] for p in response.data}
        self.assertNotIn(self.keyboard.pk, returned_ids)  # qty=0
        self.assertIn(self.mouse.pk, returned_ids)
        self.assertIn(self.headphones.pk, returned_ids)

    def test_multiple_filters_combined(self):
        """Test 21: category=Gaming & max_price=5000 & in_stock=true"""
        response = self.client.get(
            "/api/products/?category=Gaming&max_price=5000&in_stock=true"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Only Gaming Mouse qualifies (keyboard is out of stock)
        returned_ids = {p["id"] for p in response.data}
        self.assertIn(self.mouse.pk, returned_ids)
        self.assertNotIn(self.keyboard.pk, returned_ids)  # out of stock
        self.assertNotIn(self.headphones.pk, returned_ids)  # wrong category


class MerchantDetailAPITest(TestCase):
    """Tests 22–24: enriched merchant detail endpoint"""

    def setUp(self):
        self.client = APIClient()
        self.merchant = make_merchant()
        # Add 3 products
        for i in range(3):
            make_product(
                self.merchant,
                name=f"Product {i}",
                price=Decimal("100.00"),
                cost_price=Decimal("60.00"),
                inventory_quantity=10,
            )
        # Add policy
        MerchantPolicy.objects.create(
            merchant=self.merchant,
            minimum_margin_percent=Decimal("20.00"),
            maximum_discount_percent=Decimal("8.00"),
            maximum_negotiation_rounds=2,
            auto_approval_limit=Decimal("10000.00"),
        )

    def test_merchant_detail_information(self):
        """Test 22: detail response contains merchant information"""
        response = self.client.get(f"/api/merchants/{self.merchant.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.merchant.pk)
        self.assertEqual(response.data["business_name"], self.merchant.business_name)
        self.assertEqual(response.data["email"], self.merchant.email)

    def test_merchant_detail_includes_policy(self):
        """Test 23: detail response embeds policy information"""
        response = self.client.get(f"/api/merchants/{self.merchant.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("policy", response.data)
        policy = response.data["policy"]
        self.assertIsNotNone(policy)
        self.assertEqual(policy["minimum_margin_percent"], "20.00")
        self.assertEqual(policy["maximum_discount_percent"], "8.00")
        self.assertEqual(policy["maximum_negotiation_rounds"], 2)

    def test_merchant_detail_product_count(self):
        """Test 24: detail response shows correct product count"""
        response = self.client.get(f"/api/merchants/{self.merchant.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["product_count"], 3)
