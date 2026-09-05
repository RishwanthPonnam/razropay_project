"""
Tests for Step 5, 5.5 & 6 — Intent Engine + Relevance Scoring + Revenue Engine.

Step 5 tests (tests 1-10 + API tests 17-21):
    Intent parsing
    Product matching — hard-filter correctness
    Intent API contract

Step 5.5 tests (tests R1-R10):
    Relevance scoring and type-aware ranking

Step 6 tests (D1-D5, N1, U1-U4, B1-B4, S1-S4, A1-A6):
    Revenue Opportunity Engine
    Discount / No-action / Upsell / Bundle / Scoring / API
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from merchants.models import Merchant, MerchantPolicy
from products.models import Product
from ai.services.intent_engine import extract_intent, BuyerIntent
from ai.services.product_matcher import find_matching_products


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_merchant(**kwargs):
    defaults = {"business_name": "AI Test Store", "email": "aitest@store.com"}
    defaults.update(kwargs)
    return Merchant.objects.create(**defaults)


def make_product(merchant, **kwargs):
    defaults = {
        "name": "Test Product",
        "category": "Gaming",
        "price": Decimal("2000.00"),
        "cost_price": Decimal("1200.00"),
        "inventory_quantity": 10,
        "is_active": True,
        "description": "",
    }
    defaults.update(kwargs)
    return Product.objects.create(merchant=merchant, **defaults)


def pks(products) -> list:
    """Extract PKs from a list of Product objects (matcher now returns list)."""
    return [p.pk for p in products]


# ===========================================================================
# STEP 5 TESTS — Intent parsing (1–10)
# ===========================================================================


class IntentParsingTest(TestCase):

    def test_01_purchase_intent_type(self):
        """Test 1: A product request is classified as purchase intent."""
        intent = extract_intent("I need a gaming keyboard under 4500")
        self.assertEqual(intent.intent_type, "purchase")

    def test_02_budget_under(self):
        """Test 2: 'under X' sets budget_max."""
        intent = extract_intent("I need a headset under 5000")
        self.assertIsNone(intent.budget_min)
        self.assertEqual(intent.budget_max, 5000.0)

    def test_03_budget_below(self):
        """Test 3: 'below X' sets budget_max."""
        intent = extract_intent("I want headphones below 3000")
        self.assertEqual(intent.budget_max, 3000.0)

    def test_04_budget_up_to(self):
        """Test 4: 'up to X' sets budget_max."""
        intent = extract_intent("Gaming mouse up to 2500")
        self.assertEqual(intent.budget_max, 2500.0)

    def test_05_quantity_extraction(self):
        """Test 5: Explicit quantity is captured."""
        intent = extract_intent("I need 2 gaming mice under 4000")
        self.assertEqual(intent.quantity, 2)

    def test_06_category_detection_audio(self):
        """Test 6: 'headset' maps to category Audio."""
        intent = extract_intent("I need a gaming headset under 4500")
        self.assertEqual(intent.category, "Audio")

    def test_06b_category_detection_gaming(self):
        """Test 6b: 'keyboard' maps to category Gaming."""
        intent = extract_intent("I need a mechanical keyboard under 5000")
        self.assertEqual(intent.category, "Gaming")

    def test_07_use_case_extraction(self):
        """Test 7: 'for FPS games' is captured as a use-case."""
        intent = extract_intent("I need a headset for FPS games under 5000")
        self.assertIsNotNone(intent.use_case)
        self.assertIn("FPS", intent.use_case)

    def test_08_requirements_populated(self):
        """Test 8: Core product type appears in requirements."""
        intent = extract_intent("I need a wireless gaming headset with microphone")
        self.assertTrue(len(intent.requirements) > 0)
        req_str = " ".join(intent.requirements)
        self.assertTrue(
            "headset" in req_str or "wireless" in req_str or "microphone" in req_str
        )

    def test_09_empty_message_returns_browse_intent(self):
        """Test 9: Empty message returns a safe default at engine level."""
        intent = extract_intent("")
        self.assertIsInstance(intent, BuyerIntent)
        self.assertEqual(intent.intent_type, "browse")

    def test_10_no_budget_gives_none(self):
        """Test 10: A message without a budget leaves budget fields as None."""
        intent = extract_intent("Show me something good for gaming")
        self.assertIsNone(intent.budget_max)
        self.assertIsNone(intent.budget_min)

    def test_product_type_populated(self):
        """Step 5.5: product_type canonical keyword is set."""
        intent = extract_intent("I need a gaming keyboard under 4500")
        self.assertEqual(intent.product_type, "keyboard")

    def test_budget_k_suffix(self):
        intent = extract_intent("I need a laptop under 50k")
        self.assertEqual(intent.budget_max, 50000.0)

    def test_budget_less_than(self):
        intent = extract_intent("headphones less than 4000")
        self.assertEqual(intent.budget_max, 4000.0)

    def test_hard_constraints_include_budget(self):
        intent = extract_intent("I need a gaming mouse under 2000")
        self.assertTrue(any("2000" in c for c in intent.hard_constraints))


# ===========================================================================
# STEP 5 TESTS — Product matching hard filters (11–16)
# Now uses list[Product] return type (matcher changed in Step 5.5)
# ===========================================================================


class ProductMatchingTest(TestCase):

    def setUp(self):
        self.merchant = make_merchant()

        self.keyboard_cheap = make_product(
            self.merchant, name="Budget Keyboard",
            category="Gaming", price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"), inventory_quantity=20,
        )
        self.keyboard_expensive = make_product(
            self.merchant, name="Premium Keyboard",
            category="Gaming", price=Decimal("8999.00"),
            cost_price=Decimal("6000.00"), inventory_quantity=5,
        )
        self.headphones = make_product(
            self.merchant, name="Studio Headphones",
            category="Audio", price=Decimal("3499.00"),
            cost_price=Decimal("2200.00"), inventory_quantity=15,
        )
        self.out_of_stock = make_product(
            self.merchant, name="Out of Stock Mouse",
            category="Gaming", price=Decimal("1500.00"),
            cost_price=Decimal("900.00"), inventory_quantity=0,
        )
        self.inactive = make_product(
            self.merchant, name="Discontinued Monitor",
            category="Monitors", price=Decimal("12000.00"),
            cost_price=Decimal("9000.00"), inventory_quantity=3,
            is_active=False,
        )

    def test_11_product_within_budget_returned(self):
        """Test 11: price <= budget_max is returned."""
        intent = BuyerIntent(
            intent_type="purchase", category="Gaming",
            budget_max=5000.0, product_type="keyboard",
        )
        result = find_matching_products(intent)
        self.assertIn(self.keyboard_cheap.pk, pks(result))

    def test_12_product_above_budget_excluded(self):
        """Test 12: price > budget_max is excluded."""
        intent = BuyerIntent(
            intent_type="purchase", category="Gaming",
            budget_max=5000.0, product_type="keyboard",
        )
        result = find_matching_products(intent)
        self.assertNotIn(self.keyboard_expensive.pk, pks(result))

    def test_13_out_of_stock_excluded(self):
        """Test 13: inventory_quantity == 0 is excluded."""
        intent = BuyerIntent(intent_type="purchase", category="Gaming")
        result = find_matching_products(intent)
        self.assertNotIn(self.out_of_stock.pk, pks(result))

    def test_14_inactive_product_excluded(self):
        """Test 14: is_active=False is excluded."""
        intent = BuyerIntent(intent_type="purchase", category="Monitors")
        result = find_matching_products(intent)
        self.assertNotIn(self.inactive.pk, pks(result))

    def test_15_category_filter_works(self):
        """Test 15: Only Audio products returned for category=Audio."""
        intent = BuyerIntent(intent_type="purchase", category="Audio")
        result = find_matching_products(intent)
        self.assertIn(self.headphones.pk, pks(result))
        self.assertNotIn(self.keyboard_cheap.pk, pks(result))

    def test_16_multiple_constraints_combined(self):
        """Test 16: category=Gaming AND budget_max=3000 together."""
        intent = BuyerIntent(
            intent_type="purchase", category="Gaming",
            budget_max=3000.0, product_type="keyboard",
        )
        result = find_matching_products(intent)
        self.assertIn(self.keyboard_cheap.pk, pks(result))
        self.assertNotIn(self.keyboard_expensive.pk, pks(result))
        self.assertNotIn(self.out_of_stock.pk, pks(result))


# ===========================================================================
# STEP 5 TESTS — Intent API (17–21)
# ===========================================================================


class IntentAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.merchant = make_merchant(
            business_name="API Test Store", email="apitest@store.com",
        )
        self.keyboard = make_product(
            self.merchant, name="Mechanical Gaming Keyboard",
            category="Gaming", price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"), inventory_quantity=25,
        )
        self.expensive = make_product(
            self.merchant, name="Premium Keyboard",
            category="Gaming", price=Decimal("9999.00"),
            cost_price=Decimal("7000.00"), inventory_quantity=5,
        )

    def test_17_valid_intent_request_returns_200(self):
        """Test 17: A valid message returns HTTP 200."""
        response = self.client.post(
            "/api/ai/intent/",
            {"message": "I need a gaming keyboard under 4500"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_18_empty_message_returns_400(self):
        """Test 18: Empty/missing message returns HTTP 400."""
        self.assertEqual(
            self.client.post("/api/ai/intent/", {"message": ""}, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post("/api/ai/intent/", {}, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_19_response_contains_structured_intent(self):
        """Test 19: Response has all required intent fields."""
        response = self.client.post(
            "/api/ai/intent/",
            {"message": "I need a gaming keyboard under 5000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("intent", response.data)
        intent = response.data["intent"]

        for field_name in [
            "intent_type", "category", "product_type", "search_query",
            "budget_min", "budget_max", "use_case",
            "requirements", "hard_constraints", "preferences",
            "urgency", "quantity",
        ]:
            self.assertIn(field_name, intent, f"Missing intent field: {field_name}")

        self.assertEqual(intent["intent_type"], "purchase")
        self.assertEqual(intent["category"], "Gaming")
        self.assertEqual(intent["product_type"], "keyboard")
        self.assertEqual(intent["budget_max"], 5000.0)

    def test_20_response_contains_matching_products(self):
        """Test 20: Matches contain budget-filtered products."""
        response = self.client.post(
            "/api/ai/intent/",
            {"message": "I need a gaming keyboard under 5000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        match_ids = [m["id"] for m in response.data["matches"]]
        self.assertIn(self.keyboard.pk, match_ids)
        self.assertNotIn(self.expensive.pk, match_ids)

    def test_21_cost_price_not_exposed(self):
        """Test 21: cost_price must NOT appear in any match result."""
        response = self.client.post(
            "/api/ai/intent/",
            {"message": "I need a gaming keyboard"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for match in response.data.get("matches", []):
            self.assertNotIn("cost_price", match)


# ===========================================================================
# STEP 5.5 TESTS — Relevance scoring (R1–R10)
# ===========================================================================


class RelevanceScoringTest(TestCase):
    """
    Tests that verify the relevance-ranked product matcher returns the
    correct product type at the top and excludes wrong-type products.
    """

    def setUp(self):
        self.merchant = make_merchant(
            business_name="Relevance Test Store", email="relevance@store.com"
        )
        self.keyboard = make_product(
            self.merchant,
            name="Mechanical Gaming Keyboard",
            description="TKL mechanical keyboard with Cherry MX switches and RGB.",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            inventory_quantity=25,
        )
        self.mouse = make_product(
            self.merchant,
            name="Gaming Mouse",
            description="Lightweight gaming mouse with 25K DPI sensor.",
            category="Gaming",
            price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"),
            inventory_quantity=50,
        )
        self.headphones = make_product(
            self.merchant,
            name="Wireless ANC Headphones",
            description="Premium over-ear headphones with active noise cancellation.",
            category="Audio",
            price=Decimal("4499.00"),
            cost_price=Decimal("3200.00"),
            inventory_quantity=30,
        )
        self.monitor = make_product(
            self.merchant,
            name="27-inch Gaming Monitor",
            description="QHD 165Hz IPS gaming monitor.",
            category="Monitors",
            price=Decimal("22999.00"),
            cost_price=Decimal("18000.00"),
            inventory_quantity=8,
        )
        self.laptop = make_product(
            self.merchant,
            name="Performance Laptop",
            description="Intel Core Ultra laptop with 32GB RAM.",
            category="Laptops",
            price=Decimal("59999.00"),
            cost_price=Decimal("48000.00"),
            inventory_quantity=5,
        )
        # Out-of-stock and inactive for exclusion tests
        self.oos_keyboard = make_product(
            self.merchant,
            name="Budget Keyboard OOS",
            description="Mechanical keyboard",
            category="Gaming",
            price=Decimal("1500.00"),
            cost_price=Decimal("900.00"),
            inventory_quantity=0,  # out of stock
        )
        self.inactive_keyboard = make_product(
            self.merchant,
            name="Legacy Keyboard",
            description="Old mechanical keyboard",
            category="Gaming",
            price=Decimal("1200.00"),
            cost_price=Decimal("700.00"),
            inventory_quantity=5,
            is_active=False,
        )

    # ── R1: gaming keyboard prioritizes keyboard ─────────────────────────────

    def test_R1_keyboard_request_prioritizes_keyboard(self):
        """Test R1: 'gaming keyboard' → keyboard is first result."""
        intent = extract_intent("I need a gaming keyboard under 4500")
        result = find_matching_products(intent)
        self.assertTrue(len(result) > 0, "Expected at least one match")
        self.assertEqual(result[0].pk, self.keyboard.pk,
                         f"Expected keyboard first, got: {result[0].name}")

    # ── R2: gaming mouse prioritizes mouse ───────────────────────────────────

    def test_R2_mouse_request_prioritizes_mouse(self):
        """Test R2: 'gaming mouse' → mouse is first result."""
        intent = extract_intent("I need a gaming mouse under 4000")
        result = find_matching_products(intent)
        self.assertTrue(len(result) > 0)
        self.assertEqual(result[0].pk, self.mouse.pk,
                         f"Expected mouse first, got: {result[0].name}")

    # ── R3: headphone request prioritizes headphones ─────────────────────────

    def test_R3_headphone_request_prioritizes_headphones(self):
        """Test R3: 'headphones below 5000' → headphones in results."""
        intent = extract_intent("I need headphones below 5000")
        result = find_matching_products(intent)
        self.assertTrue(len(result) > 0)
        self.assertEqual(result[0].pk, self.headphones.pk,
                         f"Expected headphones first, got: {result[0].name}")

    # ── R4: explicit product type excludes unrelated ─────────────────────────

    def test_R4_keyboard_request_excludes_mouse(self):
        """Test R4: 'gaming keyboard' must NOT include Gaming Mouse."""
        intent = extract_intent("I need a gaming keyboard under 4500")
        result = find_matching_products(intent)
        result_pks = pks(result)
        self.assertNotIn(
            self.mouse.pk, result_pks,
            "Gaming Mouse should be excluded from a keyboard request",
        )

    def test_R4b_mouse_request_excludes_keyboard(self):
        """Test R4b: 'gaming mouse' must NOT include keyboard."""
        intent = extract_intent("I need a gaming mouse under 4000")
        result = find_matching_products(intent)
        self.assertNotIn(
            self.keyboard.pk, pks(result),
            "Keyboard should be excluded from a mouse request",
        )

    # ── R5: budget filtering still works ────────────────────────────────────

    def test_R5_budget_filter_still_applied(self):
        """Test R5: Budget constraint remains a hard filter."""
        intent = extract_intent("I need a gaming keyboard under 2000")
        result = find_matching_products(intent)
        # keyboard is 3999 > 2000 → excluded by price filter
        self.assertNotIn(self.keyboard.pk, pks(result))

    # ── R6: out-of-stock products remain excluded ────────────────────────────

    def test_R6_out_of_stock_excluded(self):
        """Test R6: Out-of-stock products are never returned."""
        intent = extract_intent("I need a gaming keyboard")
        result = find_matching_products(intent)
        self.assertNotIn(self.oos_keyboard.pk, pks(result))

    # ── R7: inactive products remain excluded ───────────────────────────────

    def test_R7_inactive_excluded(self):
        """Test R7: Inactive products are never returned."""
        intent = extract_intent("I need a gaming keyboard")
        result = find_matching_products(intent)
        self.assertNotIn(self.inactive_keyboard.pk, pks(result))

    # ── R8: requirements affect ranking ──────────────────────────────────────

    def test_R8_requirements_boost_matching_product(self):
        """Test R8: A product mentioning a requirement ranks higher."""
        # Create two keyboards: one mentions 'mechanical', one doesn't.
        merchant2 = make_merchant(
            business_name="Req Test", email="req@test.com"
        )
        kb_mech = make_product(
            merchant2,
            name="Mechanical Keyboard Pro",
            description="Features Cherry MX mechanical switches.",
            category="Gaming",
            price=Decimal("3500.00"),
            cost_price=Decimal("2200.00"),
            inventory_quantity=10,
        )
        kb_plain = make_product(
            merchant2,
            name="Regular Keyboard",
            description="Standard membrane keyboard.",
            category="Gaming",
            price=Decimal("3600.00"),
            cost_price=Decimal("2300.00"),
            inventory_quantity=10,
        )
        intent = extract_intent("I need a mechanical keyboard under 5000")
        result = find_matching_products(intent)
        result_pks = pks(result)
        # Both should appear (both have "keyboard") but mechanical should rank first
        self.assertIn(kb_mech.pk, result_pks)
        self.assertIn(kb_plain.pk, result_pks)
        mech_idx = result_pks.index(kb_mech.pk)
        plain_idx = result_pks.index(kb_plain.pk)
        self.assertLess(mech_idx, plain_idx,
                        "Mechanical keyboard should rank before plain keyboard")

    # ── R9: preferences affect ranking ───────────────────────────────────────

    def test_R9_preferences_boost_ranking(self):
        """Test R9: A product matching a preference keyword ranks higher."""
        merchant3 = make_merchant(
            business_name="Pref Test", email="pref@test.com"
        )
        kb_wireless = make_product(
            merchant3,
            name="Wireless Keyboard",
            description="Wireless mechanical keyboard with long battery.",
            category="Gaming",
            price=Decimal("4000.00"),
            cost_price=Decimal("2600.00"),
            inventory_quantity=10,
        )
        kb_wired = make_product(
            merchant3,
            name="Standard Keyboard",
            description="Standard wired keyboard.",
            category="Gaming",
            price=Decimal("4100.00"),   # slightly more expensive
            cost_price=Decimal("2700.00"),
            inventory_quantity=10,
        )
        # "wireless" appears in HARD features — so it goes into requirements
        # and gives +8 to the wireless keyboard's score
        intent = extract_intent("I need a wireless keyboard under 5000")
        result = find_matching_products(intent)
        result_pks = pks(result)
        self.assertIn(kb_wireless.pk, result_pks)
        self.assertIn(kb_wired.pk, result_pks)
        wireless_idx = result_pks.index(kb_wireless.pk)
        wired_idx = result_pks.index(kb_wired.pk)
        self.assertLess(wireless_idx, wired_idx,
                        "Wireless keyboard should rank before wired keyboard")

    # ── R10: no product type → broad results ─────────────────────────────────

    def test_R10_no_product_type_returns_broad_results(self):
        """Test R10: A vague query returns multiple in-stock active products."""
        intent = extract_intent("Show me something good for gaming")
        result = find_matching_products(intent)
        # Should return multiple products (at least keyboard, mouse, monitor)
        self.assertGreaterEqual(len(result), 2,
                                "Broad query should return multiple products")
        # No type exclusion — mouse, keyboard etc. can all appear
        result_pks = pks(result)
        self.assertIn(self.mouse.pk, result_pks)


# ===========================================================================
# STEP 6 TESTS — Revenue Opportunity Engine
# ===========================================================================

from ai.services.revenue_engine import (
    generate_opportunities,
    calculate_margin,
    calculate_opportunity_score,
    RevenueOpportunity,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers for Step 6
# ---------------------------------------------------------------------------

def make_policy(merchant, **kwargs):
    """Create a MerchantPolicy with sensible defaults."""
    defaults = {
        "minimum_margin_percent":    Decimal("18.00"),
        "maximum_discount_percent":  Decimal("10.00"),
        "maximum_negotiation_rounds": 3,
        "auto_approval_limit":       Decimal("25000.00"),
    }
    defaults.update(kwargs)
    return MerchantPolicy.objects.create(merchant=merchant, **defaults)


class Step6BaseTestCase(TestCase):
    """
    Base class that creates a standard NovaTech-like merchant, policy, and
    product catalogue for Step 6 tests.

    Products (active, in-stock unless overridden):
        keyboard   : Gaming, Rs.3999, cost Rs.2700
        mouse      : Gaming, Rs.1999, cost Rs.1200
        monitor    : Monitors, Rs.24999, cost Rs.19000
        headphones : Audio,   Rs.5499, cost Rs.3800
        laptop     : Laptops, Rs.64999, cost Rs.52000
    """

    def setUp(self):
        self.merchant = make_merchant(
            business_name="NovaTech Test",
            email="nova6test@store.com",
        )
        self.policy = make_policy(self.merchant)

        self.keyboard = make_product(
            self.merchant,
            name="Mechanical Gaming Keyboard",
            description="Tenkeyless mechanical keyboard with Cherry MX Red switches.",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            inventory_quantity=25,
        )
        self.mouse = make_product(
            self.merchant,
            name="Gaming Mouse",
            description="Lightweight ergonomic gaming mouse 25K DPI sensor.",
            category="Gaming",
            price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"),
            inventory_quantity=50,
        )
        self.monitor = make_product(
            self.merchant,
            name="27-inch Gaming Monitor",
            description="27-inch IPS gaming monitor 165Hz QHD display.",
            category="Monitors",
            price=Decimal("24999.00"),
            cost_price=Decimal("19000.00"),
            inventory_quantity=12,
        )
        self.headphones = make_product(
            self.merchant,
            name="Wireless ANC Headphones",
            description="Premium over-ear headphones active noise cancellation.",
            category="Audio",
            price=Decimal("5499.00"),
            cost_price=Decimal("3800.00"),
            inventory_quantity=42,
        )
        self.laptop = make_product(
            self.merchant,
            name="Performance Laptop",
            description="14-inch professional laptop Intel Core Ultra 9.",
            category="Laptops",
            price=Decimal("64999.00"),
            cost_price=Decimal("52000.00"),
            inventory_quantity=8,
        )


# ===========================================================================
# D: Discount tests
# ===========================================================================

class DiscountOpportunityTest(Step6BaseTestCase):
    """Tests D1-D5: DISCOUNT opportunity generation."""

    def _get_discounts(self, product, intent):
        opps = generate_opportunities(intent, [product], self.policy)
        return [o for o in opps if o.action == "DISCOUNT"]

    # D1 — Valid discount generated
    def test_D1_valid_discount_generated(self):
        """D1: At least one DISCOUNT opportunity is generated for an in-budget product."""
        intent = extract_intent("I need a gaming keyboard under 5000")
        discounts = self._get_discounts(self.keyboard, intent)
        self.assertTrue(
            len(discounts) > 0,
            "Expected at least one DISCOUNT opportunity for keyboard.",
        )

    # D2 — Maximum discount is never exceeded
    def test_D2_maximum_discount_respected(self):
        """D2: No discount candidate exceeds policy.maximum_discount_percent."""
        intent = extract_intent("I need a gaming keyboard under 5000")
        discounts = self._get_discounts(self.keyboard, intent)
        for opp in discounts:
            self.assertLessEqual(
                opp.discount_percent,
                self.policy.maximum_discount_percent,
                f"Discount {opp.discount_percent}% exceeds policy max "
                f"{self.policy.maximum_discount_percent}%.",
            )

    # D3 — Minimum margin is respected (compliant flag correct)
    def test_D3_minimum_margin_respected(self):
        """D3: Discounts that violate minimum_margin_percent are marked non-compliant."""
        # Policy floor = 18%. keyboard cost=2700, price=3999
        # At 8% discount: proposed=3679.08, margin=(3679.08-2700)/3679.08=26.6% -> compliant
        # We create a product where even 5% would violate margin
        thin_product = make_product(
            self.merchant,
            name="Thin Margin Widget",
            description="Low margin item.",
            category="Gaming",
            price=Decimal("2000.00"),
            cost_price=Decimal("1700.00"),  # margin = 15% (below policy floor)
            inventory_quantity=10,
        )
        # Even at 0% discount, the margin is 15% < 18% policy minimum
        # So any discount produces policy_compliant=False
        intent = extract_intent("I need something for gaming under 3000")
        discounts = self._get_discounts(thin_product, intent)
        for opp in discounts:
            self.assertFalse(
                opp.policy_compliant,
                f"Thin-margin product discount should be non-compliant "
                f"(margin={opp.resulting_margin_percent}%, "
                f"floor={self.policy.minimum_margin_percent}%)",
            )

    # D4 — Invalid discount is never recommended as compliant
    def test_D4_invalid_discount_not_compliant(self):
        """D4: Discount steps exceeding policy max are marked policy_compliant=False."""
        # Create a policy with very low max discount so we can trigger exceeds_policy
        strict_policy_merchant = make_merchant(
            business_name="Strict Corp", email="strict@corp.test"
        )
        strict_policy = make_policy(
            strict_policy_merchant,
            maximum_discount_percent=Decimal("1.00"),  # Only 1% allowed
            minimum_margin_percent=Decimal("5.00"),
        )
        product = make_product(
            strict_policy_merchant,
            name="Keyboard",
            description="A keyboard.",
            category="Gaming",
            price=Decimal("3000.00"),
            cost_price=Decimal("1000.00"),
            inventory_quantity=10,
        )
        intent = extract_intent("I need a keyboard under 5000")
        opps = generate_opportunities(intent, [product], strict_policy)
        discounts = [o for o in opps if o.action == "DISCOUNT"]
        for opp in discounts:
            if opp.discount_percent > strict_policy.maximum_discount_percent:
                self.assertFalse(
                    opp.policy_compliant,
                    f"Discount {opp.discount_percent}% over policy max "
                    f"must be non-compliant.",
                )

    # D5 — Decimal arithmetic is used (price_difference is exact Decimal)
    def test_D5_decimal_arithmetic_precision(self):
        """D5: All monetary values in DISCOUNT opportunities are Decimal instances."""
        intent = extract_intent("I need a gaming keyboard under 5000")
        discounts = self._get_discounts(self.keyboard, intent)
        self.assertTrue(len(discounts) > 0)
        for opp in discounts:
            self.assertIsInstance(opp.proposed_price,  Decimal)
            self.assertIsInstance(opp.discount_amount, Decimal)
            self.assertIsInstance(opp.resulting_margin_percent, Decimal)


# ===========================================================================
# N: No-action tests
# ===========================================================================

class NoActionOpportunityTest(Step6BaseTestCase):
    """Test N1: NO_ACTION baseline opportunity."""

    def test_N1_baseline_opportunity_generated(self):
        """N1: A NO_ACTION opportunity is generated for each matched product."""
        intent = extract_intent("I need a gaming keyboard under 5000")
        opps = generate_opportunities(intent, [self.keyboard], self.policy)
        no_actions = [o for o in opps if o.action == "NO_ACTION"]
        self.assertEqual(len(no_actions), 1, "Expected exactly one NO_ACTION per product.")
        opp = no_actions[0]
        self.assertEqual(opp.product_id, self.keyboard.pk)
        self.assertEqual(opp.proposed_price, opp.current_price)
        self.assertEqual(opp.discount_amount, Decimal("0.00"))
        self.assertEqual(opp.discount_percent, Decimal("0.00"))
        self.assertTrue(opp.policy_compliant)


# ===========================================================================
# U: Upsell tests
# ===========================================================================

class UpsellOpportunityTest(Step6BaseTestCase):
    """Tests U1-U4: UPSELL opportunity generation."""

    def setUp(self):
        super().setUp()
        # Add a premium keyboard (higher price, same category)
        self.premium_keyboard = make_product(
            self.merchant,
            name="Premium Mechanical Keyboard",
            description="High-end mechanical keyboard with OLED display.",
            category="Gaming",
            price=Decimal("6999.00"),
            cost_price=Decimal("4500.00"),
            inventory_quantity=10,
        )

    def _get_upsells(self, products, intent):
        opps = generate_opportunities(intent, products, self.policy)
        return [o for o in opps if o.action == "UPSELL"]

    # U1 — Relevant higher-priced product identified
    def test_U1_relevant_upsell_identified(self):
        """U1: A higher-priced same-category product appears as an UPSELL."""
        intent = extract_intent("I need a gaming keyboard under 8000")
        products = [self.keyboard, self.premium_keyboard]
        upsells = self._get_upsells(products, intent)
        self.assertTrue(
            len(upsells) > 0,
            "Expected UPSELL opportunities for keyboard -> premium keyboard.",
        )
        upsell_recommended_ids = [o.recommended_product_id for o in upsells]
        self.assertIn(self.premium_keyboard.pk, upsell_recommended_ids)

    # U2 — Unrelated product not treated as strong upsell
    def test_U2_unrelated_product_not_upsell(self):
        """U2: Products from different categories are not upsold against each other."""
        intent = extract_intent("I need a gaming keyboard")
        # keyboard (Gaming) vs headphones (Audio) — different category
        products = [self.keyboard, self.headphones]
        upsells = self._get_upsells(products, intent)
        for opp in upsells:
            # headphones should not be recommended as upsell for keyboard
            self.assertNotEqual(
                opp.recommended_product_id, self.headphones.pk,
                "Cross-category upsell (keyboard -> headphones) must not appear.",
            )

    # U3 — Out-of-stock upsell excluded
    def test_U3_out_of_stock_upsell_excluded(self):
        """U3: An out-of-stock product must not appear as an upsell candidate."""
        self.premium_keyboard.inventory_quantity = 0
        self.premium_keyboard.save()
        intent = extract_intent("I need a gaming keyboard under 8000")
        products = [self.keyboard, self.premium_keyboard]
        upsells = self._get_upsells(products, intent)
        for opp in upsells:
            self.assertNotEqual(
                opp.recommended_product_id, self.premium_keyboard.pk,
                "Out-of-stock product must not be an upsell target.",
            )

    # U4 — Inactive upsell excluded
    def test_U4_inactive_upsell_excluded(self):
        """U4: An inactive product must not appear as an upsell candidate."""
        self.premium_keyboard.is_active = False
        self.premium_keyboard.save()
        intent = extract_intent("I need a gaming keyboard under 8000")
        products = [self.keyboard, self.premium_keyboard]
        upsells = self._get_upsells(products, intent)
        for opp in upsells:
            self.assertNotEqual(
                opp.recommended_product_id, self.premium_keyboard.pk,
                "Inactive product must not be an upsell target.",
            )


# ===========================================================================
# B: Bundle tests
# ===========================================================================

class BundleOpportunityTest(Step6BaseTestCase):
    """Tests B1-B4: BUNDLE opportunity generation."""

    def _get_bundles(self, products, intent):
        opps = generate_opportunities(intent, products, self.policy)
        return [o for o in opps if o.action == "BUNDLE"]

    # B1 — Complementary products form a bundle
    def test_B1_complementary_products_bundle(self):
        """B1: keyboard + mouse (Gaming complementary pair) forms a bundle."""
        intent = extract_intent("I need gaming peripherals")
        products = [self.keyboard, self.mouse]
        bundles = self._get_bundles(products, intent)
        self.assertTrue(
            len(bundles) > 0,
            "Expected BUNDLE for gaming keyboard + mouse pair.",
        )

    # B2 — Unrelated products do not form strong bundles
    def test_B2_unrelated_products_no_bundle(self):
        """B2: Headphones (Audio) and Laptop (Laptops) do not form a bundle."""
        intent = extract_intent("I need audio and computing gear")
        products = [self.headphones, self.laptop]
        bundles = self._get_bundles(products, intent)
        self.assertEqual(
            len(bundles), 0,
            "Unrelated categories (Audio + Laptops) must not bundle.",
        )

    # B3 — Out-of-stock bundle item excluded
    def test_B3_out_of_stock_bundle_item_excluded(self):
        """B3: Bundle with an out-of-stock companion must not be generated."""
        self.mouse.inventory_quantity = 0
        self.mouse.save()
        intent = extract_intent("I need gaming peripherals")
        products = [self.keyboard, self.mouse]
        bundles = self._get_bundles(products, intent)
        for opp in bundles:
            self.assertNotEqual(
                opp.recommended_product_id, self.mouse.pk,
                "Out-of-stock product must not appear as bundle companion.",
            )

    # B4 — Bundle respects margin rules
    def test_B4_bundle_margin_respected(self):
        """B4: Bundle opportunity is marked non-compliant if combined margin falls below policy."""
        # Create a very tight-margin keyboard to force bundle margin below policy floor
        tight_keyboard = make_product(
            self.merchant,
            name="Budget Keyboard",
            description="Cheap keyboard.",
            category="Gaming",
            price=Decimal("500.00"),
            cost_price=Decimal("490.00"),  # 2% margin before bundle discount
            inventory_quantity=10,
        )
        tight_mouse = make_product(
            self.merchant,
            name="Budget Mouse",
            description="Cheap mouse.",
            category="Gaming",
            price=Decimal("500.00"),
            cost_price=Decimal("490.00"),
            inventory_quantity=10,
        )
        intent = extract_intent("I need cheap gaming gear")
        products = [tight_keyboard, tight_mouse]
        bundles = self._get_bundles(products, intent)
        for opp in bundles:
            # With only 2% product margin + 5% bundle discount, margin must violate policy
            if (opp.base_product_id == tight_keyboard.pk or
                    opp.base_product_id == tight_mouse.pk):
                self.assertFalse(
                    opp.policy_compliant,
                    "Tight-margin bundle must be marked non-compliant.",
                )


# ===========================================================================
# S: Scoring tests
# ===========================================================================

class ScoringTest(Step6BaseTestCase):
    """Tests S1-S4: Deterministic opportunity scoring."""

    # S1 — Relevant product scores higher than irrelevant
    def test_S1_relevant_product_scores_higher(self):
        """S1: Higher intent_relevance signal produces a higher opportunity_score."""
        score_high, _ = calculate_opportunity_score(
            intent_relevance=80,
            budget_fit=20,
            margin_preservation=25,
            inventory=10,
            action_factor=10,
            policy_compliant=True,
        )
        score_low, _ = calculate_opportunity_score(
            intent_relevance=10,
            budget_fit=20,
            margin_preservation=25,
            inventory=10,
            action_factor=10,
            policy_compliant=True,
        )
        self.assertGreater(
            score_high, score_low,
            "Higher intent_relevance should produce a higher opportunity_score.",
        )

    # S2 — Policy-compliant ranks above non-compliant
    def test_S2_compliant_ranks_above_noncompliant(self):
        """S2: policy_compliant=False subtracts 100 from score."""
        score_compliant, _ = calculate_opportunity_score(
            intent_relevance=50,
            budget_fit=20,
            margin_preservation=25,
            inventory=10,
            action_factor=15,
            policy_compliant=True,
        )
        score_noncompliant, _ = calculate_opportunity_score(
            intent_relevance=50,
            budget_fit=20,
            margin_preservation=25,
            inventory=10,
            action_factor=15,
            policy_compliant=False,
        )
        self.assertGreater(
            score_compliant, score_noncompliant,
            "Policy-compliant opportunity must rank above non-compliant.",
        )
        self.assertEqual(
            score_compliant - score_noncompliant, 100,
            "Non-compliant penalty must be exactly 100 points.",
        )

    # S3 — Better budget fit improves score
    def test_S3_better_budget_fit_improves_score(self):
        """S3: Higher budget_fit signal directly increases opportunity_score."""
        score_good_fit, _ = calculate_opportunity_score(
            intent_relevance=50,
            budget_fit=30,
            margin_preservation=25,
            inventory=10,
            action_factor=10,
            policy_compliant=True,
        )
        score_poor_fit, _ = calculate_opportunity_score(
            intent_relevance=50,
            budget_fit=0,
            margin_preservation=25,
            inventory=10,
            action_factor=10,
            policy_compliant=True,
        )
        self.assertGreater(
            score_good_fit, score_poor_fit,
            "Better budget fit must improve opportunity_score.",
        )

    # S4 — Signals are stored in metadata for explainability
    def test_S4_signals_stored_in_metadata(self):
        """S4: metadata['signals'] contains all scoring signal values."""
        intent = extract_intent("I need a gaming keyboard under 5000")
        opps = generate_opportunities(intent, [self.keyboard], self.policy)
        self.assertTrue(len(opps) > 0)
        for opp in opps:
            self.assertIn("signals", opp.metadata,
                          f"metadata must contain 'signals' for {opp.action}.")
            signals = opp.metadata["signals"]
            for key in ("intent_relevance", "budget_fit", "margin_preservation",
                        "inventory", "action_factor"):
                self.assertIn(key, signals,
                              f"signals must contain '{key}' for {opp.action}.")


# ===========================================================================
# A: API tests
# ===========================================================================

class OpportunityAPITest(TestCase):
    """Tests A1-A6: POST /api/ai/opportunities/ API contract."""

    def setUp(self):
        self.client = APIClient()
        self.merchant = make_merchant(
            business_name="NovaTech API Test",
            email="nova_api6@store.com",
        )
        self.policy = make_policy(self.merchant)
        self.keyboard = make_product(
            self.merchant,
            name="Mechanical Gaming Keyboard",
            description="Tenkeyless mechanical keyboard.",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            inventory_quantity=25,
        )
        self.mouse = make_product(
            self.merchant,
            name="Gaming Mouse",
            description="Lightweight ergonomic gaming mouse.",
            category="Gaming",
            price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"),
            inventory_quantity=50,
        )

    # A1 — Valid opportunity request
    def test_A1_valid_opportunity_request(self):
        """A1: Valid POST with merchant_id returns 200 and opportunities list."""
        resp = self.client.post(
            "/api/ai/opportunities/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("intent", data)
        self.assertIn("opportunities", data)
        self.assertIn("merchant_id", data)
        self.assertIsInstance(data["opportunities"], list)

    # A2 — Invalid/empty message returns 400
    def test_A2_empty_message_rejected(self):
        """A2: Empty message returns HTTP 400."""
        resp = self.client.post(
            "/api/ai/opportunities/",
            {"message": "", "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_A2b_missing_message_rejected(self):
        """A2b: Missing message field returns HTTP 400."""
        resp = self.client.post(
            "/api/ai/opportunities/",
            {"merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # A3 — Merchant ID handling — unknown merchant returns 404
    def test_A3_unknown_merchant_id_returns_404(self):
        """A3: A non-existent merchant_id returns HTTP 404."""
        resp = self.client.post(
            "/api/ai/opportunities/",
            {"message": "I need a keyboard", "merchant_id": 999999},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # A4 — Opportunity response structure
    def test_A4_opportunity_response_structure(self):
        """A4: Each opportunity has the required fields."""
        resp = self.client.post(
            "/api/ai/opportunities/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        opps = resp.json()["opportunities"]
        required_fields = {
            "action", "product_id", "product_name", "base_product_id",
            "current_price", "proposed_price", "discount_amount",
            "discount_percent", "resulting_margin_percent",
            "opportunity_score", "policy_compliant", "reason", "metadata",
        }
        for opp in opps:
            for field in required_fields:
                self.assertIn(field, opp,
                              f"Opportunity missing field '{field}'.")

    # A5 — resulting_margin_percent is present (merchant-side acceptable)
    def test_A5_margin_info_present_in_opportunity_response(self):
        """A5: resulting_margin_percent appears in the opportunities response."""
        resp = self.client.post(
            "/api/ai/opportunities/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        opps = resp.json()["opportunities"]
        self.assertTrue(len(opps) > 0)
        for opp in opps:
            self.assertIn("resulting_margin_percent", opp)

    # A6 — cost_price must NEVER appear in any response field
    def test_A6_cost_price_never_exposed(self):
        """A6: cost_price must not appear in either /intent/ or /opportunities/ responses."""
        import json

        # Check /api/ai/intent/
        resp_intent = self.client.post(
            "/api/ai/intent/",
            {"message": "I need a gaming keyboard under 5000"},
            format="json",
        )
        self.assertEqual(resp_intent.status_code, status.HTTP_200_OK)
        intent_text = json.dumps(resp_intent.json())
        self.assertNotIn(
            "cost_price", intent_text,
            "cost_price must never appear in /api/ai/intent/ response.",
        )

        # Check /api/ai/opportunities/
        resp_opp = self.client.post(
            "/api/ai/opportunities/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp_opp.status_code, status.HTTP_200_OK)
        opp_text = json.dumps(resp_opp.json())
        self.assertNotIn(
            "cost_price", opp_text,
            "cost_price must never appear in /api/ai/opportunities/ response.",
        )


# ===========================================================================
# Margin calculation unit test
# ===========================================================================

class MarginCalculationTest(TestCase):
    """Unit tests for calculate_margin helper."""

    def test_margin_correct(self):
        """calculate_margin((5000, 3800)) should be 24.00%."""
        result = calculate_margin(Decimal("5000"), Decimal("3800"))
        self.assertEqual(result, Decimal("24.00"))

    def test_margin_zero_selling_price_raises(self):
        """calculate_margin raises ZeroDivisionError when selling_price == 0."""
        with self.assertRaises(ZeroDivisionError):
            calculate_margin(Decimal("0"), Decimal("100"))

    def test_margin_is_decimal(self):
        """calculate_margin always returns a Decimal."""
        result = calculate_margin(Decimal("3999"), Decimal("2700"))
        self.assertIsInstance(result, Decimal)


# ===========================================================================
# STEP 7 TESTS — Autonomous Revenue Decision Engine
# ===========================================================================

from ai.services.decision_engine import (
    make_decision,
    DecisionResult,
    ValidationResult,
    _validate_opportunity,
    _calculate_confidence,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers for Step 7 (re-use Step 6 helpers)
# ---------------------------------------------------------------------------

class Step7BaseTestCase(TestCase):
    """
    Base test case for Decision Engine tests.

    Creates a fresh merchant, policy, and catalogue for each test:
        keyboard   : Gaming, Rs.3999, cost Rs.2700
        mouse      : Gaming, Rs.1999, cost Rs.1200
        monitor    : Monitors, Rs.24999, cost Rs.19000
        headphones : Audio,   Rs.5499, cost Rs.3800
        laptop     : Laptops, Rs.64999, cost Rs.52000
    """

    def setUp(self):
        self.merchant = make_merchant(
            business_name="Decision Test Store",
            email="decision_test@store.com",
        )
        self.policy = make_policy(self.merchant)

        self.keyboard = make_product(
            self.merchant,
            name="Mechanical Gaming Keyboard",
            description="Tenkeyless mechanical keyboard with Cherry MX Red switches.",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            inventory_quantity=25,
        )
        self.mouse = make_product(
            self.merchant,
            name="Gaming Mouse",
            description="Lightweight ergonomic gaming mouse 25K DPI.",
            category="Gaming",
            price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"),
            inventory_quantity=50,
        )
        self.monitor = make_product(
            self.merchant,
            name="27-inch Gaming Monitor",
            description="27-inch IPS gaming monitor 165Hz QHD.",
            category="Monitors",
            price=Decimal("24999.00"),
            cost_price=Decimal("19000.00"),
            inventory_quantity=12,
        )
        self.headphones = make_product(
            self.merchant,
            name="Wireless ANC Headphones",
            description="Premium over-ear headphones ANC.",
            category="Audio",
            price=Decimal("5499.00"),
            cost_price=Decimal("3800.00"),
            inventory_quantity=42,
        )
        self.laptop = make_product(
            self.merchant,
            name="Performance Laptop",
            description="14-inch professional laptop Intel Core Ultra 9.",
            category="Laptops",
            price=Decimal("64999.00"),
            cost_price=Decimal("52000.00"),
            inventory_quantity=8,
        )

    def _opportunities_for(self, message):
        from ai.services.revenue_engine import generate_opportunities
        intent = extract_intent(message)
        products = find_matching_products(intent, merchant=self.merchant)
        return intent, products, generate_opportunities(intent, products, self.policy)

    def _decision_for(self, message):
        intent, products, opps = self._opportunities_for(message)
        return intent, make_decision(intent, opps, self.policy)


# ===========================================================================
# A: Highest valid opportunity selected
# ===========================================================================

class DecisionSelectionTest(Step7BaseTestCase):

    def test_A_highest_valid_opportunity_selected(self):
        """A: The decision engine selects the highest-scoring valid opportunity."""
        intent, decision = self._decision_for("I need a gaming keyboard under 5000")
        self.assertIsNotNone(decision.selected_opportunity)
        # Selected must be policy compliant
        self.assertTrue(decision.selected_opportunity.policy_compliant)
        # Its score must be >= all alternatives
        for alt in decision.alternatives:
            self.assertGreaterEqual(
                decision.decision_score, alt.opportunity_score,
                "Selected score must be >= all alternatives.",
            )


# ===========================================================================
# B: Non-compliant opportunity rejected
# ===========================================================================

class NonCompliantRejectionTest(Step7BaseTestCase):

    def test_B_non_compliant_opportunity_rejected(self):
        """B: Non-compliant opportunities are rejected, not selected."""
        intent, decision = self._decision_for("I need a gaming keyboard under 5000")
        # None of the rejected opportunities should have been selected
        if decision.selected_opportunity:
            self.assertTrue(decision.selected_opportunity.policy_compliant)
        # All rejected ones must have a reason
        for rej in decision.rejected_opportunities:
            self.assertIn("reason", rej)
            self.assertTrue(len(rej["reason"]) > 0)


# ===========================================================================
# C: Discount above maximum rejected
# ===========================================================================

class DiscountCeilingRejectionTest(TestCase):

    def test_C_discount_above_max_rejected(self):
        """C: A discount opportunity exceeding maximum_discount_percent is rejected."""
        merchant = make_merchant(business_name="Strict Disc", email="strictdisc@test.com")
        policy = make_policy(
            merchant,
            maximum_discount_percent=Decimal("3.00"),
            minimum_margin_percent=Decimal("5.00"),
        )
        product = make_product(
            merchant,
            name="Gadget",
            description="A gadget.",
            category="Gaming",
            price=Decimal("2000.00"),
            cost_price=Decimal("500.00"),
            inventory_quantity=10,
        )
        from ai.services.revenue_engine import generate_opportunities, RevenueOpportunity
        from dataclasses import replace

        intent = extract_intent("I need a gadget")
        opps = generate_opportunities(intent, [product], policy)

        # Inject an artificially over-limit discount opportunity
        fake_over = RevenueOpportunity(
            action="DISCOUNT",
            product_id=product.pk,
            product_name=product.name,
            base_product_id=product.pk,
            recommended_product_id=None,
            recommended_product_name=None,
            current_price=Decimal("2000.00"),
            proposed_price=Decimal("1800.00"),
            price_difference=Decimal("-200.00"),
            discount_amount=Decimal("200.00"),
            discount_percent=Decimal("10.00"),   # > policy max of 3%
            resulting_margin_percent=Decimal("72.22"),
            opportunity_score=999,
            policy_compliant=True,   # engine marked compliant (test override)
            reason="Injected over-limit discount",
            metadata={"signals": {
                "intent_relevance": 50, "budget_fit": 20,
                "margin_preservation": 25, "inventory": 10, "action_factor": 15,
            }},
        )
        decision = make_decision(intent, [fake_over] + opps, policy)
        # The injected over-limit discount must be in rejected, not selected
        rejected_actions = [r["opportunity"].discount_percent for r in decision.rejected_opportunities
                            if r["opportunity"].action == "DISCOUNT"]
        self.assertIn(Decimal("10.00"), rejected_actions)
        if decision.selected_opportunity:
            self.assertNotEqual(decision.selected_opportunity.discount_percent, Decimal("10.00"))


# ===========================================================================
# D: Margin below minimum rejected
# ===========================================================================

class MarginFloorRejectionTest(TestCase):

    def test_D_margin_below_minimum_rejected(self):
        """D: An opportunity with margin below minimum_margin_percent is rejected."""
        merchant = make_merchant(business_name="Margin Test", email="margintest@test.com")
        policy = make_policy(merchant, minimum_margin_percent=Decimal("30.00"))
        product = make_product(
            merchant,
            name="Low Margin Item",
            description="Low margin.",
            category="Gaming",
            price=Decimal("1000.00"),
            cost_price=Decimal("800.00"),  # margin = 20%
            inventory_quantity=10,
        )
        from ai.services.revenue_engine import RevenueOpportunity

        # Create a fake opportunity with 15% margin < 30% policy min
        low_margin_opp = RevenueOpportunity(
            action="DISCOUNT",
            product_id=product.pk,
            product_name=product.name,
            base_product_id=product.pk,
            recommended_product_id=None,
            recommended_product_name=None,
            current_price=Decimal("1000.00"),
            proposed_price=Decimal("900.00"),
            price_difference=Decimal("-100.00"),
            discount_amount=Decimal("100.00"),
            discount_percent=Decimal("10.00"),
            resulting_margin_percent=Decimal("11.11"),  # below 30% floor
            opportunity_score=500,
            policy_compliant=True,   # override to test decision engine re-check
            reason="Injected below-margin discount",
            metadata={"signals": {
                "intent_relevance": 50, "budget_fit": 20,
                "margin_preservation": -50, "inventory": 10, "action_factor": 15,
            }},
        )
        intent = extract_intent("I need a gaming item")
        decision = make_decision(intent, [low_margin_opp], policy)
        rejected_reasons = [r["reason"] for r in decision.rejected_opportunities]
        # Must be rejected with a margin floor reason
        self.assertTrue(
            any("margin" in r.lower() for r in rejected_reasons),
            "Below-minimum-margin opportunity must be rejected with a margin reason.",
        )


# ===========================================================================
# E: Inactive product rejected
# ===========================================================================

class InactiveProductRejectionTest(Step7BaseTestCase):

    def test_E_inactive_product_excluded_from_selection(self):
        """E: Opportunities for inactive products are never selected."""
        self.keyboard.is_active = False
        self.keyboard.save()
        intent, decision = self._decision_for("I need a gaming keyboard under 5000")
        if decision.selected_opportunity:
            self.assertNotEqual(
                decision.selected_opportunity.product_id,
                self.keyboard.pk,
                "Inactive product must not be the selected opportunity.",
            )


# ===========================================================================
# F: Out-of-stock product rejected
# ===========================================================================

class OutOfStockRejectionTest(Step7BaseTestCase):

    def test_F_out_of_stock_product_not_selected(self):
        """F: Opportunities from out-of-stock products are not selected."""
        self.keyboard.inventory_quantity = 0
        self.keyboard.save()
        intent, decision = self._decision_for("I need a gaming keyboard under 5000")
        if decision.selected_opportunity:
            self.assertNotEqual(
                decision.selected_opportunity.product_id,
                self.keyboard.pk,
                "Out-of-stock product must not be selected.",
            )


# ===========================================================================
# G: Auto-approval limit behavior
# ===========================================================================

class AutoApprovalTest(Step7BaseTestCase):

    def test_G1_within_auto_approval_limit_not_flagged(self):
        """G1: A decision within auto_approval_limit has requires_approval=False."""
        # policy.auto_approval_limit=25000; keyboard price=3999 < 25000
        intent, decision = self._decision_for("I need a gaming keyboard under 5000")
        if decision.selected_opportunity:
            if decision.selected_opportunity.proposed_price <= self.policy.auto_approval_limit:
                self.assertFalse(
                    decision.requires_approval,
                    "Transaction within auto_approval_limit must not require approval.",
                )

    def test_G2_exceeds_auto_approval_limit_flagged(self):
        """G2: A decision exceeding auto_approval_limit has requires_approval=True."""
        # Laptop Rs.64999 > policy.auto_approval_limit=25000
        # Create a laptop-budget query that would select laptop
        high_limit_merchant = make_merchant(
            business_name="BigTicket", email="bigticket@test.com"
        )
        high_limit_policy = make_policy(
            high_limit_merchant,
            auto_approval_limit=Decimal("20000.00"),  # below laptop price
            minimum_margin_percent=Decimal("10.00"),
            maximum_discount_percent=Decimal("10.00"),
        )
        expensive_product = make_product(
            high_limit_merchant,
            name="Big Laptop",
            description="Expensive professional laptop.",
            category="Laptops",
            price=Decimal("64999.00"),
            cost_price=Decimal("50000.00"),
            inventory_quantity=5,
        )
        from ai.services.revenue_engine import generate_opportunities

        intent = extract_intent("I need a laptop under 70000")
        products = find_matching_products(intent, merchant=high_limit_merchant)
        opps = generate_opportunities(intent, products, high_limit_policy)
        decision = make_decision(intent, opps, high_limit_policy)

        if decision.selected_opportunity and \
                decision.selected_opportunity.proposed_price > high_limit_policy.auto_approval_limit:
            self.assertTrue(
                decision.requires_approval,
                "Transaction exceeding auto_approval_limit must require approval.",
            )


# ===========================================================================
# H: NO_ACTION selection
# ===========================================================================

class NoActionSelectionTest(TestCase):

    def test_H_no_action_is_valid_selection(self):
        """H: NO_ACTION is a legitimate decision outcome."""
        merchant = make_merchant(business_name="NoAct", email="noact@test.com")
        policy = make_policy(merchant)
        product = make_product(
            merchant,
            name="Perfect Priced Gadget",
            description="Gadget at a fair price.",
            category="Gaming",
            price=Decimal("2000.00"),
            cost_price=Decimal("1200.00"),
            inventory_quantity=10,
        )
        from ai.services.revenue_engine import generate_opportunities, RevenueOpportunity

        intent = extract_intent("I need a gaming gadget")
        # Build only a NO_ACTION opportunity
        no_action_opp = RevenueOpportunity(
            action="NO_ACTION",
            product_id=product.pk,
            product_name=product.name,
            base_product_id=product.pk,
            recommended_product_id=None,
            recommended_product_name=None,
            current_price=Decimal("2000.00"),
            proposed_price=Decimal("2000.00"),
            price_difference=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            discount_percent=Decimal("0.00"),
            resulting_margin_percent=Decimal("40.00"),
            opportunity_score=80,
            policy_compliant=True,
            reason="Sell at catalog price.",
            metadata={"signals": {
                "intent_relevance": 40, "budget_fit": 20,
                "margin_preservation": 25, "inventory": 10, "action_factor": 10,
            }},
        )
        decision = make_decision(intent, [no_action_opp], policy)
        self.assertEqual(decision.selected_action, "NO_ACTION")
        self.assertIsNotNone(decision.selected_opportunity)


# ===========================================================================
# I: Deterministic tie-breaking
# ===========================================================================

class TieBreakingTest(TestCase):

    def test_I_deterministic_tie_breaking_by_score(self):
        """I: When two opportunities have equal scores, tie-breaking is deterministic."""
        merchant = make_merchant(business_name="Tie", email="tie@test.com")
        policy = make_policy(merchant)
        from ai.services.revenue_engine import RevenueOpportunity

        def make_opp(action, product_id, score, price):
            return RevenueOpportunity(
                action=action,
                product_id=product_id,
                product_name=f"Product {product_id}",
                base_product_id=product_id,
                recommended_product_id=None,
                recommended_product_name=None,
                current_price=price,
                proposed_price=price,
                price_difference=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                discount_percent=Decimal("0.00"),
                resulting_margin_percent=Decimal("30.00"),
                opportunity_score=score,
                policy_compliant=True,
                reason="Test opp",
                metadata={"signals": {
                    "intent_relevance": 30, "budget_fit": 10,
                    "margin_preservation": 25, "inventory": 10, "action_factor": 10,
                }},
            )

        opp_a = make_opp("NO_ACTION", 1, 100, Decimal("3000.00"))
        opp_b = make_opp("NO_ACTION", 2, 100, Decimal("3000.00"))

        intent = extract_intent("I need something")
        # Run twice — result must be identical
        result1 = make_decision(intent, [opp_a, opp_b], policy)
        result2 = make_decision(intent, [opp_a, opp_b], policy)
        self.assertEqual(
            result1.selected_opportunity.product_id,
            result2.selected_opportunity.product_id,
            "Tie-breaking must be deterministic across identical runs.",
        )


# ===========================================================================
# J: Alternatives returned correctly
# ===========================================================================

class AlternativesTest(Step7BaseTestCase):

    def test_J_alternatives_populated(self):
        """J: alternatives list contains valid opportunities after the selected one."""
        intent, decision = self._decision_for("I need a gaming keyboard under 5000")
        # Should have at least 1 alternative (NO_ACTION + DISCOUNTs)
        self.assertIsInstance(decision.alternatives, list)
        # All alternatives must also be policy-compliant
        for alt in decision.alternatives:
            self.assertTrue(
                alt.policy_compliant,
                "Alternatives must be policy-compliant valid opportunities.",
            )
        # Alternatives must score <= selected
        for alt in decision.alternatives:
            self.assertLessEqual(
                alt.opportunity_score,
                decision.decision_score,
                "Alternatives must have a score <= selected opportunity score.",
            )


# ===========================================================================
# K: Rejected opportunities include reasons
# ===========================================================================

class RejectedWithReasonsTest(TestCase):

    def test_K_rejected_opportunities_include_reasons(self):
        """K: Every rejected opportunity has a non-empty reason."""
        merchant = make_merchant(business_name="Reject Test", email="rejecttest@test.com")
        policy = make_policy(merchant)
        product = make_product(
            merchant,
            name="Widget",
            description="A widget.",
            category="Gaming",
            price=Decimal("1000.00"),
            cost_price=Decimal("500.00"),
            inventory_quantity=10,
        )
        from ai.services.revenue_engine import RevenueOpportunity

        # Create a non-compliant opportunity
        bad_opp = RevenueOpportunity(
            action="DISCOUNT",
            product_id=product.pk,
            product_name=product.name,
            base_product_id=product.pk,
            recommended_product_id=None,
            recommended_product_name=None,
            current_price=Decimal("1000.00"),
            proposed_price=Decimal("850.00"),
            price_difference=Decimal("-150.00"),
            discount_amount=Decimal("150.00"),
            discount_percent=Decimal("15.00"),  # exceeds policy max=10%
            resulting_margin_percent=Decimal("41.18"),
            opportunity_score=50,
            policy_compliant=False,
            reason="Exceeds max discount",
            metadata={"signals": {
                "intent_relevance": 30, "budget_fit": 10,
                "margin_preservation": 25, "inventory": 10, "action_factor": 15,
            }},
        )
        intent = extract_intent("I need a widget")
        decision = make_decision(intent, [bad_opp], policy)
        self.assertTrue(
            len(decision.rejected_opportunities) > 0,
            "Expected at least one rejected opportunity.",
        )
        for rej in decision.rejected_opportunities:
            self.assertIn("reason", rej, "Rejected entry must have 'reason' key.")
            self.assertTrue(len(rej["reason"]) > 0, "Rejection reason must not be empty.")


# ===========================================================================
# L: Decision trace structure
# ===========================================================================

class DecisionTraceTest(Step7BaseTestCase):

    def test_L_decision_trace_structure(self):
        """L: decision_trace contains all required top-level keys."""
        intent, decision = self._decision_for("I need a gaming keyboard under 5000")
        trace = decision.decision_trace
        # Top-level structure
        self.assertIn("input", trace)
        self.assertIn("pipeline_summary", trace)
        self.assertIn("candidate_evaluations", trace)
        # Input fields
        for key in ("intent_type", "search_query", "budget_max"):
            self.assertIn(key, trace["input"])
        # Pipeline summary fields
        summary = trace["pipeline_summary"]
        for key in ("candidates_considered", "candidates_validated",
                    "candidates_rejected", "selected_action",
                    "requires_approval", "confidence"):
            self.assertIn(key, summary)
        # candidate_evaluations is a list
        self.assertIsInstance(trace["candidate_evaluations"], list)
        # Each evaluation has decision field
        for eval_entry in trace["candidate_evaluations"]:
            self.assertIn("decision", eval_entry)
            self.assertIn(eval_entry["decision"], ("selected", "alternative", "rejected"))


# ===========================================================================
# M: Confidence calculation
# ===========================================================================

class ConfidenceTest(TestCase):

    def test_M1_large_gap_high_confidence(self):
        """M1: A large score gap yields high confidence."""
        confidence = _calculate_confidence(200, [])
        self.assertGreaterEqual(confidence, 0.5)

    def test_M2_no_alternatives_yields_valid_confidence(self):
        """M2: When there are no alternatives, confidence is still between 0 and 1."""
        confidence = _calculate_confidence(80, [])
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_M3_confidence_is_float(self):
        """M3: _calculate_confidence returns a float."""
        from ai.services.revenue_engine import RevenueOpportunity
        alt = RevenueOpportunity(
            action="NO_ACTION", product_id=1, product_name="P",
            base_product_id=1, recommended_product_id=None,
            recommended_product_name=None,
            current_price=Decimal("100.00"), proposed_price=Decimal("100.00"),
            price_difference=Decimal("0.00"), discount_amount=Decimal("0.00"),
            discount_percent=Decimal("0.00"), resulting_margin_percent=Decimal("30.00"),
            opportunity_score=50, policy_compliant=True, reason="",
            metadata={"signals": {}},
        )
        confidence = _calculate_confidence(100, [alt])
        self.assertIsInstance(confidence, float)

    def test_M4_confidence_bounded(self):
        """M4: Confidence is always in [0.0, 1.0]."""
        for selected_score in [0, 50, 100, 200, -10]:
            c = _calculate_confidence(max(0, selected_score), [])
            self.assertGreaterEqual(c, 0.0)
            self.assertLessEqual(c, 1.0)


# ===========================================================================
# N: API endpoint tests
# ===========================================================================

class DecisionAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.merchant = make_merchant(
            business_name="Decision API Store",
            email="decapi@store.com",
        )
        self.policy = make_policy(self.merchant)
        self.keyboard = make_product(
            self.merchant,
            name="Mechanical Gaming Keyboard",
            description="Tenkeyless mechanical keyboard.",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            inventory_quantity=25,
        )
        self.mouse = make_product(
            self.merchant,
            name="Gaming Mouse",
            description="Lightweight gaming mouse.",
            category="Gaming",
            price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"),
            inventory_quantity=50,
        )

    def test_N1_valid_decision_request(self):
        """N1: Valid POST returns 200 with required top-level keys."""
        resp = self.client.post(
            "/api/ai/decision/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("intent", data)
        self.assertIn("merchant_id", data)
        self.assertIn("selected_decision", data)
        sd = data["selected_decision"]
        for key in ("selected_action", "decision_score", "confidence",
                    "reason", "requires_approval", "alternatives",
                    "rejected_opportunities", "decision_trace"):
            self.assertIn(key, sd, f"selected_decision missing key '{key}'.")

    def test_N2_empty_message_returns_400(self):
        """N2: Empty message returns HTTP 400."""
        resp = self.client.post(
            "/api/ai/decision/",
            {"message": "", "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_N3_unknown_merchant_returns_404(self):
        """N3: Non-existent merchant_id returns HTTP 404."""
        resp = self.client.post(
            "/api/ai/decision/",
            {"message": "I need a keyboard", "merchant_id": 999999},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_N4_decision_trace_in_response(self):
        """N4: decision_trace is present and contains pipeline_summary."""
        resp = self.client.post(
            "/api/ai/decision/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        trace = resp.json()["selected_decision"]["decision_trace"]
        self.assertIn("pipeline_summary", trace)
        self.assertIn("candidate_evaluations", trace)

    def test_N5_cost_price_never_in_response(self):
        """N5: cost_price must never appear in /api/ai/decision/ response."""
        import json
        resp = self.client.post(
            "/api/ai/decision/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        raw = json.dumps(resp.json())
        self.assertNotIn(
            "cost_price", raw,
            "cost_price must never appear in /api/ai/decision/ response.",
        )

    def test_N6_alternatives_are_list(self):
        """N6: alternatives field is a list of opportunity objects."""
        resp = self.client.post(
            "/api/ai/decision/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        alternatives = resp.json()["selected_decision"]["alternatives"]
        self.assertIsInstance(alternatives, list)

    def test_N7_requires_approval_field_present(self):
        """N7: requires_approval is a boolean in the response."""
        resp = self.client.post(
            "/api/ai/decision/",
            {"message": "I need a gaming keyboard under 5000",
             "merchant_id": self.merchant.pk},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sd = resp.json()["selected_decision"]
        self.assertIn("requires_approval", sd)
        self.assertIsInstance(sd["requires_approval"], bool)


# ===========================================================================
# O: Validation unit tests
# ===========================================================================

class ValidationPipelineTest(TestCase):
    """Unit tests for _validate_opportunity validation stages."""

    def _make_compliant_opp(self, **kwargs):
        """Build a compliant RevenueOpportunity with sensible defaults."""
        from ai.services.revenue_engine import RevenueOpportunity
        defaults = dict(
            action="NO_ACTION",
            product_id=1,
            product_name="Test Product",
            base_product_id=1,
            recommended_product_id=None,
            recommended_product_name=None,
            current_price=Decimal("1000.00"),
            proposed_price=Decimal("1000.00"),
            price_difference=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            discount_percent=Decimal("0.00"),
            resulting_margin_percent=Decimal("30.00"),
            opportunity_score=80,
            policy_compliant=True,
            reason="OK",
            metadata={"signals": {
                "intent_relevance": 30, "budget_fit": 10,
                "margin_preservation": 25, "inventory": 10, "action_factor": 10,
            }},
        )
        defaults.update(kwargs)
        return RevenueOpportunity(**defaults)

    def _make_policy(self):
        merchant = make_merchant(
            business_name="ValTest", email="valtest@store.com"
        )
        return make_policy(merchant), merchant

    def test_O1_compliant_passes_all_stages(self):
        """O1: A fully valid opportunity passes all validation stages."""
        policy, _ = self._make_policy()
        opp = self._make_compliant_opp()
        result = _validate_opportunity(opp, policy)
        self.assertTrue(result.valid)

    def test_O2_non_compliant_flag_rejected_at_stage1(self):
        """O2: policy_compliant=False is caught at stage 1."""
        policy, _ = self._make_policy()
        opp = self._make_compliant_opp(policy_compliant=False)
        result = _validate_opportunity(opp, policy)
        self.assertFalse(result.valid)
        self.assertEqual(result.stage, "policy_compliant")

    def test_O3_zero_proposed_price_rejected(self):
        """O3: proposed_price <= 0 is rejected at safety stage."""
        policy, _ = self._make_policy()
        opp = self._make_compliant_opp(proposed_price=Decimal("0.00"))
        result = _validate_opportunity(opp, policy)
        self.assertFalse(result.valid)
        self.assertEqual(result.stage, "safety")

    def test_O4_excess_discount_rejected(self):
        """O4: discount_percent > maximum_discount_percent is rejected."""
        policy, _ = self._make_policy()  # max_discount = 10%
        opp = self._make_compliant_opp(discount_percent=Decimal("15.00"))
        result = _validate_opportunity(opp, policy)
        self.assertFalse(result.valid)
        self.assertEqual(result.stage, "discount_ceiling")

    def test_O5_below_margin_rejected(self):
        """O5: resulting_margin_percent < minimum_margin_percent is rejected."""
        policy, _ = self._make_policy()  # min_margin = 18%
        opp = self._make_compliant_opp(resulting_margin_percent=Decimal("10.00"))
        result = _validate_opportunity(opp, policy)
        self.assertFalse(result.valid)
        self.assertEqual(result.stage, "margin_floor")

    def test_O6_no_valid_action_result(self):
        """O6: make_decision returns NO_VALID_ACTION when all candidates are invalid."""
        policy, merchant = self._make_policy()
        opp = self._make_compliant_opp(policy_compliant=False)
        intent = extract_intent("I need something")
        decision = make_decision(intent, [opp], policy)
        self.assertEqual(decision.selected_action, "NO_VALID_ACTION")
        self.assertIsNone(decision.selected_opportunity)
        self.assertEqual(decision.confidence, 0.0)


# ===========================================================================
# STEP 8 TESTS — Bounded Autonomous Commerce Agent
# ===========================================================================

from ai.models import CommerceConversation, CommerceEvent
from ai.services.commerce_agent import CommerceAgent, InvalidStateTransitionError
from ai.services.negotiation_engine import (
    NegotiationEngine,
    extract_buyer_proposed_price,
    classify_buyer_message
)


class Step8BaseTestCase(TestCase):
    """
    Base test case for Step 8 Autonomous Commerce Agent tests.
    Sets up merchant, policy (max_discount=10%, min_margin=18%, max_rounds=3),
    and catalog products.
    """

    def setUp(self):
        self.merchant = make_merchant(
            business_name="Agent Test Store",
            email="agent_test@store.com"
        )
        self.policy = make_policy(self.merchant)  # max_disc=10, min_margin=18, max_rounds=3

        self.keyboard = make_product(
            self.merchant,
            name="Mechanical Gaming Keyboard",
            description="Tenkeyless mechanical keyboard RGB.",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            inventory_quantity=25,
        )
        self.mouse = make_product(
            self.merchant,
            name="Gaming Mouse",
            description="Ergonomic gaming mouse 25K DPI.",
            category="Gaming",
            price=Decimal("1999.00"),
            cost_price=Decimal("1200.00"),
            inventory_quantity=50,
        )


class Step8AgentServiceTests(Step8BaseTestCase):

    def test_A_create_conversation(self):
        """A: Creates persistent conversation with initial ACTIVE status."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id, buyer_session_id="session_123")
        self.assertEqual(conv.status, CommerceConversation.STATUS_ACTIVE)
        self.assertEqual(conv.merchant, self.merchant)
        self.assertEqual(conv.buyer_session_id, "session_123")
        self.assertEqual(conv.events.count(), 1)
        self.assertEqual(conv.events.first().event_type, CommerceEvent.EVENT_SYSTEM_EVENT)

    def test_B_initial_buyer_message_and_C_recommendation(self):
        """B & C: Initial message yields product recommendation and sets status to OFFERED."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        res = CommerceAgent.process_message(conv, "I want a gaming keyboard under 4500")

        conv.refresh_from_db()
        self.assertEqual(conv.status, CommerceConversation.STATUS_OFFERED)
        self.assertEqual(conv.current_product, self.keyboard)
        self.assertEqual(res['status'], CommerceConversation.STATUS_OFFERED)
        self.assertEqual(res['product']['id'], self.keyboard.id)
        self.assertEqual(res['offered_price'], str(conv.current_price))

    def test_D_buyer_offer_extraction(self):
        """D: Deterministic buyer offer price extraction from natural language."""
        self.assertEqual(extract_buyer_proposed_price("Can you do ₹3500?"), Decimal("3500"))
        self.assertEqual(extract_buyer_proposed_price("Rs. 3500 deal"), Decimal("3500"))
        self.assertEqual(extract_buyer_proposed_price("my budget is 3600"), Decimal("3600"))
        self.assertEqual(extract_buyer_proposed_price("I'll pay 3700"), Decimal("3700"))
        self.assertIsNone(extract_buyer_proposed_price("I want 2 keyboards"))

    def test_E_valid_buyer_offer_accepted(self):
        """E: Buyer offer meeting merchant policy is accepted directly."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")

        # Keyboard price 3999, cost 2700. Offer 3799 (5% disc, 28.9% margin >= 18%)
        res = CommerceAgent.process_message(conv, "Can you do 3799?")

        conv.refresh_from_db()
        self.assertEqual(conv.status, CommerceConversation.STATUS_ACCEPTED)
        self.assertEqual(res['status'], CommerceConversation.STATUS_ACCEPTED)
        self.assertTrue(res['payment_ready'])
        self.assertEqual(conv.agreed_price, Decimal("3799.00"))

    def test_F_invalid_buyer_offer_countered(self):
        """F & G: Invalid buyer offer yields valid counteroffer within policy bounds."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")

        # Offer 3000 -> Max discount 10% (min price 3599.10), cost 2700 (min price at 18% margin is 3292.68).
        # Counter should be around 3599.10.
        res = CommerceAgent.process_message(conv, "Can you do 3000?")

        conv.refresh_from_db()
        self.assertEqual(conv.status, CommerceConversation.STATUS_COUNTER_OFFERED)
        self.assertEqual(res['action'], "COUNTER_OFFER")
        self.assertIsNotNone(res['offered_price'])

        counter_price = Decimal(res['offered_price'])
        self.assertGreater(counter_price, Decimal("3000"))
        self.assertLessEqual(counter_price, Decimal("3999"))

    def test_H_counter_offer_max_discount_and_I_min_margin(self):
        """H & I: Counteroffer strictly respects maximum discount and minimum margin."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")
        res = CommerceAgent.process_message(conv, "Can you do 2500?")

        counter_price = Decimal(res['offered_price'])
        catalog_price = Decimal("3999.00")
        cost_price = Decimal("2700.00")

        discount_pct = ((catalog_price - counter_price) / catalog_price) * Decimal("100")
        margin_pct = ((counter_price - cost_price) / counter_price) * Decimal("100")

        self.assertLessEqual(discount_pct, Decimal("10.00"))
        self.assertGreaterEqual(margin_pct, Decimal("18.00"))

    def test_J_negotiation_round_increment_and_K_max_rounds(self):
        """J & K: Negotiation rounds increment and max rounds (3) enforces rejection on excess rounds."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")  # Round 0

        # Round 1
        res1 = CommerceAgent.process_message(conv, "Can you do 3000?")
        self.assertEqual(res1['negotiation_round'], 1)

        # Round 2
        res2 = CommerceAgent.process_message(conv, "How about 3100?")
        self.assertEqual(res2['negotiation_round'], 2)

        # Round 3
        res3 = CommerceAgent.process_message(conv, "Can you do 3200?")
        self.assertEqual(res3['negotiation_round'], 3)

        # Round 4 -> Exceeds max_rounds=3 -> Rejection
        res4 = CommerceAgent.process_message(conv, "3300?")
        conv.refresh_from_db()
        self.assertEqual(conv.status, CommerceConversation.STATUS_REJECTED)
        self.assertEqual(res4['status'], CommerceConversation.STATUS_REJECTED)

    def test_L_buyer_acceptance(self):
        """L: Buyer saying 'okay' accepts the current offer."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")

        res = CommerceAgent.process_message(conv, "Okay, deal")
        conv.refresh_from_db()
        self.assertEqual(conv.status, CommerceConversation.STATUS_ACCEPTED)
        self.assertEqual(conv.agreed_price, conv.current_price)
        self.assertTrue(res['payment_ready'])

    def test_M_buyer_rejection(self):
        """M: Buyer saying 'no, too expensive' rejects the negotiation."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")

        res = CommerceAgent.process_message(conv, "No, too expensive")
        conv.refresh_from_db()
        self.assertEqual(conv.status, CommerceConversation.STATUS_REJECTED)
        self.assertEqual(res['status'], CommerceConversation.STATUS_REJECTED)
        self.assertFalse(res['payment_ready'])

    def test_N_requirement_change_causes_reevaluation(self):
        """N: Buyer changing requirements switches current product and re-evaluates."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")
        self.assertEqual(conv.current_product, self.keyboard)

        # Requirement change -> mouse
        res = CommerceAgent.process_message(conv, "Show me a gaming mouse instead")
        conv.refresh_from_db()
        self.assertEqual(conv.current_product, self.mouse)
        self.assertEqual(res['product']['id'], self.mouse.id)

    def test_O_invalid_state_transition_rejected(self):
        """O: Attempting invalid transition directly or via process_message fails safely."""
        with self.assertRaises(InvalidStateTransitionError):
            CommerceAgent.validate_transition(
                CommerceConversation.STATUS_ACCEPTED,
                CommerceConversation.STATUS_OFFERED
            )

    def test_P_accepted_conversation_cannot_negotiate_again(self):
        """P: Sending messages to ACCEPTED conversation returns terminal state response."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")
        CommerceAgent.process_message(conv, "Okay")

        conv.refresh_from_db()
        self.assertEqual(conv.status, CommerceConversation.STATUS_ACCEPTED)

        # Send new message
        res = CommerceAgent.process_message(conv, "Can you give it for 3000?")
        self.assertEqual(res['status'], CommerceConversation.STATUS_ACCEPTED)
        self.assertEqual(res['action'], "TERMINAL_STATE")
        self.assertTrue(res['payment_ready'])

    def test_Q_rejected_conversation_cannot_negotiate_again(self):
        """Q: Sending messages to REJECTED conversation returns terminal state response."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")
        CommerceAgent.process_message(conv, "No, too expensive")

        conv.refresh_from_db()
        self.assertEqual(conv.status, CommerceConversation.STATUS_REJECTED)

        res = CommerceAgent.process_message(conv, "What about 3500?")
        self.assertEqual(res['status'], CommerceConversation.STATUS_REJECTED)
        self.assertEqual(res['action'], "TERMINAL_STATE")
        self.assertFalse(res['payment_ready'])

    def test_R_event_history_preserved(self):
        """R: Conversation maintains complete append-only audit event trail."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")
        CommerceAgent.process_message(conv, "Can you do 3500?")
        CommerceAgent.process_message(conv, "Okay")

        events = conv.events.all()
        # System event + (Buyer msg + Agent offer) * 3
        self.assertGreaterEqual(events.count(), 5)
        event_types = [e.event_type for e in events]
        self.assertIn(CommerceEvent.EVENT_SYSTEM_EVENT, event_types)
        self.assertIn(CommerceEvent.EVENT_BUYER_MESSAGE, event_types)
        self.assertIn(CommerceEvent.EVENT_COUNTER_OFFER, event_types)

    def test_S_decision_trace_preserved(self):
        """S: Process message responses attach structured decision_trace."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        res = CommerceAgent.process_message(conv, "I want a gaming keyboard")
        self.assertIn("decision_trace", res)
        self.assertIn("agent_step", res["decision_trace"])

    def test_T_cost_price_never_appears_in_api_response(self):
        """T: Cost price is strictly omitted from serializers and responses."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        res = CommerceAgent.process_message(conv, "I want a gaming keyboard")
        res_str = str(res)
        self.assertNotIn("cost_price", res_str)
        self.assertNotIn("2700", res_str)

    def test_U_payment_not_executed(self):
        """U: Commercial agreement sets payment_ready=True without calling external payment gateways."""
        conv = CommerceAgent.create_conversation(merchant_id=self.merchant.id)
        CommerceAgent.process_message(conv, "I want a gaming keyboard")
        res = CommerceAgent.process_message(conv, "Okay")
        self.assertTrue(res['payment_ready'])
        self.assertNotIn("order_id", res)
        self.assertNotIn("razorpay", res)


class Step8AgentAPITests(Step8BaseTestCase):

    def setUp(self):
        super().setUp()
        from rest_framework.test import APIClient
        self.client = APIClient()

    def test_V_api_create_conversation(self):
        """V: POST /api/ai/agent/conversations/ creates a new session."""
        url = "/api/ai/agent/conversations/"
        resp = self.client.post(url, {"merchant_id": self.merchant.id, "buyer_session_id": "api_session_1"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("conversation_id", resp.data)
        self.assertEqual(resp.data["status"], "ACTIVE")

    def test_W_api_send_message(self):
        """W: POST /api/ai/agent/conversations/<id>/messages/ processes buyer input."""
        # Create conv
        c_url = "/api/ai/agent/conversations/"
        c_resp = self.client.post(c_url, {"merchant_id": self.merchant.id}, format="json")
        cid = c_resp.data["conversation_id"]

        # Send msg
        m_url = f"/api/ai/agent/conversations/{cid}/messages/"
        m_resp = self.client.post(m_url, {"message": "I want a gaming keyboard"}, format="json")
        self.assertEqual(m_resp.status_code, 200)
        self.assertEqual(m_resp.data["status"], "OFFERED")
        self.assertIn("agent_response", m_resp.data)

    def test_X_api_retrieve_conversation(self):
        """X: GET /api/ai/agent/conversations/<id>/ retrieves full state and events."""
        c_url = "/api/ai/agent/conversations/"
        c_resp = self.client.post(c_url, {"merchant_id": self.merchant.id}, format="json")
        cid = c_resp.data["conversation_id"]

        d_url = f"/api/ai/agent/conversations/{cid}/"
        d_resp = self.client.get(d_url)
        self.assertEqual(d_resp.status_code, 200)
        self.assertEqual(d_resp.data["id"], cid)
        self.assertIn("events", d_resp.data)
        self.assertNotIn("cost_price", str(d_resp.data))

    def test_Y_repeated_message_idempotency_behavior(self):
        """Y: Processing duplicate identical messages does not corrupt state machine."""
        c_url = "/api/ai/agent/conversations/"
        c_resp = self.client.post(c_url, {"merchant_id": self.merchant.id}, format="json")
        cid = c_resp.data["conversation_id"]

        m_url = f"/api/ai/agent/conversations/{cid}/messages/"
        m1 = self.client.post(m_url, {"message": "I want a gaming keyboard"}, format="json")
        m2 = self.client.post(m_url, {"message": "I want a gaming keyboard"}, format="json")

        self.assertEqual(m1.data["status"], "OFFERED")
        self.assertEqual(m2.data["status"], "OFFERED")


# ===========================================================================
# STEP 9 TESTS — Autonomous AI Buyer Agent
# ===========================================================================

from django.core.exceptions import ValidationError
from ai.models import (
    BuyerAgentProfile,
    BuyerNegotiationSession,
    BuyerNegotiationEvent
)
from ai.services.buyer_agent import BuyerAgent, InvalidBuyerStateTransitionError
from ai.services.buyer_decision_engine import (
    BuyerDecisionEngine,
    calculate_buyer_counter_offer,
    validate_product_requirements
)


class Step9BaseTestCase(TestCase):
    def setUp(self):
        self.merchant = make_merchant(
            business_name="Buyer Test Merchant",
            email="buyer_test@store.com"
        )
        self.keyboard = make_product(
            self.merchant,
            name="Mechanical Gaming Keyboard",
            description="RGB Mechanical Gaming Keyboard with tactile switches.",
            category="Gaming",
            price=Decimal("6200.00"),
            cost_price=Decimal("4000.00"),
            inventory_quantity=20,
        )
        self.mouse = make_product(
            self.merchant,
            name="Office Mouse",
            description="Basic silent office mouse.",
            category="Office",
            price=Decimal("1500.00"),
            cost_price=Decimal("800.00"),
            inventory_quantity=30,
        )

    def _make_profile(self, **kwargs):
        defaults = {
            "buyer_session_id": "buyer-test-session",
            "name": "Test AI Buyer",
            "requirements": ["gaming keyboard", "mechanical"],
            "budget_min": Decimal("3000.00"),
            "budget_max": Decimal("7000.00"),
            "preferred_price": Decimal("5500.00"),
            "maximum_price": Decimal("6500.00"),
            "walk_away_price": Decimal("6500.00"),
            "preferences": ["RGB"],
            "negotiation_enabled": True,
            "maximum_negotiation_rounds": 3,
            "strategy": BuyerAgentProfile.STRATEGY_BALANCED,
        }
        defaults.update(kwargs)
        return BuyerAgent.create_profile(**defaults)


class Step9BuyerAgentTests(Step9BaseTestCase):

    def test_A_buyer_profile_creation(self):
        """A: Creates BuyerAgentProfile with explicit parameters."""
        profile = self._make_profile()
        self.assertEqual(profile.name, "Test AI Buyer")
        self.assertEqual(profile.preferred_price, Decimal("5500.00"))
        self.assertEqual(profile.strategy, BuyerAgentProfile.STRATEGY_BALANCED)

    def test_B_validation_of_budget_fields(self):
        """B: Profile clean() validates price hierarchy (min <= pref <= max <= walk_away)."""
        with self.assertRaises(ValidationError):
            profile = BuyerAgentProfile(
                buyer_session_id="invalid-b",
                budget_min=Decimal("5000"),
                budget_max=Decimal("7000"),
                preferred_price=Decimal("6800"),
                maximum_price=Decimal("6000"),  # Invalid: pref > max
                walk_away_price=Decimal("6500"),
            )
            profile.full_clean()

    def test_C_buyer_session_creation(self):
        """C: Creates persistent BuyerNegotiationSession with initial ACTIVE status."""
        profile = self._make_profile()
        session = BuyerAgent.create_session(profile.id, self.merchant.id)
        self.assertEqual(session.status, BuyerNegotiationSession.STATUS_ACTIVE)
        self.assertEqual(session.buyer_profile, profile)
        self.assertEqual(session.merchant, self.merchant)

    def test_D_merchant_offer_evaluation_and_E_attractive_offer_accepted(self):
        """D & E: Merchant offer <= preferred price is accepted directly."""
        profile = self._make_profile()
        session = BuyerAgent.create_session(profile.id, self.merchant.id)

        res = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("5400.00"))
        session.refresh_from_db()

        self.assertEqual(session.status, BuyerNegotiationSession.STATUS_ACCEPTED)
        self.assertEqual(res['decision'], "ACCEPT")
        self.assertEqual(res['agreed_price'], "5400.00")
        self.assertTrue(res['payment_ready'])

    def test_F_moderate_offer_countered(self):
        """F: Merchant offer above preferred price triggers counteroffer."""
        profile = self._make_profile()
        session = BuyerAgent.create_session(profile.id, self.merchant.id)

        res = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6200.00"))
        session.refresh_from_db()

        self.assertEqual(session.status, BuyerNegotiationSession.STATUS_COUNTER_OFFERED)
        self.assertEqual(res['decision'], "COUNTER")
        self.assertIsNotNone(res['buyer_counter_offer'])

        counter = Decimal(res['buyer_counter_offer'])
        self.assertGreaterEqual(counter, profile.preferred_price)
        self.assertLess(counter, Decimal("6200.00"))

    def test_G_and_H_offer_above_walk_away_rejected(self):
        """G & H: Merchant offer > walk_away_price is immediately rejected."""
        profile = self._make_profile(walk_away_price=Decimal("6500.00"))
        session = BuyerAgent.create_session(profile.id, self.merchant.id)

        res = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6700.00"))
        session.refresh_from_db()

        self.assertEqual(session.status, BuyerNegotiationSession.STATUS_REJECTED)
        self.assertEqual(res['decision'], "REJECT")
        # Internal reason preserved
        self.assertIn("exceeds walk-away price", res['reason'])
        # Customer-facing message is empathetic and excludes internal terms
        self.assertIn("best and final price", res['customer_message'])
        self.assertIn("6,700.00", res['customer_message'])
        self.assertNotIn("walk-away", res['customer_message'].lower())
        self.assertNotIn("walk_away", res['customer_message'].lower())

    def test_customer_facing_rejection_wording_in_autonomous_negotiation(self):
        """Verify that autonomous negotiation rejection creates empathetic buyer-facing messages."""
        from ai.models import AgentNegotiation, AgentNegotiationEvent
        from ai.services.agent_negotiation import AgentNegotiationOrchestrator
        from merchants.models import MerchantPolicy

        MerchantPolicy.objects.get_or_create(
            merchant=self.merchant,
            defaults={
                'minimum_margin_percent': Decimal('18.00'),
                'maximum_discount_percent': Decimal('10.00'),
                'maximum_negotiation_rounds': 3,
                'auto_approval_limit': Decimal('25000.00'),
            }
        )

        # Create buyer with walk_away lower than merchant's best offer
        profile = self._make_profile(
            walk_away_price=Decimal("3200.00"),
            preferred_price=Decimal("3000.00"),
            maximum_price=Decimal("3200.00"),
        )
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
            product_id=self.keyboard.id
        )
        AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=10)
        neg.refresh_from_db()

        self.assertEqual(neg.status, AgentNegotiation.STATUS_REJECTED)
        reject_event = AgentNegotiationEvent.objects.filter(
            negotiation=neg,
            event_type=AgentNegotiationEvent.EVENT_BUYER_REJECT
        ).first()
        self.assertIsNotNone(reject_event)
        # Verify customer-facing wording matches preferred format
        self.assertIn("is our best and final price", reject_event.message)
        self.assertIn("We've already applied the maximum discount we can offer", reject_event.message)
        self.assertNotIn("walk-away", reject_event.message.lower())
        self.assertNotIn("walk_away", reject_event.message.lower())
        self.assertNotIn("margin", reject_event.message.lower())
        # Internal reason preserved in metadata
        self.assertIn("internal_reason", reject_event.metadata)
        self.assertIn("walk-away price", reject_event.metadata["internal_reason"])


    def test_I_hard_product_requirement_mismatch(self):
        """I: Product violating buyer hard requirement is rejected."""
        profile = self._make_profile(requirements=["gaming keyboard", "mechanical"])
        session = BuyerAgent.create_session(profile.id, self.merchant.id)

        # Mouse is an office product, not a gaming keyboard
        res = BuyerAgent.evaluate_merchant_offer(session, self.mouse, Decimal("1000.00"))
        session.refresh_from_db()

        self.assertEqual(session.status, BuyerNegotiationSession.STATUS_REJECTED)
        self.assertEqual(res['decision'], "REJECT")
        self.assertIn("does not meet hard requirement", res['reason'])

    def test_J_soft_preference_scoring(self):
        """J: Preference match signal increments when product contains preference keywords."""
        profile = self._make_profile(preferences=["RGB"])
        signals = BuyerDecisionEngine.evaluate_offer(self.keyboard, Decimal("5000.00"), profile, 0)['signals']
        self.assertEqual(signals['preference_match'], 100)

    def test_K_and_L_counter_offer_bounds(self):
        """K & L: Counteroffer calculation never exceeds maximum_price."""
        profile = self._make_profile(preferred_price=Decimal("5500.00"), maximum_price=Decimal("6500.00"))
        counter = calculate_buyer_counter_offer(Decimal("6400.00"), profile, 0)
        self.assertLessEqual(counter, profile.maximum_price)
        self.assertGreaterEqual(counter, profile.preferred_price)

    def test_M_and_N_negotiation_round_increment_and_max_rounds(self):
        """M & N: Negotiation round increments and max rounds (3) enforces final decision."""
        profile = self._make_profile(strategy=BuyerAgentProfile.STRATEGY_VALUE_SEEKER, maximum_negotiation_rounds=3)
        session = BuyerAgent.create_session(profile.id, self.merchant.id)

        res1 = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6400.00"))  # Round 1 counter
        self.assertEqual(res1['negotiation_round'], 1)

        res2 = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6300.00"))  # Round 2 counter
        self.assertEqual(res2['negotiation_round'], 2)

        res3 = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6200.00"))  # Round 3 counter
        self.assertEqual(res3['negotiation_round'], 3)

        res4 = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6100.00"))  # Max rounds reached -> ACCEPT
        session.refresh_from_db()
        self.assertEqual(session.status, BuyerNegotiationSession.STATUS_ACCEPTED)

    def test_O_VALUE_SEEKER_behavior(self):
        """O: VALUE_SEEKER mode aggressively counters to seek lowest price."""
        profile = self._make_profile(strategy=BuyerAgentProfile.STRATEGY_VALUE_SEEKER)
        session = BuyerAgent.create_session(profile.id, self.merchant.id)
        res = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6000.00"))
        self.assertEqual(res['decision'], "COUNTER")

    def test_P_BALANCED_behavior(self):
        """P: BALANCED mode counters if offer is above midpoint of preferred & maximum."""
        profile = self._make_profile(strategy=BuyerAgentProfile.STRATEGY_BALANCED, preferred_price=Decimal("5000"), maximum_price=Decimal("6000"))
        session = BuyerAgent.create_session(profile.id, self.merchant.id)
        res = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("5800.00"))
        self.assertEqual(res['decision'], "COUNTER")

    def test_Q_FAST_BUYER_behavior(self):
        """Q: FAST_BUYER mode accepts offers <= maximum_price immediately."""
        profile = self._make_profile(strategy=BuyerAgentProfile.STRATEGY_FAST_BUYER, maximum_price=Decimal("6500.00"))
        session = BuyerAgent.create_session(profile.id, self.merchant.id)
        res = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6400.00"))
        self.assertEqual(res['decision'], "ACCEPT")

    def test_R_decision_trace(self):
        """R: Evaluated offer returns machine-readable decision_trace."""
        profile = self._make_profile()
        session = BuyerAgent.create_session(profile.id, self.merchant.id)
        res = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6000.00"))
        self.assertIn("decision_trace", res)
        self.assertEqual(res["decision_trace"]["agent"], "AI_BUYER")

    def test_S_deterministic_repeated_decision(self):
        """S: Running evaluation twice with identical input yields identical outputs."""
        profile = self._make_profile()
        eval1 = BuyerDecisionEngine.evaluate_offer(self.keyboard, Decimal("6200.00"), profile, 0)
        eval2 = BuyerDecisionEngine.evaluate_offer(self.keyboard, Decimal("6200.00"), profile, 0)
        self.assertEqual(eval1["decision"], eval2["decision"])
        self.assertEqual(eval1["counter_offer"], eval2["counter_offer"])

    def test_T_event_history(self):
        """T: Session maintains append-only BuyerNegotiationEvent log."""
        profile = self._make_profile()
        session = BuyerAgent.create_session(profile.id, self.merchant.id)
        BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6200.00"))
        self.assertGreaterEqual(session.events.count(), 2)

    def test_U_and_V_acceptance_and_rejection_states(self):
        """U & V: Verified ACCEPTED and REJECTED terminal state transitions."""
        profile = self._make_profile()
        session1 = BuyerAgent.create_session(profile.id, self.merchant.id)
        BuyerAgent.evaluate_merchant_offer(session1, self.keyboard, Decimal("5000.00"))
        self.assertEqual(session1.status, BuyerNegotiationSession.STATUS_ACCEPTED)

        session2 = BuyerAgent.create_session(profile.id, self.merchant.id)
        BuyerAgent.evaluate_merchant_offer(session2, self.keyboard, Decimal("7500.00"))
        self.assertEqual(session2.status, BuyerNegotiationSession.STATUS_REJECTED)

    def test_W_and_X_payment_ready_boundary_and_no_razorpay(self):
        """W & X: ACCEPTED sets payment_ready=True without Razorpay / payment calls."""
        profile = self._make_profile()
        session = BuyerAgent.create_session(profile.id, self.merchant.id)
        res = BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("5000.00"))
        self.assertTrue(res['payment_ready'])
        self.assertNotIn("razorpay", str(res))

    def test_Y_api_profile_creation(self):
        """Y: POST /api/ai/buyer/profiles/ creates buyer profile."""
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.post("/api/ai/buyer/profiles/", {
            "buyer_session_id": "api-buyer-1",
            "name": "API Buyer",
            "requirements": ["keyboard"],
            "budget_min": "1000.00",
            "budget_max": "7000.00",
            "preferred_price": "5000.00",
            "maximum_price": "6000.00",
            "walk_away_price": "6000.00",
            "preferences": ["RGB"],
            "negotiation_enabled": True,
            "maximum_negotiation_rounds": 3,
            "strategy": "BALANCED"
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.data)

    def test_Z_api_session_creation(self):
        """Z: POST /api/ai/buyer/sessions/ creates negotiation session."""
        from rest_framework.test import APIClient
        client = APIClient()
        profile = self._make_profile()
        resp = client.post("/api/ai/buyer/sessions/", {
            "buyer_profile_id": str(profile.id),
            "merchant_id": self.merchant.id
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("session_id", resp.data)

    def test_AA_api_offer_evaluation(self):
        """AA: POST /api/ai/buyer/sessions/<id>/offers/ evaluates merchant offer."""
        from rest_framework.test import APIClient
        client = APIClient()
        profile = self._make_profile()
        session = BuyerAgent.create_session(profile.id, self.merchant.id)

        resp = client.post(f"/api/ai/buyer/sessions/{session.id}/offers/", {
            "product_id": self.keyboard.id,
            "merchant_offer": "6200.00"
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["decision"], "COUNTER")

    def test_AB_api_session_history(self):
        """AB: GET /api/ai/buyer/sessions/<id>/ retrieves session detail & event history."""
        from rest_framework.test import APIClient
        client = APIClient()
        profile = self._make_profile()
        session = BuyerAgent.create_session(profile.id, self.merchant.id)
        BuyerAgent.evaluate_merchant_offer(session, self.keyboard, Decimal("6200.00"))

        resp = client.get(f"/api/ai/buyer/sessions/{session.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], str(session.id))
        self.assertIn("events", resp.data)
        self.assertNotIn("cost_price", str(resp.data))


# ===========================================================================
# STEP 10 TESTS — Autonomous AI-to-AI Commerce Negotiation
# ===========================================================================

from ai.models import AgentNegotiation, AgentNegotiationEvent
from ai.services.agent_negotiation import (
    AgentNegotiationOrchestrator,
    InvalidNegotiationStateTransitionError,
)


class Step10BaseTestCase(TestCase):
    """Shared fixtures for all Step 10 tests."""

    def setUp(self):
        self.merchant = Merchant.objects.create(
            business_name="Step10 Store",
            email="step10@store.test",
        )
        self.policy = MerchantPolicy.objects.create(
            merchant=self.merchant,
            minimum_margin_percent=Decimal("20.00"),
            maximum_discount_percent=Decimal("15.00"),
            maximum_negotiation_rounds=3,
            auto_approval_limit=Decimal("25000.00"),
        )
        # Product priced at 6000, cost 3000
        self.keyboard = Product.objects.create(
            merchant=self.merchant,
            name="Mechanical Keyboard",
            category="Gaming",
            description="RGB mechanical keyboard gaming peripherals",
            price=Decimal("6000.00"),
            cost_price=Decimal("3000.00"),
            inventory_quantity=20,
            is_active=True,
        )

    def _make_buyer_profile(self, **kwargs):
        defaults = dict(
            buyer_session_id="step10-buyer-1",
            name="Step10 AI Buyer",
            requirements=["keyboard"],
            budget_min=Decimal("3000.00"),
            budget_max=Decimal("7000.00"),
            preferred_price=Decimal("5000.00"),
            maximum_price=Decimal("6500.00"),
            walk_away_price=Decimal("6500.00"),
            preferences=["RGB"],
            negotiation_enabled=True,
            maximum_negotiation_rounds=3,
            strategy=BuyerAgentProfile.STRATEGY_BALANCED,
        )
        defaults.update(kwargs)
        return BuyerAgentProfile.objects.create(**defaults)

    def _make_buyer_profile_fast(self, **kwargs):
        """Buyer whose preferred_price >= catalog price -> accepts on first offer."""
        defaults = dict(
            buyer_session_id="step10-fast-buyer",
            name="Fast Buyer",
            requirements=["keyboard"],
            budget_min=Decimal("3000.00"),
            budget_max=Decimal("8000.00"),
            preferred_price=Decimal("7000.00"),
            maximum_price=Decimal("8000.00"),
            walk_away_price=Decimal("8000.00"),
            preferences=[],
            negotiation_enabled=True,
            maximum_negotiation_rounds=3,
            strategy=BuyerAgentProfile.STRATEGY_FAST_BUYER,
        )
        defaults.update(kwargs)
        return BuyerAgentProfile.objects.create(**defaults)

    def _make_buyer_profile_walk_away(self, **kwargs):
        """Buyer with walk-away below catalog price -> will reject."""
        defaults = dict(
            buyer_session_id="step10-walkaway-buyer",
            name="Walk-away Buyer",
            requirements=["keyboard"],
            budget_min=Decimal("1000.00"),
            budget_max=Decimal("3500.00"),
            preferred_price=Decimal("3000.00"),
            maximum_price=Decimal("3500.00"),
            walk_away_price=Decimal("3500.00"),
            preferences=[],
            negotiation_enabled=True,
            maximum_negotiation_rounds=3,
            strategy=BuyerAgentProfile.STRATEGY_VALUE_SEEKER,
        )
        defaults.update(kwargs)
        return BuyerAgentProfile.objects.create(**defaults)


class Step10ModelTests(Step10BaseTestCase):

    def test_10_01_agent_negotiation_model_creation(self):
        """10-01: AgentNegotiation model creates with correct defaults."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiation.objects.create(
            buyer_profile=profile,
            merchant=self.merchant,
            product=self.keyboard,
            status=AgentNegotiation.STATUS_ACTIVE,
            max_rounds=3,
            current_price=self.keyboard.price,
        )
        self.assertEqual(neg.status, AgentNegotiation.STATUS_ACTIVE)
        self.assertEqual(neg.negotiation_round, 0)
        self.assertFalse(neg.payment_ready)
        self.assertIsNone(neg.agreed_price)
        self.assertIsNone(neg.buyer_last_offer)
        self.assertIsNone(neg.merchant_last_offer)

    def test_10_02_agent_negotiation_event_model_creation(self):
        """10-02: AgentNegotiationEvent model creates and links to negotiation."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiation.objects.create(
            buyer_profile=profile,
            merchant=self.merchant,
            product=self.keyboard,
            status=AgentNegotiation.STATUS_ACTIVE,
            max_rounds=3,
        )
        evt = AgentNegotiationEvent.objects.create(
            negotiation=neg,
            round_number=0,
            actor=AgentNegotiationEvent.ACTOR_SYSTEM,
            event_type=AgentNegotiationEvent.EVENT_NEGOTIATION_STARTED,
            message="Test event",
        )
        self.assertEqual(evt.negotiation, neg)
        self.assertEqual(evt.actor, "SYSTEM")
        self.assertEqual(neg.events.count(), 1)

    def test_10_03_terminal_states_defined(self):
        """10-03: Terminal states are AGREED, REJECTED, EXPIRED and disjoint from active."""
        terminal = {
            AgentNegotiation.STATUS_AGREED,
            AgentNegotiation.STATUS_REJECTED,
            AgentNegotiation.STATUS_EXPIRED,
        }
        active = {
            AgentNegotiation.STATUS_ACTIVE,
            AgentNegotiation.STATUS_BUYER_TURN,
            AgentNegotiation.STATUS_MERCHANT_TURN,
        }
        self.assertEqual(len(terminal), 3)
        self.assertEqual(len(active), 3)
        self.assertTrue(terminal.isdisjoint(active))

    def test_10_04_negotiation_str_representation(self):
        """10-04: __str__ of AgentNegotiation includes status and round number."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiation.objects.create(
            buyer_profile=profile,
            merchant=self.merchant,
            status=AgentNegotiation.STATUS_ACTIVE,
            max_rounds=3,
        )
        self.assertIn("ACTIVE", str(neg))
        self.assertIn("0", str(neg))


