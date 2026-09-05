"""
ai/services/revenue_engine.py
Deterministic Revenue Opportunity Engine.

This module converts a BuyerIntent + candidate products + MerchantPolicy into
a ranked list of RevenueOpportunity objects using merchant-economic opportunity
scoring.

SCORING PHILOSOPHY
The opportunity_score is a deterministic heuristic that reflects
merchant-economic desirability.  It is NOT a machine-learning prediction
of conversion probability or actual revenue.

Scoring signals (stored verbatim in opportunity.metadata["signals"]):
  * intent_relevance    - how well the product matches the buyer query
  * budget_fit          - price position relative to the buyer budget
  * margin_preservation - how much of the gross margin is preserved
  * inventory           - reward for healthy stock levels
  * action_factor       - per-action base weight (tunable constant)

IMPORTANT SECURITY CONSTRAINTS
- cost_price is used ONLY internally and must NEVER be serialised to
  any buyer-facing API response.
- Opportunity objects are transient (not persisted to the database).

ARCHITECTURE
Natural language -> Intent Engine -> Product Matcher ->
Revenue Opportunity Engine (this module) -> Ranked RevenueOpportunity list
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from merchants.models import MerchantPolicy
    from products.models import Product
    from .intent_engine import BuyerIntent


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Candidate discount steps (percent).  The engine evaluates each step and
# validates it against maximum_discount_percent AND minimum_margin_percent.
# maximum_discount_percent is the policy CEILING, not the optimum.
_DISCOUNT_STEPS: list[Decimal] = [
    Decimal("2"),
    Decimal("5"),
    Decimal("8"),
]

# Bundle complementary-category rules.
# (trigger_category, complementary_name_keywords)
_BUNDLE_PAIRS: list[tuple[str, list[str]]] = [
    ("Gaming", ["mouse"]),
    ("Gaming", ["keyboard"]),
    ("Gaming", ["monitor"]),
    ("Monitors", ["keyboard"]),
    ("Monitors", ["mouse"]),
]

# Minimum relevance score to qualify as upsell candidate.
_MIN_RELEVANCE_FOR_UPSELL = 0

# Fixed bundle discount applied on the combined individual price total.
_BUNDLE_DISCOUNT_PERCENT = Decimal("5")

# Action base weights.
_ACTION_FACTOR: dict[str, int] = {
    "NO_ACTION": 10,
    "DISCOUNT":  15,
    "UPSELL":    20,
    "BUNDLE":    18,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RevenueOpportunity:
    """A single merchant-economic opportunity candidate."""
    action: str
    product_id: int
    product_name: str
    base_product_id: int
    recommended_product_id: Optional[int]
    recommended_product_name: Optional[str]
    current_price: Decimal
    proposed_price: Decimal
    price_difference: Decimal
    discount_amount: Decimal
    discount_percent: Decimal
    resulting_margin_percent: Decimal
    opportunity_score: int
    policy_compliant: bool
    reason: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Financial helpers
# ---------------------------------------------------------------------------

def _two(value: Decimal) -> Decimal:
    """Round to 2 decimal places (ROUND_HALF_UP)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_margin(selling_price: Decimal, cost_price: Decimal) -> Decimal:
    """
    margin_percent = ((selling_price - cost_price) / selling_price) * 100
    Raises ZeroDivisionError if selling_price is zero.
    """
    if selling_price == Decimal("0"):
        raise ZeroDivisionError("selling_price must not be zero.")
    return _two((selling_price - cost_price) / selling_price * Decimal("100"))


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _budget_fit_score(price: Decimal, intent: "BuyerIntent") -> int:
    """
    Score how well the price fits the buyer budget.
    BuyerIntent budget values are floats; coerce to Decimal for arithmetic.
    """
    score = 0
    if intent.budget_max is not None:
        budget_max = Decimal(str(intent.budget_max))
        if price <= budget_max:
            score += 20
            headroom = budget_max - price
            if headroom > Decimal("0"):
                score += min(10, int(headroom / budget_max * Decimal("20")))
        else:
            overage = price - budget_max
            pct_over = int(overage / budget_max * Decimal("100"))
            score -= min(30, pct_over)
    if intent.budget_min is not None:
        budget_min = Decimal(str(intent.budget_min))
        if price < budget_min:
            score -= 10
    return score



