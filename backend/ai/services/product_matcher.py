"""
ai/services/product_matcher.py
───────────────────────────────
Translates a BuyerIntent into a relevance-ranked list of candidate Products.

Two-phase approach
──────────────────
Phase 1 — Hard filters (ORM, database-level)
    • Only active products (is_active=True)
    • Only in-stock products (inventory_quantity > 0)
    • Price within [budget_min, budget_max] if specified
    • Category match if specified

Phase 2 — Relevance scoring (Python, in-memory)
    Scores every candidate that passed the hard filters. Products are then
    ranked by score (descending) and by price (ascending) as a tiebreaker.

    When intent.product_type is set (e.g. "keyboard"), products whose name
    and description do NOT contain a matching product-type keyword receive a
    heavy penalty (-80 points) and are excluded if their final score < 0.
    This prevents "gaming mouse" from appearing in a "gaming keyboard" search.

    Scoring signals:
    ────────────────
    +50  Core product-type keyword found in product name/description
    -80  Core product-type keyword NOT found  (wrong product type)
    +30  Full search_query phrase found in product name
    + 8  Individual search_query word (>3 chars) found in product name
    + 8  Each requirement keyword found in product text
    + 3  Each preference keyword found in product text

    Preferences affect ranking only — they never exclude.

No external APIs, embeddings, or LLM calls.
Returns a list[Product] ordered by relevance (best first).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from django.db.models import Q

from .intent_engine import BuyerIntent

if TYPE_CHECKING:
    from merchants.models import Merchant
    from products.models import Product


# ===========================================================================
# Product-type synonym groups
# ===========================================================================
# When checking whether a product's text "contains the right product type",
# we expand the core keyword to its synonym group so that:
#   - A "headset" query still matches a product called "Headphones"
#   - A "mouse" query still matches "mice" in product text
#
# Each tuple is a frozenset of synonyms treated as equivalent.
_SYNONYM_GROUPS: list[frozenset[str]] = [
    frozenset({"headphone", "headphones", "headset", "earphone", "earphones",
               "earbud", "earbuds"}),
    frozenset({"mouse", "mice"}),
    frozenset({"keyboard", "keyboards"}),
    frozenset({"monitor", "monitors", "display", "screen"}),
    frozenset({"laptop", "laptops", "notebook"}),
    frozenset({"speaker", "speakers"}),
]


def _synonym_group(core_type: str) -> frozenset[str]:
    """Return the synonym group containing core_type, or a singleton set."""
    for group in _SYNONYM_GROUPS:
        if core_type in group:
            return group
    return frozenset({core_type})


# ===========================================================================
# Relevance scorer
# ===========================================================================

def get_product_relevance_score(product: "Product", intent: BuyerIntent) -> int:
    """
    Compute an integer relevance score for a single product against an intent.

    Positive score  → product is a good match.
    Negative score  → product is the wrong type (excluded when product_type set).
    """
    score = 0
    text = (product.name + " " + product.description).lower()
    name_lower = product.name.lower()

    # ── Core product-type match ───────────────────────────────────────────────
    # This is the dominant signal.  A keyboard request must return keyboards.
    if intent.product_type:
        synonyms = _synonym_group(intent.product_type)
        type_found = any(
            re.search(rf"\b{re.escape(syn)}\b", text)
            for syn in synonyms
        )
        if type_found:
            score += 50
        else:
            score -= 80  # Wrong product type → heavy penalty

    # ── Search query in product name ──────────────────────────────────────────
    if intent.search_query:
        sq = intent.search_query.lower()
        if sq in name_lower:
            score += 30                 # Full phrase match in name
        else:
            # Partial: check each meaningful word individually
            for word in sq.split():
                if len(word) > 3 and re.search(rf"\b{re.escape(word)}\b", name_lower):
                    score += 8

    # ── Requirements ──────────────────────────────────────────────────────────
    for req in intent.requirements:
        req_lower = req.lower()
        if len(req_lower) > 3 and req_lower in text:
            score += 8

    # ── Preferences (soft — only affect ranking, never exclude) ───────────────
    for pref in intent.preferences:
        pref_lower = pref.lower()
        if len(pref_lower) > 3 and pref_lower in text:
            score += 3

    return score


# ===========================================================================
# Public API
# ===========================================================================

def find_matching_products(
    intent: BuyerIntent,
    merchant: Optional["Merchant"] = None,
) -> list["Product"]:
    """
    Return a relevance-ranked list of candidate Products for the given intent.

    Hard filters are applied at the database level (ORM).
    Relevance scoring and type-mismatch exclusion are applied in Python.

    Parameters
    ----------
    intent : BuyerIntent
        Structured buyer intent from extract_intent().

    Returns
    -------
    list[Product]
        Products ordered by relevance score (desc) then price (asc).
        Empty list if no products pass all filters.
    """
    # Import here to avoid circular imports (ai ↔ products).
    from products.models import Product

    # ── Phase 1: Hard database filters ───────────────────────────────────────
    qs = (
        Product.objects.select_related("merchant")
        .filter(is_active=True, inventory_quantity__gt=0)
    )

    if merchant is not None:
        qs = qs.filter(merchant=merchant)

    if intent.category:
        qs = qs.filter(category__iexact=intent.category)

    if intent.budget_max is not None:
        qs = qs.filter(price__lte=float(intent.budget_max) / 0.85)

    if intent.budget_min is not None:
        qs = qs.filter(price__gte=intent.budget_min)

    # Text-search fallback only when no category was detected
    if intent.search_query and not intent.category:
        qs = qs.filter(
            Q(name__icontains=intent.search_query)
            | Q(description__icontains=intent.search_query)
        )

    candidates = list(qs)

    if not candidates:
        return []

    # ── Phase 2: Relevance scoring ────────────────────────────────────────────
    scored: list[tuple[Product, int]] = [
        (product, get_product_relevance_score(product, intent))
        for product in candidates
    ]

    # When a specific product type is requested, exclude type-mismatched results
    # (those with a negative score from the -80 product-type penalty).
    if intent.product_type:
        positive = [(p, s) for p, s in scored if s >= 0]
        if positive:
            scored = positive
        # If ALL products scored negative → return empty (catalog has no match)
        else:
            return []

    # ── Sort: relevance desc, price asc ──────────────────────────────────────
    scored.sort(key=lambda x: (-x[1], x[0].price))

    return [product for product, _ in scored]