class Step10StateMachineTests(Step10BaseTestCase):

    def test_10_05_valid_transition_active_to_buyer_turn(self):
        """10-05: State machine allows ACTIVE -> BUYER_TURN."""
        AgentNegotiationOrchestrator.validate_transition(
            AgentNegotiation.STATUS_ACTIVE,
            AgentNegotiation.STATUS_BUYER_TURN
        )

    def test_10_06_valid_transition_buyer_turn_to_merchant_turn(self):
        """10-06: State machine allows BUYER_TURN -> MERCHANT_TURN."""
        AgentNegotiationOrchestrator.validate_transition(
            AgentNegotiation.STATUS_BUYER_TURN,
            AgentNegotiation.STATUS_MERCHANT_TURN
        )

    def test_10_07_valid_transition_merchant_turn_to_agreed(self):
        """10-07: State machine allows MERCHANT_TURN -> AGREED."""
        AgentNegotiationOrchestrator.validate_transition(
            AgentNegotiation.STATUS_MERCHANT_TURN,
            AgentNegotiation.STATUS_AGREED
        )

    def test_10_08_invalid_transition_agreed_to_active(self):
        """10-08: State machine raises on AGREED -> ACTIVE (terminal -> active)."""
        with self.assertRaises(InvalidNegotiationStateTransitionError):
            AgentNegotiationOrchestrator.validate_transition(
                AgentNegotiation.STATUS_AGREED,
                AgentNegotiation.STATUS_ACTIVE
            )

    def test_10_09_invalid_transition_rejected_to_buyer_turn(self):
        """10-09: State machine raises on REJECTED -> BUYER_TURN."""
        with self.assertRaises(InvalidNegotiationStateTransitionError):
            AgentNegotiationOrchestrator.validate_transition(
                AgentNegotiation.STATUS_REJECTED,
                AgentNegotiation.STATUS_BUYER_TURN
            )

    def test_10_10_invalid_transition_expired_to_merchant_turn(self):
        """10-10: State machine raises on EXPIRED -> MERCHANT_TURN."""
        with self.assertRaises(InvalidNegotiationStateTransitionError):
            AgentNegotiationOrchestrator.validate_transition(
                AgentNegotiation.STATUS_EXPIRED,
                AgentNegotiation.STATUS_MERCHANT_TURN
            )

    def test_10_11_same_state_transition_is_allowed(self):
        """10-11: Transitioning to same state is a no-op (no exception)."""
        AgentNegotiationOrchestrator.validate_transition(
            AgentNegotiation.STATUS_ACTIVE,
            AgentNegotiation.STATUS_ACTIVE
        )