def _margin_preservation_score(
    resulting_margin: Decimal, minimum_margin: Decimal
) -> int:
    spread = resulting_margin - minimum_margin
    if spread < Decimal("0"):
        return -50
    elif spread < Decimal("2"):
        return 5
    elif spread < Decimal("5"):
        return 15
    else:
        return 25


def _inventory_score(quantity: int) -> int:
    if quantity <= 0:
        return -100
    elif quantity < 5:
        return 0
    elif quantity < 20:
        return 5
    else:
        return 10


def calculate_opportunity_score(
    *,
    intent_relevance: int,
    budget_fit: int,
    margin_preservation: int,
    inventory: int,
    action_factor: int,
    policy_compliant: bool,
) -> tuple[int, dict]:
    """
    Compute deterministic heuristic opportunity_score.
    Returns (score, signals_dict) — signals stored in metadata["signals"]
    for explainable AI decision traces.
    """
    signals = {
        "intent_relevance":    intent_relevance,
        "budget_fit":          budget_fit,
        "margin_preservation": margin_preservation,
        "inventory":           inventory,
        "action_factor":       action_factor,
    }
    raw = (
        intent_relevance
        + budget_fit
        + margin_preservation
        + inventory
        + action_factor
        + (0 if policy_compliant else -100)
    )
    return raw, signals


# ---------------------------------------------------------------------------
# Per-action generators
# ---------------------------------------------------------------------------

def _generate_no_action(
    product: "Product",
    intent: "BuyerIntent",
    policy: "MerchantPolicy",
    relevance: int,
) -> RevenueOpportunity:
    price  = product.price
    margin = calculate_margin(price, product.cost_price)
    compliant = margin >= policy.minimum_margin_percent

    score, signals = calculate_opportunity_score(
        intent_relevance    = relevance,
        budget_fit          = _budget_fit_score(price, intent),
        margin_preservation = _margin_preservation_score(margin, policy.minimum_margin_percent),
        inventory           = _inventory_score(product.inventory_quantity),
        action_factor       = _ACTION_FACTOR["NO_ACTION"],
        policy_compliant    = compliant,
    )
    return RevenueOpportunity(
        action="NO_ACTION",
        product_id=product.pk,
        product_name=product.name,
        base_product_id=product.pk,
        recommended_product_id=None,
        recommended_product_name=None,
        current_price=_two(price),
        proposed_price=_two(price),
        price_difference=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        discount_percent=Decimal("0.00"),
        resulting_margin_percent=margin,
        opportunity_score=score,
        policy_compliant=compliant,
        reason="Sell at catalog price — no adjustment needed.",
        metadata={"signals": signals},
    )


def _generate_discounts(
    product: "Product",
    intent: "BuyerIntent",
    policy: "MerchantPolicy",
    relevance: int,
) -> list[RevenueOpportunity]:
    """
    Generate DISCOUNT candidates.

    Flow:
      1. Build candidate discount percentages from fixed steps + policy max.
      2. For each: validate <= max_discount_percent.
      3. Compute proposed_price and resulting margin.
      4. Validate resulting margin >= minimum_margin_percent.
      5. Score each candidate independently.
      6. Return all (compliant and non-compliant, marked accordingly).

    The policy maximum is the CEILING, not the automatic optimum.
    Smaller, margin-preserving discounts may score higher.
    """
    candidates: list[RevenueOpportunity] = []
    max_disc = policy.maximum_discount_percent

    steps = list(_DISCOUNT_STEPS)
    if max_disc not in steps and max_disc > Decimal("0"):
        steps.append(max_disc)
    steps = sorted(set(steps))

    for disc_pct in steps:
        exceeds_policy  = disc_pct > max_disc
        discount_amount = _two(product.price * disc_pct / Decimal("100"))
        proposed_price  = _two(product.price - discount_amount)

        if proposed_price <= Decimal("0"):
            continue

        resulting_margin = calculate_margin(proposed_price, product.cost_price)
        violates_margin  = resulting_margin < policy.minimum_margin_percent
        compliant        = not exceeds_policy and not violates_margin

        score, signals = calculate_opportunity_score(
            intent_relevance    = relevance,
            budget_fit          = _budget_fit_score(proposed_price, intent),
            margin_preservation = _margin_preservation_score(
                resulting_margin, policy.minimum_margin_percent
            ),
            inventory           = _inventory_score(product.inventory_quantity),
            action_factor       = _ACTION_FACTOR["DISCOUNT"],
            policy_compliant    = compliant,
        )

        if exceeds_policy:
            reason = (
                f"Discount of {disc_pct}% exceeds policy maximum "
                f"({max_disc}%) — not compliant."
            )
        elif violates_margin:
            reason = (
                f"Discount of {disc_pct}% reduces margin to "
                f"{resulting_margin}% which is below the policy minimum "
                f"of {policy.minimum_margin_percent}%."
            )
        else:
            reason = (
                f"Offer {disc_pct}% discount: price Rs.{proposed_price} "
                f"preserves {resulting_margin}% margin."
            )

        candidates.append(RevenueOpportunity(
            action="DISCOUNT",
            product_id=product.pk,
            product_name=product.name,
            base_product_id=product.pk,
            recommended_product_id=None,
            recommended_product_name=None,
            current_price=_two(product.price),
            proposed_price=proposed_price,
            price_difference=_two(proposed_price - product.price),
            discount_amount=discount_amount,
            discount_percent=disc_pct,
            resulting_margin_percent=resulting_margin,
            opportunity_score=score,
            policy_compliant=compliant,
            reason=reason,
            metadata={"signals": signals, "discount_step": str(disc_pct)},
        ))

    return candidates


def _generate_upsells(
    product: "Product",
    intent: "BuyerIntent",
    policy: "MerchantPolicy",
    relevance: int,
    all_products: list["Product"],
) -> list[RevenueOpportunity]:
    """Generate UPSELL opportunities from same-category higher-priced products."""
    from .product_matcher import get_product_relevance_score

    candidates: list[RevenueOpportunity] = []

    for candidate in all_products:
        if candidate.pk == product.pk:
            continue
        if not candidate.is_active or candidate.inventory_quantity <= 0:
            continue
        if candidate.price <= product.price:
            continue
        if candidate.category.lower() != product.category.lower():
            continue

        cand_relevance = get_product_relevance_score(candidate, intent)
        if cand_relevance < _MIN_RELEVANCE_FOR_UPSELL:
            continue

        margin    = calculate_margin(candidate.price, candidate.cost_price)
        compliant = margin >= policy.minimum_margin_percent

        score, signals = calculate_opportunity_score(
            intent_relevance    = cand_relevance,
            budget_fit          = _budget_fit_score(candidate.price, intent),
            margin_preservation = _margin_preservation_score(
                margin, policy.minimum_margin_percent
            ),
            inventory           = _inventory_score(candidate.inventory_quantity),
            action_factor       = _ACTION_FACTOR["UPSELL"],
            policy_compliant    = compliant,
        )

        candidates.append(RevenueOpportunity(
            action="UPSELL",
            product_id=product.pk,
            product_name=product.name,
            base_product_id=product.pk,
            recommended_product_id=candidate.pk,
            recommended_product_name=candidate.name,
            current_price=_two(product.price),
            proposed_price=_two(candidate.price),
            price_difference=_two(candidate.price - product.price),
            discount_amount=Decimal("0.00"),
            discount_percent=Decimal("0.00"),
            resulting_margin_percent=margin,
            opportunity_score=score,
            policy_compliant=compliant,
            reason=(
                f"Upgrade to '{candidate.name}' (+Rs.{_two(candidate.price - product.price)}) "
                f"for a better {candidate.category} experience."
            ),
            metadata={"signals": signals},
        ))

    return candidates