class Step10OrchestratorCreateTests(Step10BaseTestCase):

    def test_10_12_create_negotiation_success(self):
        """10-12: create_negotiation() returns ACTIVE negotiation with product matched."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        self.assertEqual(neg.status, AgentNegotiation.STATUS_ACTIVE)
        self.assertIsNotNone(neg.product)
        self.assertEqual(neg.buyer_profile, profile)
        self.assertEqual(neg.merchant, self.merchant)

    def test_10_13_create_negotiation_logs_started_and_product_selected_events(self):
        """10-13: create_negotiation() logs NEGOTIATION_STARTED and PRODUCT_SELECTED events."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        event_types = list(neg.events.values_list("event_type", flat=True))
        self.assertIn(AgentNegotiationEvent.EVENT_NEGOTIATION_STARTED, event_types)
        self.assertIn(AgentNegotiationEvent.EVENT_PRODUCT_SELECTED, event_types)

    def test_10_14_create_negotiation_no_matching_product_gives_rejected(self):
        """10-14: create_negotiation() with unmatched requirements -> REJECTED with NO_MATCHING_PRODUCT."""
        profile = BuyerAgentProfile.objects.create(
            buyer_session_id="no-match-buyer",
            name="No Match Buyer",
            requirements=["spaceship engine"],
            budget_min=Decimal("100.00"),
            budget_max=Decimal("200.00"),
            preferred_price=Decimal("150.00"),
            maximum_price=Decimal("200.00"),
            walk_away_price=Decimal("200.00"),
            negotiation_enabled=True,
            maximum_negotiation_rounds=3,
            strategy=BuyerAgentProfile.STRATEGY_BALANCED,
        )
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        self.assertEqual(neg.status, AgentNegotiation.STATUS_REJECTED)
        self.assertEqual(neg.termination_reason, "NO_MATCHING_PRODUCT")

    def test_10_15_effective_max_rounds_is_minimum_of_buyer_and_merchant(self):
        """10-15: max_rounds = min(buyer.maximum_negotiation_rounds, policy.maximum_negotiation_rounds)."""
        profile = self._make_buyer_profile(maximum_negotiation_rounds=5)
        # Policy has max 3, buyer has 5 -> effective should be 3
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        self.assertEqual(neg.max_rounds, 3)