def _generate_bundles(
    product: "Product",
    intent: "BuyerIntent",
    policy: "MerchantPolicy",
    relevance: int,
    all_products: list["Product"],
) -> list[RevenueOpportunity]:
    """Generate two-product BUNDLE opportunities per complementary-category rules."""
    candidates: list[RevenueOpportunity] = []

    complementary_keywords: list[str] = []
    for trigger_cat, keywords in _BUNDLE_PAIRS:
        if trigger_cat.lower() == product.category.lower():
            complementary_keywords.extend(keywords)

    if not complementary_keywords:
        return []

    seen: set[int] = set()

    for companion in all_products:
        if companion.pk == product.pk:
            continue
        if not companion.is_active or companion.inventory_quantity <= 0:
            continue
        if companion.pk in seen:
            continue

        matched = next(
            (kw for kw in complementary_keywords if kw in companion.name.lower()), None
        )
        if matched is None:
            continue

        seen.add(companion.pk)

        individual_total = _two(product.price + companion.price)
        bundle_discount  = _two(individual_total * _BUNDLE_DISCOUNT_PERCENT / Decimal("100"))
        bundle_price     = _two(individual_total - bundle_discount)
        combined_cost    = product.cost_price + companion.cost_price
        bundle_margin    = _two(
            (bundle_price - combined_cost) / bundle_price * Decimal("100")
        )
        compliant = bundle_margin >= policy.minimum_margin_percent

        score, signals = calculate_opportunity_score(
            intent_relevance    = relevance,
            budget_fit          = _budget_fit_score(bundle_price, intent),
            margin_preservation = _margin_preservation_score(
                bundle_margin, policy.minimum_margin_percent
            ),
            inventory           = min(
                _inventory_score(product.inventory_quantity),
                _inventory_score(companion.inventory_quantity),
            ),
            action_factor       = _ACTION_FACTOR["BUNDLE"],
            policy_compliant    = compliant,
        )

        if compliant:
            reason = (
                f"Bundle '{product.name}' + '{companion.name}' at "
                f"Rs.{bundle_price} ({_BUNDLE_DISCOUNT_PERCENT}% bundle "
                f"saving, margin {bundle_margin}%)."
            )
        else:
            reason = (
                f"Bundle '{product.name}' + '{companion.name}' would yield "
                f"{bundle_margin}% margin — below policy minimum "
                f"({policy.minimum_margin_percent}%)."
            )

        candidates.append(RevenueOpportunity(
            action="BUNDLE",
            product_id=product.pk,
            product_name=product.name,
            base_product_id=product.pk,
            recommended_product_id=companion.pk,
            recommended_product_name=companion.name,
            current_price=_two(product.price),
            proposed_price=bundle_price,
            price_difference=_two(bundle_price - individual_total),
            discount_amount=bundle_discount,
            discount_percent=_BUNDLE_DISCOUNT_PERCENT,
            resulting_margin_percent=bundle_margin,
            opportunity_score=score,
            policy_compliant=compliant,
            reason=reason,
            metadata={
                "signals":          signals,
                "companion_price":  str(_two(companion.price)),
                "individual_total": str(individual_total),
                "bundle_discount":  str(bundle_discount),
            },
        ))

    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_opportunities(
    intent: "BuyerIntent",
    products: list["Product"],
    policy: "MerchantPolicy",
) -> list[RevenueOpportunity]:
    """
    Generate and rank merchant-economic revenue opportunities.

    Parameters
    ----------
    intent   : Structured buyer intent from intent_engine.extract_intent().
    products : Candidate products from product_matcher.find_matching_products().
    policy   : MerchantPolicy governing discount and margin limits.

    Returns
    -------
    list[RevenueOpportunity]
        All opportunity candidates ranked by opportunity_score (desc).
        Non-compliant candidates included with policy_compliant=False
        for the future Decision Engine to inspect.
    """
    from .product_matcher import get_product_relevance_score  # noqa: F401 (used by sub-fns)

    if not products:
        return []

    opportunities: list[RevenueOpportunity] = []

    for product in products:
        relevance = get_product_relevance_score(product, intent)

        opportunities.append(_generate_no_action(product, intent, policy, relevance))
        opportunities.extend(_generate_discounts(product, intent, policy, relevance))
        opportunities.extend(_generate_upsells(product, intent, policy, relevance, products))
        opportunities.extend(_generate_bundles(product, intent, policy, relevance, products))

    # Deterministic ranking: score desc, action name for stable tie-break
    opportunities.sort(key=lambda o: (-o.opportunity_score, o.action))
    return opportunities