class Step10OrchestratorRunTests(Step10BaseTestCase):

    def test_10_16_run_negotiation_reaches_terminal_state(self):
        """10-16: run_negotiation() always terminates in a terminal state."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        summary = AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        neg.refresh_from_db()
        terminal = {
            AgentNegotiation.STATUS_AGREED,
            AgentNegotiation.STATUS_REJECTED,
            AgentNegotiation.STATUS_EXPIRED,
        }
        self.assertIn(neg.status, terminal)
        self.assertIn(summary["status"], terminal)

    def test_10_17_fast_buyer_accepts_immediately(self):
        """10-17: FAST_BUYER with preferred_price >= catalog price accepts in round 0."""
        profile = self._make_buyer_profile_fast()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        summary = AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        neg.refresh_from_db()
        self.assertEqual(neg.status, AgentNegotiation.STATUS_AGREED)
        self.assertTrue(neg.payment_ready)
        self.assertIsNotNone(neg.agreed_price)

    def test_10_18_walk_away_buyer_is_rejected(self):
        """10-18: Buyer with walk_away_price << catalog price leads to REJECTED or EXPIRED."""
        profile = self._make_buyer_profile_walk_away()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        summary = AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        neg.refresh_from_db()
        self.assertIn(neg.status, {
            AgentNegotiation.STATUS_REJECTED,
            AgentNegotiation.STATUS_EXPIRED,
        })

    def test_10_19_agreed_negotiation_sets_payment_ready(self):
        """10-19: AGREED negotiation sets payment_ready=True."""
        profile = self._make_buyer_profile_fast()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        neg.refresh_from_db()
        if neg.status == AgentNegotiation.STATUS_AGREED:
            self.assertTrue(neg.payment_ready)

    def test_10_20_payment_ready_boundary_no_razorpay(self):
        """10-20: Agreed negotiation does NOT include Razorpay references."""
        profile = self._make_buyer_profile_fast()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        summary = AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        self.assertNotIn("razorpay", str(summary).lower())

    def test_10_21_run_on_terminal_negotiation_is_idempotent(self):
        """10-21: run_negotiation() on a terminal negotiation returns immediately without side effects."""
        profile = self._make_buyer_profile_fast()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        neg.refresh_from_db()
        event_count_before = neg.events.count()

        # Run again -- should be idempotent
        AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        neg.refresh_from_db()
        self.assertEqual(neg.events.count(), event_count_before)

    def test_10_22_round_limit_triggers_expired_or_terminal(self):
        """10-22: Negotiation terminates if max_rounds is exhausted without agreement."""
        profile = BuyerAgentProfile.objects.create(
            buyer_session_id="round-limit-buyer",
            name="Round Limit Buyer",
            requirements=["keyboard"],
            budget_min=Decimal("3600.00"),
            budget_max=Decimal("4800.00"),
            preferred_price=Decimal("4000.00"),
            maximum_price=Decimal("4800.00"),
            walk_away_price=Decimal("4800.00"),
            negotiation_enabled=True,
            maximum_negotiation_rounds=1,
            strategy=BuyerAgentProfile.STRATEGY_VALUE_SEEKER,
        )
        self.policy.maximum_negotiation_rounds = 1
        self.policy.save()

        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=30)
        neg.refresh_from_db()
        self.assertIn(neg.status, {
            AgentNegotiation.STATUS_EXPIRED,
            AgentNegotiation.STATUS_REJECTED,
            AgentNegotiation.STATUS_AGREED,
        })

    def test_10_23_summary_does_not_contain_cost_price(self):
        """10-23: Negotiation summary never exposes cost_price."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        summary = AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        self.assertNotIn("cost_price", str(summary))

    def test_10_24_summary_contains_decision_trace(self):
        """10-24: Negotiation summary includes a machine-readable 'trace' field."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        summary = AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        self.assertIn("trace", summary)
        self.assertIn("negotiation_id", summary["trace"])
        self.assertIn("rounds", summary["trace"])
        self.assertIn("final_status", summary["trace"])

    def test_10_25_event_log_is_append_only_and_ordered(self):
        """10-25: Event log grows monotonically and is ordered by creation time."""
        profile = self._make_buyer_profile()
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(profile.id),
            merchant_id=self.merchant.id,
        )
        events_before = neg.events.count()
        AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        events_after = neg.events.count()
        self.assertGreater(events_after, events_before)

        created_ats = list(neg.events.values_list("created_at", flat=True))
        self.assertEqual(created_ats, sorted(created_ats))


class Step10APITests(Step10BaseTestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_10_26_api_create_negotiation(self):
        """10-26: POST /api/ai/negotiations/ creates negotiation and returns negotiation_id."""
        profile = self._make_buyer_profile()
        resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": str(profile.id),
            "merchant_id": self.merchant.id,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("negotiation_id", resp.data)
        self.assertIn("status", resp.data)
        self.assertIn("merchant_id", resp.data)

    def test_10_27_api_run_negotiation(self):
        """10-27: POST /api/ai/negotiations/<id>/run/ executes negotiation and returns summary."""
        profile = self._make_buyer_profile()
        create_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": str(profile.id),
            "merchant_id": self.merchant.id,
        }, format="json")
        self.assertEqual(create_resp.status_code, 201)
        neg_id = create_resp.data["negotiation_id"]

        run_resp = self.client.post(f"/api/ai/negotiations/{neg_id}/run/",
                                    {"max_steps": 20}, format="json")
        self.assertEqual(run_resp.status_code, 200)
        self.assertIn("status", run_resp.data)
        self.assertIn("trace", run_resp.data)
        terminal = {"AGREED", "REJECTED", "EXPIRED"}
        self.assertIn(run_resp.data["status"], terminal)

    def test_10_28_api_negotiation_detail(self):
        """10-28: GET /api/ai/negotiations/<id>/ returns full detail including events and summary."""
        profile = self._make_buyer_profile_fast()
        create_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": str(profile.id),
            "merchant_id": self.merchant.id,
        }, format="json")
        neg_id = create_resp.data["negotiation_id"]
        self.client.post(f"/api/ai/negotiations/{neg_id}/run/",
                         {"max_steps": 20}, format="json")

        detail_resp = self.client.get(f"/api/ai/negotiations/{neg_id}/")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertIn("events", detail_resp.data)
        self.assertIn("summary", detail_resp.data)
        self.assertNotIn("cost_price", str(detail_resp.data))

    def test_10_29_api_negotiation_not_found(self):
        """10-29: GET /api/ai/negotiations/<unknown-id>/ returns 404."""
        import uuid
        resp = self.client.get(f"/api/ai/negotiations/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)

    def test_10_30_api_run_unknown_negotiation_returns_404(self):
        """10-30: POST /api/ai/negotiations/<unknown-id>/run/ returns 404."""
        import uuid
        resp = self.client.post(f"/api/ai/negotiations/{uuid.uuid4()}/run/",
                                {"max_steps": 10}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_10_31_full_e2e_ai_to_ai_negotiation_trace(self):
        """10-31: Full E2E -- fast buyer profile reaches AGREED with payment_ready and clean trace."""
        profile = self._make_buyer_profile_fast()

        # Create negotiation
        create_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": str(profile.id),
            "merchant_id": self.merchant.id,
        }, format="json")
        self.assertEqual(create_resp.status_code, 201)
        neg_id = create_resp.data["negotiation_id"]

        # Run negotiation
        run_resp = self.client.post(f"/api/ai/negotiations/{neg_id}/run/",
                                    {"max_steps": 20}, format="json")
        self.assertEqual(run_resp.status_code, 200)
        self.assertEqual(run_resp.data["status"], "AGREED")
        self.assertTrue(run_resp.data["payment_ready"])
        self.assertIsNotNone(run_resp.data["agreed_price"])

        # Verify detail view
        detail_resp = self.client.get(f"/api/ai/negotiations/{neg_id}/")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertGreater(len(detail_resp.data["events"]), 0)

        # Verify cost_price never leaked
        self.assertNotIn("cost_price", str(run_resp.data))
        self.assertNotIn("cost_price", str(detail_resp.data))

    def test_10_32_api_negotiations_list_filter_by_merchant_id(self):
        """10-32: GET /api/ai/negotiations/?merchant_id=<id> filters negotiations by merchant."""
        profile1 = self._make_buyer_profile_fast()
        resp1 = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": str(profile1.id),
            "merchant_id": self.merchant.id,
        }, format="json")
        self.assertEqual(resp1.status_code, 201)
        neg1_id = resp1.data["negotiation_id"]

        merchant2 = make_merchant(business_name="Second Merchant", email="second@merchant.test")
        MerchantPolicy.objects.create(
            merchant=merchant2,
            minimum_margin_percent=Decimal("15.00"),
            maximum_discount_percent=Decimal("10.00"),
            maximum_negotiation_rounds=3,
            auto_approval_limit=Decimal("10000.00"),
        )
        make_product(merchant2, name="Other Headset", price=Decimal("3000.00"))
        profile2 = BuyerAgentProfile.objects.create(
            buyer_session_id="session-buyer-m2",
            name="Buyer for M2",
            requirements=["headset"],
            budget_min=Decimal("2000.00"),
            budget_max=Decimal("4000.00"),
            preferred_price=Decimal("2500.00"),
            maximum_price=Decimal("3500.00"),
            walk_away_price=Decimal("3500.00"),
            negotiation_enabled=True,
            maximum_negotiation_rounds=3,
            strategy=BuyerAgentProfile.STRATEGY_FAST_BUYER,
        )
        resp2 = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": str(profile2.id),
            "merchant_id": merchant2.id,
        }, format="json")
        self.assertEqual(resp2.status_code, 201)
        neg2_id = resp2.data["negotiation_id"]

        filter1_resp = self.client.get(f"/api/ai/negotiations/?merchant_id={self.merchant.id}")
        self.assertEqual(filter1_resp.status_code, 200)
        filter1_ids = [n["id"] for n in filter1_resp.data]
        self.assertIn(neg1_id, filter1_ids)
        self.assertNotIn(neg2_id, filter1_ids)

        filter2_resp = self.client.get(f"/api/ai/negotiations/?merchant_id={merchant2.id}")
        self.assertEqual(filter2_resp.status_code, 200)
        filter2_ids = [n["id"] for n in filter2_resp.data]
        self.assertIn(neg2_id, filter2_ids)
        self.assertNotIn(neg1_id, filter2_ids)

        all_resp = self.client.get("/api/ai/negotiations/")
        self.assertEqual(all_resp.status_code, 200)
        all_ids = [n["id"] for n in all_resp.data]
        self.assertIn(neg1_id, all_ids)
        self.assertIn(neg2_id, all_ids)

    def test_10_33_find_optimal_counter_price_regression(self):
        """10-33: find_optimal_counter_price returns 3599.10 for catalog 3999, max discount 10%, min margin 18%."""
        from ai.services.negotiation_engine import NegotiationEngine
        optimal = NegotiationEngine.find_optimal_counter_price(
            catalog_price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            max_discount_pct=Decimal("10.00"),
            min_margin_pct=Decimal("18.00"),
            buyer_proposed_price=Decimal("3179.73")
        )
        self.assertEqual(optimal, Decimal("3599.10"))

    def test_10_34_evaluate_offer_monotonic_merchant_counter(self):
        """10-34: Multi-round counter-offer must NOT increase to 3999 after offering 3599.10."""
        from ai.services.negotiation_engine import NegotiationEngine
        product = make_product(self.merchant, name="Keyboard", price=Decimal("3999.00"), cost_price=Decimal("2700.00"))
        policy, _ = MerchantPolicy.objects.get_or_create(
            merchant=self.merchant,
            defaults={
                "minimum_margin_percent": Decimal("18.00"),
                "maximum_discount_percent": Decimal("10.00"),
                "maximum_negotiation_rounds": 3,
                "auto_approval_limit": Decimal("25000.00"),
            }
        )
        policy.minimum_margin_percent = Decimal("18.00")
        policy.maximum_discount_percent = Decimal("10.00")
        policy.save()

        # Buyer counters with 3179.73 in response to merchant's initial 3599.10
        merch_eval = NegotiationEngine.evaluate_offer(
            merchant_policy=policy,
            product=product,
            buyer_proposed_price=Decimal("3179.73"),
            current_round=0,
            previous_merchant_offer=Decimal("3599.10")
        )
        self.assertEqual(merch_eval["action"], "COUNTER")
        self.assertEqual(merch_eval["counter_price"], Decimal("3599.10"))
        self.assertLessEqual(merch_eval["counter_price"], Decimal("3599.10"))
        self.assertNotEqual(merch_eval["counter_price"], Decimal("3999.00"))

    def test_10_35_orchestrator_monotonic_and_round_limit(self):
        """10-35: End-to-end orchestrator ensures monotonic offers and enforces max_rounds=3 limit."""
        policy, _ = MerchantPolicy.objects.get_or_create(merchant=self.merchant)
        policy.maximum_discount_percent = Decimal("10.00")
        policy.minimum_margin_percent = Decimal("18.00")
        policy.maximum_negotiation_rounds = 3
        policy.save()

        buyer_profile = BuyerAgentProfile.objects.create(
            buyer_session_id="test-val-buyer",
            name="Alice",
            requirements=["keyboard"],
            budget_min=Decimal("2500.00"),
            budget_max=Decimal("3800.00"),
            preferred_price=Decimal("3000.00"),
            maximum_price=Decimal("3500.00"),
            walk_away_price=Decimal("3800.00"),
            negotiation_enabled=True,
            maximum_negotiation_rounds=3,
            strategy=BuyerAgentProfile.STRATEGY_VALUE_SEEKER,
        )

        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(buyer_profile.id),
            merchant_id=self.merchant.id
        )
        self.assertEqual(neg.max_rounds, 3)

        AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=20)
        neg.refresh_from_db()

        # Check all merchant events to ensure price never increases
        merchant_events = neg.events.filter(actor=AgentNegotiationEvent.ACTOR_AI_MERCHANT, proposed_price__isnull=False).order_by("created_at")
        prev_price = None
        for me in merchant_events:
            if prev_price is not None:
                self.assertLessEqual(me.proposed_price, prev_price, f"Merchant price increased from {prev_price} to {me.proposed_price}")
            prev_price = me.proposed_price

        # Ensure round count stayed within max_rounds
        self.assertLessEqual(neg.negotiation_round, neg.max_rounds)

    def test_10_36_buyer_profile_creation_with_frontend_payload(self):
        """10-36: POST /api/ai/buyer/profiles/ accepts frontend modal payload and derives economic constraints."""
        payload = {
            "name": "Alex Kumar",
            "budget_max": 3999.0,
            "price_sensitivity": "HIGH",
            "loyalty_tier": "NEW",
            "merchant": self.merchant.id,
            "product": self.keyboard.id,
        }
        resp = self.client.post("/api/ai/buyer/profiles/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("id", resp.data)
        prof_data = resp.data["profile"]
        self.assertEqual(prof_data["name"], "Alex Kumar")
        self.assertEqual(prof_data["strategy"], BuyerAgentProfile.STRATEGY_VALUE_SEEKER)
        self.assertIsNotNone(prof_data["buyer_session_id"])
        self.assertEqual(Decimal(str(prof_data["budget_max"])), Decimal("3999.00"))
        self.assertEqual(Decimal(str(prof_data["walk_away_price"])), Decimal("3999.00"))
        self.assertEqual(Decimal(str(prof_data["maximum_price"])), Decimal("3999.00"))
        self.assertEqual(Decimal(str(prof_data["preferred_price"])), Decimal("3199.20"))
        self.assertLessEqual(Decimal(str(prof_data["preferred_price"])), Decimal(str(prof_data["maximum_price"])))

    def test_10_37_new_autonomous_negotiation_full_flow_regression(self):
        """10-37: Full 3-step autonomous negotiation sequence succeeds without 400."""
        # 1. Create Buyer Profile
        p_resp = self.client.post("/api/ai/buyer/profiles/", {
            "name": "Alex Kumar",
            "budget_max": 3999.0,
            "price_sensitivity": "HIGH",
            "loyalty_tier": "NEW",
            "merchant": self.merchant.id,
            "product": self.keyboard.id,
        }, format="json")
        self.assertEqual(p_resp.status_code, 201)
        profile_id = p_resp.data["id"]

        # 2. Create Negotiation Session
        n_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": profile_id,
            "merchant_id": self.merchant.id,
            "product_id": self.keyboard.id,
        }, format="json")
        self.assertEqual(n_resp.status_code, 201)
        self.assertIn("negotiation_id", n_resp.data)
        self.assertIn("id", n_resp.data)
        self.assertEqual(n_resp.data["status"], AgentNegotiation.STATUS_ACTIVE)
        neg_id = n_resp.data["id"]

        # 3. Run Negotiation Session
        r_resp = self.client.post(f"/api/ai/negotiations/{neg_id}/run/", {
            "max_steps": 10
        }, format="json")
        self.assertEqual(r_resp.status_code, 200)
        self.assertIn(r_resp.data["status"], {"AGREED", "REJECTED", "EXPIRED"})
        self.assertIn("trace", r_resp.data)
        self.assertTrue(len(r_resp.data["trace"]) > 0)

    def test_10_38_buyer_portal_intent_to_agreement_pipeline(self):
        """10-38: End-to-end Buyer Portal pipeline: intent extraction -> product match -> negotiation -> agreement."""
        # Step 1: Buyer queries intent
        intent_resp = self.client.post("/api/ai/intent/", {
            "message": "I want a gaming keyboard under 6000",
            "merchant_id": self.merchant.id,
        }, format="json")
        self.assertEqual(intent_resp.status_code, 200)
        matched_products = intent_resp.data.get("matches", [])
        self.assertTrue(len(matched_products) > 0)
        
        # Verify cost_price is shielded from buyer
        import json
        raw_intent = json.dumps(intent_resp.data)
        self.assertNotIn("cost_price", raw_intent)
        
        # Pick the keyboard
        matched_kb = next((p for p in matched_products if p["id"] == self.keyboard.id), None)
        self.assertIsNotNone(matched_kb)
        self.assertEqual(Decimal(str(matched_kb["price"])), Decimal("6000.00"))

        # Step 2: Create buyer profile based on user's query
        p_resp = self.client.post("/api/ai/buyer/profiles/", {
            "name": "Consumer Alex",
            "budget_max": 6000.0,
            "price_sensitivity": "MEDIUM",
            "loyalty_tier": "NEW",
            "merchant": self.merchant.id,
            "product": self.keyboard.id,
        }, format="json")
        self.assertEqual(p_resp.status_code, 201)
        profile_id = p_resp.data["id"]

        # Step 3: Create autonomous negotiation session
        n_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": profile_id,
            "merchant_id": self.merchant.id,
            "product_id": self.keyboard.id,
        }, format="json")
        self.assertEqual(n_resp.status_code, 201)
        neg_id = n_resp.data["id"]


        # Step 4: Run AI-to-AI autonomous negotiation
        r_resp = self.client.post(f"/api/ai/negotiations/{neg_id}/run/", {
            "max_steps": 10
        }, format="json")
        self.assertEqual(r_resp.status_code, 200)
        self.assertEqual(r_resp.data["status"], "AGREED")
        self.assertEqual(Decimal(str(r_resp.data["agreed_price"])), Decimal("5100.00"))
        self.assertTrue(r_resp.data["payment_ready"])


# ===========================================================================
# Buyer Budget Propagation Tests
# ===========================================================================

from ai.services.buyer_decision_engine import BuyerDecisionEngine


class BuyerBudgetPropagationTests(TestCase):
    """
    Tests that explicit buyer budget and preferred price values
    correctly propagate through BuyerAgentProfile creation and
    into BuyerDecisionEngine decisions.
    """

    @classmethod
    def setUpTestData(cls):
        cls.merchant = make_merchant(business_name="Budget Test Store")
        MerchantPolicy.objects.create(
            merchant=cls.merchant,
            maximum_discount_percent=Decimal("10.00"),
            minimum_margin_percent=Decimal("18.00"),
            maximum_negotiation_rounds=5,
            auto_approval_limit=Decimal("50000.00"),
        )
        cls.product = make_product(
            cls.merchant,
            name="Mechanical Gaming Keyboard",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2400.00"),
            inventory_quantity=20,
        )
        cls.client = APIClient()

    def setUp(self):
        self.client = APIClient()

    def _create_profile(self, budget_max, preferred_price=None, strategy="BALANCED"):
        """Helper to POST a buyer profile and return the response data profile dict."""
        payload = {
            "buyer_session_id": f"test-session-{budget_max}-{preferred_price}",
            "name": "Test Buyer",
            "budget_min": 0,
            "budget_max": budget_max,
            "maximum_price": budget_max,
            "walk_away_price": budget_max,
            "strategy": strategy,
            "negotiation_enabled": True,
            "maximum_negotiation_rounds": 3,
            "requirements": [self.product.name],
        }
        if preferred_price is not None:
            payload["preferred_price"] = preferred_price
        resp = self.client.post("/api/ai/buyer/profiles/", payload, format="json")
        self.assertEqual(resp.status_code, 201, f"Profile creation failed: {resp.data}")
        return resp.data

    def test_budget_3600_preferred_3400(self):
        """TEST 1: budget_max=3600, preferred_price=3400 — values propagate exactly."""
        resp_data = self._create_profile(budget_max=3600, preferred_price=3400)
        profile_data = resp_data["profile"]
        self.assertEqual(Decimal(str(profile_data["budget_max"])), Decimal("3600.00"))
        self.assertEqual(Decimal(str(profile_data["preferred_price"])), Decimal("3400.00"))
        self.assertEqual(Decimal(str(profile_data["maximum_price"])), Decimal("3600.00"))
        self.assertEqual(Decimal(str(profile_data["walk_away_price"])), Decimal("3600.00"))

    def test_budget_3600_preferred_3500(self):
        """TEST 2: budget_max=3600, preferred_price=3500 — different preferred."""
        resp_data = self._create_profile(budget_max=3600, preferred_price=3500)
        profile_data = resp_data["profile"]
        self.assertEqual(Decimal(str(profile_data["preferred_price"])), Decimal("3500.00"))
        self.assertEqual(Decimal(str(profile_data["maximum_price"])), Decimal("3600.00"))

    def test_low_budget_3200_rejects_high_offer(self):
        """TEST 3: budget_max=3200 — merchant min ₹3599.10 > walk_away → REJECT on exhausted rounds."""
        resp_data = self._create_profile(budget_max=3200, preferred_price=3000)
        profile = BuyerAgentProfile.objects.get(id=resp_data["id"])

        # Simulate a merchant offer of ₹3599.10 (10% off ₹3999) at final round
        merchant_offer = Decimal("3599.10")

        result = BuyerDecisionEngine.evaluate_offer(
            product=self.product,
            merchant_offer=merchant_offer,
            buyer_profile=profile,
            current_round=3,  # Final round, rounds exhausted
        )
        self.assertEqual(result["decision"], "REJECT",
                         f"Expected REJECT for offer {merchant_offer} > walk_away {profile.walk_away_price}")

    def test_high_budget_4000_accepts_within_range(self):
        """TEST 4: budget_max=4000 — merchant offer ₹3599.10 ≤ max → accepted via engine."""
        resp_data = self._create_profile(budget_max=4000, preferred_price=3500, strategy="BALANCED")
        profile = BuyerAgentProfile.objects.get(id=resp_data["id"])

        merchant_offer = Decimal("3599.10")

        result = BuyerDecisionEngine.evaluate_offer(
            product=self.product,
            merchant_offer=merchant_offer,
            buyer_profile=profile,
            current_round=1,
        )
        self.assertEqual(result["decision"], "ACCEPT",
                         f"Expected ACCEPT for offer {merchant_offer} within budget. Got: {result['decision']}")
        self.assertEqual(result["agreed_price"], merchant_offer)


# ===========================================================================
# Buyer Budget vs Merchant Floor Full E2E Negotiation Tests (Tests A-F)
# ===========================================================================

from ai.services.agent_negotiation import AgentNegotiationOrchestrator


class BuyerBudgetVsMerchantFloorNegotiationTests(TestCase):
    """
    Direct regression tests for Tasks 8 (Tests A to F):
    - Test A: Laptop Catalog Rs.64,999, Buyer max Rs.60,000, Floor Rs.58,499.10 -> AGREED
    - Test B: Laptop Catalog Rs.64,999, Buyer max Rs.57,000, Floor Rs.58,499.10 -> REJECTED
    - Test C: Keyboard Catalog Rs.3,999, Buyer max Rs.3,600, Floor Rs.3,599.10 -> AGREED
    - Test D: NL Query "High performance laptop under Rs.60,000" -> parsed budget_max=60000 -> maximum_price=60000
    - Test E: NL Query "I want a gaming keyboard under Rs.3,600" -> parsed budget_max=3600
    - Test F: Invariant: agreed_price >= merchant_policy_floor and agreed_price <= buyer.maximum_price
    """

    @classmethod
    def setUpTestData(cls):
        cls.merchant = make_merchant(business_name="NovaTech Store Floor Test")
        cls.policy = MerchantPolicy.objects.create(
            merchant=cls.merchant,
            maximum_discount_percent=Decimal("10.00"),
            minimum_margin_percent=Decimal("18.00"),
            maximum_negotiation_rounds=3,
            auto_approval_limit=Decimal("50000.00"),
        )
        cls.laptop = make_product(
            cls.merchant,
            name="Performance Laptop",
            category="Laptops",
            price=Decimal("64999.00"),
            cost_price=Decimal("45000.00"),
            inventory_quantity=10,
        )
        cls.keyboard = make_product(
            cls.merchant,
            name="Mechanical Gaming Keyboard",
            category="Gaming",
            price=Decimal("3999.00"),
            cost_price=Decimal("2700.00"),
            inventory_quantity=20,
        )

    def setUp(self):
        self.client = APIClient()

    def test_scenario_a_laptop_budget_60000_agreed(self):
        """TEST A: Performance Laptop (64,999), Buyer max 60,000, Merchant max discount 10% (Floor 58,499.10) -> AGREED."""
        # Create Buyer Profile
        p_resp = self.client.post("/api/ai/buyer/profiles/", {
            "name": "Shopper Alex",
            "budget_max": 60000.0,
            "maximum_price": 60000.0,
            "walk_away_price": 60000.0,
            "preferred_price": 51000.0,
            "strategy": "BALANCED",
            "negotiation_enabled": True,
            "maximum_negotiation_rounds": 3,
            "requirements": [self.laptop.name],
        }, format="json")
        self.assertEqual(p_resp.status_code, 201)
        profile_id = p_resp.data["id"]

        # Create Negotiation
        n_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": profile_id,
            "merchant_id": self.merchant.id,
            "product_id": self.laptop.id,
        }, format="json")
        self.assertEqual(n_resp.status_code, 201)
        neg_id = n_resp.data["id"]

        # Run AI-to-AI Negotiation
        r_resp = self.client.post(f"/api/ai/negotiations/{neg_id}/run/", {
            "max_steps": 10
        }, format="json")
        self.assertEqual(r_resp.status_code, 200)

        # Expected: NEGOTIATION ALLOWED and AGREED
        self.assertEqual(r_resp.data["status"], "AGREED")
        agreed_price = Decimal(str(r_resp.data["agreed_price"]))
        merchant_floor = Decimal("58499.10")

        self.assertLessEqual(agreed_price, Decimal("60000.00"))
        self.assertGreaterEqual(agreed_price, merchant_floor)
        self.assertEqual(agreed_price, merchant_floor)
        self.assertTrue(r_resp.data["payment_ready"])

    def test_scenario_b_laptop_budget_57000_rejected(self):
        """TEST B: Performance Laptop (64,999), Buyer max 57,000, Merchant floor 58,499.10 -> REJECTED."""
        p_resp = self.client.post("/api/ai/buyer/profiles/", {
            "name": "Budget Conscious Buyer",
            "budget_max": 57000.0,
            "maximum_price": 57000.0,
            "walk_away_price": 57000.0,
            "preferred_price": 50000.0,
            "strategy": "BALANCED",
            "negotiation_enabled": True,
            "maximum_negotiation_rounds": 3,
            "requirements": [self.laptop.name],
        }, format="json")
        self.assertEqual(p_resp.status_code, 201)
        profile_id = p_resp.data["id"]

        n_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": profile_id,
            "merchant_id": self.merchant.id,
            "product_id": self.laptop.id,
        }, format="json")
        self.assertEqual(n_resp.status_code, 201)
        neg_id = n_resp.data["id"]

        r_resp = self.client.post(f"/api/ai/negotiations/{neg_id}/run/", {
            "max_steps": 10
        }, format="json")
        self.assertEqual(r_resp.status_code, 200)

        # Expected: REJECTED (Buyer budget is below merchant's policy floor)
        self.assertEqual(r_resp.data["status"], "REJECTED")
        self.assertIsNone(r_resp.data["agreed_price"])

    def test_scenario_c_keyboard_budget_3600_agreed(self):
        """TEST C: Keyboard (3,999), Buyer max 3,600, Merchant floor 3,599.10 -> AGREED."""
        p_resp = self.client.post("/api/ai/buyer/profiles/", {
            "name": "Gamer Sam",
            "budget_max": 3600.0,
            "maximum_price": 3600.0,
            "walk_away_price": 3600.0,
            "preferred_price": 3200.0,
            "strategy": "BALANCED",
            "negotiation_enabled": True,
            "maximum_negotiation_rounds": 3,
            "requirements": [self.keyboard.name],
        }, format="json")
        self.assertEqual(p_resp.status_code, 201)
        profile_id = p_resp.data["id"]

        n_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": profile_id,
            "merchant_id": self.merchant.id,
            "product_id": self.keyboard.id,
        }, format="json")
        self.assertEqual(n_resp.status_code, 201)
        neg_id = n_resp.data["id"]

        r_resp = self.client.post(f"/api/ai/negotiations/{neg_id}/run/", {
            "max_steps": 10
        }, format="json")
        self.assertEqual(r_resp.status_code, 200)

        self.assertEqual(r_resp.data["status"], "AGREED")
        agreed_price = Decimal(str(r_resp.data["agreed_price"]))
        self.assertLessEqual(agreed_price, Decimal("3600.00"))
        self.assertGreaterEqual(agreed_price, Decimal("3599.10"))

    def test_scenario_d_nl_intent_laptop_under_60000(self):
        """TEST D: Query 'High performance laptop under ₹60,000' -> budget_max=60000 -> maximum_price=60000."""
        intent = extract_intent("High performance laptop under ₹60,000")
        self.assertEqual(float(intent.budget_max), 60000.0)

        # Profile created using parsed intent
        p_resp = self.client.post("/api/ai/buyer/profiles/", {
            "name": "NL Buyer",
            "budget_max": intent.budget_max,
            "maximum_price": intent.budget_max,
            "walk_away_price": intent.budget_max,
            "strategy": "BALANCED",
            "requirements": [self.laptop.name],
        }, format="json")
        self.assertEqual(p_resp.status_code, 201)
        profile_data = p_resp.data["profile"]
        self.assertEqual(Decimal(str(profile_data["budget_max"])), Decimal("60000.00"))
        self.assertEqual(Decimal(str(profile_data["maximum_price"])), Decimal("60000.00"))

    def test_scenario_e_nl_intent_keyboard_under_3600(self):
        """TEST E: Query 'I want a gaming keyboard under ₹3,600' -> budget_max=3600."""
        intent = extract_intent("I want a gaming keyboard under ₹3,600")
        self.assertEqual(float(intent.budget_max), 3600.0)

    def test_scenario_f_invariants_policy_compliance(self):
        """TEST F: Invariant: agreed_price >= merchant_policy_floor and agreed_price <= buyer.maximum_price."""
        p_resp = self.client.post("/api/ai/buyer/profiles/", {
            "name": "Invariant Test Buyer",
            "budget_max": 62000.0,
            "maximum_price": 62000.0,
            "walk_away_price": 62000.0,
            "preferred_price": 55000.0,
            "strategy": "BALANCED",
            "negotiation_enabled": True,
            "maximum_negotiation_rounds": 3,
            "requirements": [self.laptop.name],
        }, format="json")
        profile_id = p_resp.data["id"]

        n_resp = self.client.post("/api/ai/negotiations/", {
            "buyer_profile_id": profile_id,
            "merchant_id": self.merchant.id,
            "product_id": self.laptop.id,
        }, format="json")
        neg_id = n_resp.data["id"]

        r_resp = self.client.post(f"/api/ai/negotiations/{neg_id}/run/", {
            "max_steps": 10
        }, format="json")
        self.assertEqual(r_resp.data["status"], "AGREED")

        agreed = Decimal(str(r_resp.data["agreed_price"]))
        merchant_floor = Decimal("58499.10")
        buyer_max = Decimal("62000.00")

        self.assertGreaterEqual(agreed, merchant_floor, "Agreed price violated merchant policy floor!")
        self.assertLessEqual(agreed, buyer_max, "Agreed price violated buyer maximum budget!")

