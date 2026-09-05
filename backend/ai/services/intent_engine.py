"""
ai/services/intent_engine.py
────────────────────────────
Converts natural-language buyer messages into a structured BuyerIntent.

ARCHITECTURE CONTRACT
─────────────────────
The public API is:

    intent = extract_intent(user_message: str) -> BuyerIntent

This contract is intentionally stable.  The current implementation is
deterministic (regex + keyword rules).  A future implementation can swap
the body of extract_intent() for an LLM call — all downstream code
(product_matcher, views, tests) continues to work unchanged because they
only consume the BuyerIntent dataclass.

Do NOT add LLM/external-API calls here yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ===========================================================================
# Data structures
# ===========================================================================


@dataclass
class BuyerIntent:
    """
    Structured representation of a buyer's purchase intent.

    Fields
    ------
    intent_type          : "purchase" | "browse" | "compare"
    category             : detected product category (matches Product.category)
    product_type         : canonical product-type keyword (e.g. "keyboard", "mouse",
                           "headphone").  Used by the matcher for type-aware scoring.
    search_query         : core product phrase extracted from the message
    budget_min           : lower price bound in INR (None = no lower bound)
    budget_max           : upper price bound in INR (None = no upper bound)
    use_case             : detected use-case string ("FPS gaming", "work", …)
    requirements         : list of must-have features / product type
    hard_constraints     : machine-readable constraint strings ("budget <= 4500")
    preferences          : list of nice-to-have features
    urgency              : "urgent" | "flexible" | None
    quantity             : number of units requested (default 1)
    """

    intent_type: str = "purchase"
    category: Optional[str] = None
    product_type: Optional[str] = None
    search_query: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    preferred_price: Optional[float] = None
    use_case: Optional[str] = None
    requirements: list[str] = field(default_factory=list)
    hard_constraints: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    urgency: Optional[str] = None
    quantity: int = 1

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON responses."""
        return {
            "intent_type": self.intent_type,
            "category": self.category,
            "product_type": self.product_type,
            "search_query": self.search_query,
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "preferred_price": self.preferred_price,
            "use_case": self.use_case,
            "requirements": self.requirements,
            "hard_constraints": self.hard_constraints,
            "preferences": self.preferences,
            "urgency": self.urgency,
            "quantity": self.quantity,
        }


# ===========================================================================
# Internal lookup tables
# ===========================================================================

# Maps product-type keywords → Product.category values.
# Order matters: more specific entries come first.
_PRODUCT_TYPE_TO_CATEGORY: list[tuple[str, str]] = [
    # Audio
    ("headset",    "Audio"),
    ("headphone",  "Audio"),
    ("headphones", "Audio"),
    ("earphone",   "Audio"),
    ("earphones",  "Audio"),
    ("earbud",     "Audio"),
    ("earbuds",    "Audio"),
    ("speaker",    "Audio"),
    ("speakers",   "Audio"),
    # Gaming peripherals
    ("keyboard",   "Gaming"),
    ("keyboards",  "Gaming"),
    ("mouse",      "Gaming"),
    ("mice",       "Gaming"),   # plural of mouse (computing)
    ("gamepad",    "Gaming"),
    ("controller", "Gaming"),
    # Monitors
    ("monitor",    "Monitors"),
    ("monitors",   "Monitors"),
    ("display",    "Monitors"),
    ("screen",     "Monitors"),
    # Laptops
    ("laptop",     "Laptops"),
    ("laptops",    "Laptops"),
    ("notebook",   "Laptops"),
]

# Normalise plural/variant spellings to a canonical product word for the
# search_query so downstream text search is more reliable.
_KEYWORD_NORMALISE: dict[str, str] = {
    "headphones": "headphone",
    "earphones":  "earphone",
    "earbuds":    "earbud",
    "speakers":   "speaker",
    "keyboards":  "keyboard",
    "mice":       "mouse",
    "monitors":   "monitor",
    "laptops":    "laptop",
}

# Words we do NOT want to carry into the search_query prefix slot.
_STOPWORDS: frozenset[str] = frozenset({
    "i", "need", "a", "an", "the", "some", "good", "want", "looking",
    "for", "with", "me", "something", "show", "find", "get", "buy",
    "purchase", "anything", "what", "which", "please", "can", "you",
    "do", "have", "is", "are", "one", "give", "recommend", "suggest",
    "tell", "about", "any", "suitable", "decent", "nice", "just",
    "really", "very", "quite",
})

# Budget extraction patterns — ordered from most-specific to least-specific.
# Each entry: (regex_pattern, kind)  kind ∈ {"max", "min", "range"}
_BUDGET_PATTERNS: list[tuple[str, str]] = [
    # Range: "between 3000 and 5000"
    (
        r"\bbetween\s+(?:₹\s*|rs\.?\s*|inr\s*)?"
        r"([\d,]+(?:\.\d+)?[kK]?)"
        r"\s+and\s+(?:₹\s*|rs\.?\s*|inr\s*)?"
        r"([\d,]+(?:\.\d+)?[kK]?)\b",
        "range",
    ),
    # Upper bound: under / below / less than / no more than / within /
    #              max / maximum / up to / upto / at most
    (
        r"\b(?:under|below|less\s+than|no\s+more\s+than|within|"
        r"max(?:imum)?|up\s+to|upto|at\s+most)\s+"
        r"(?:₹\s*|rs\.?\s*|inr\s*)?"
        r"([\d,]+(?:\.\d+)?[kK]?)\b",
        "max",
    ),
    # Explicit budget mention: "budget of 5000", "budget is 5000"
    (
        r"\bbudget\s+(?:is\s+|of\s+|around\s+|about\s+)?"
        r"(?:₹\s*|rs\.?\s*|inr\s*)?"
        r"([\d,]+(?:\.\d+)?[kK]?)\b",
        "max",
    ),
    # Lower bound: above / over / more than / at least
    (
        r"\b(?:above|over|more\s+than|at\s+least)\s+"
        r"(?:₹\s*|rs\.?\s*|inr\s*)?"
        r"([\d,]+(?:\.\d+)?[kK]?)\b",
        "min",
    ),
]

# Preferred price extraction patterns — look for explicit target prices
_PREFERRED_PRICE_PATTERNS: list[tuple[str, str]] = [
    (
        r"\b(?:around|about|approximately|~)\s+(?:₹\s*|rs\.?\s*|inr\s*)?([\d,]+(?:\.\d+)?[kK]?)\b",
        "preferred",
    ),
    (
        r"\bpay\s+(?:around|about|approximately|~)?\s*(?:₹\s*|rs\.?\s*|inr\s*)?([\d,]+(?:\.\d+)?[kK]?)\b",
        "preferred",
    ),
]

_USE_CASE_PATTERNS: list[tuple[str, str]] = [
    (r"\bfor\s+(?:competitive|pro(?:fessional)?)\s+gaming\b", "competitive gaming"),
    (r"\bfor\s+fps\s+(?:games?|gaming)?\b",                   "FPS gaming"),
    (r"\bfor\s+(?:moba|battle\s*royale)\b",                   "MOBA / battle royale"),
    (r"\bfor\s+(?:gaming|games?)\b",                          "gaming"),
    (r"\bfor\s+(?:work|office|professional)\b",               "work / productivity"),
    (r"\bfor\s+(?:music|listening)\b",                        "music listening"),
    (r"\bfor\s+(?:streaming|content\s+creation)\b",           "streaming / content creation"),
    (r"\bfor\s+(?:coding|programming|development)\b",          "coding / development"),
    (r"\bfor\s+(?:studying|study|students?)\b",               "studying"),
    (r"\bfor\s+(?:everyday|daily)\s+use\b",                   "everyday use"),
]

# Feature keywords that represent hard requirements (must-have).
_HARD_FEATURES: list[str] = [
    "microphone", "mic", "noise cancellation", "anc",
    "wireless", "wired", "bluetooth",
    "mechanical", "rgb", "backlit",
    "waterproof", "water resistant",
]

# Feature keywords that represent soft preferences (nice-to-have).
_SOFT_FEATURES: list[str] = [
    "portable", "lightweight", "durable", "comfortable",
    "long battery", "fast charging",
    "surround sound", "bass",
    "ergonomic", "slim", "thin", "premium",
    "high resolution", "4k",
]

# Spoken / written number words → integer.
_WORD_NUMBERS: dict[str, int] = {
    "two":   2, "three": 3, "four":  4, "five":  5,
    "six":   6, "seven": 7, "eight": 8, "nine":  9, "ten": 10,
}


# ===========================================================================
# Private helpers
# ===========================================================================


def _parse_amount(raw: str) -> float:
    """
    Parse a currency amount string to float.
    Handles: commas ("4,500"), k-suffix ("4.5k", "5K").
    """
    raw = raw.strip().replace(",", "")
    if raw.lower().endswith("k"):
        return float(raw[:-1]) * 1000.0
    return float(raw)


def _extract_budget(text_lower: str) -> tuple[Optional[float], Optional[float]]:
    """Return (budget_min, budget_max) from text. Both default to None."""
    for pattern, kind in _BUDGET_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            if kind == "range":
                return _parse_amount(m.group(1)), _parse_amount(m.group(2))
            if kind == "max":
                return None, _parse_amount(m.group(1))
            if kind == "min":
                return _parse_amount(m.group(1)), None
    return None, None

def _extract_preferred_price(text_lower: str) -> Optional[float]:
    """Extract an explicit preferred price if mentioned (e.g., "around ₹3400")."""
    for pattern, kind in _PREFERRED_PRICE_PATTERNS:
        m = re.search(pattern, text_lower)
        if m:
            return _parse_amount(m.group(1))
    return None

def _extract_quantity(text_lower: str) -> int:
    """
    Extract a numeric quantity from text.  Default is 1.
    Handles: "2 keyboards", "three gaming mice", etc.
    """
    # Numeric digit before a product-type word (with optional adjective)
    m = re.search(
        r"\b(\d+)\s+(?:\w+\s+)?"
        r"(?:keyboard|mouse|mice|headphone|headset|laptop|monitor|speaker|earbud)s?\b",
        text_lower,
    )
    if m:
        qty = int(m.group(1))
        if 1 <= qty <= 100:
            return qty

    # Written number word before a product-type word
    for word, num in _WORD_NUMBERS.items():
        if re.search(
            rf"\b{word}\s+(?:\w+\s+)?"
            r"(?:keyboard|mouse|mice|headphone|headset|laptop|monitor|speaker|earbud)s?\b",
            text_lower,
        ):
            return num

    return 1


def _extract_category_and_query(
    text_lower: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Detect the product-type keyword and map it to a Product.category value.
    Also constructs a human-readable search_query phrase (e.g. "gaming keyboard").

    Returns (category, search_query, product_type) where product_type is the
    canonical single-word product keyword (e.g. "keyboard", "mouse", "headphone").
    This is distinct from search_query which may include an adjective prefix.
    """
    words = text_lower.split()

    for keyword, category in _PRODUCT_TYPE_TO_CATEGORY:
        # Find the keyword as a whole word in the message.
        pattern = rf"\b{re.escape(keyword)}\b"
        if not re.search(pattern, text_lower):
            continue

        # Normalise plural/variant to canonical form.
        canonical = _KEYWORD_NORMALISE.get(keyword, keyword)

        # Try to prepend the immediately preceding non-stopword as an adjective
        # (e.g. "gaming" before "keyboard" → "gaming keyboard").
        try:
            idx = next(i for i, w in enumerate(words) if w == keyword)
        except StopIteration:
            return category, canonical, canonical

        prefix = ""
        if idx > 0:
            prev_word = re.sub(r"[^a-z]", "", words[idx - 1])
            if prev_word and prev_word not in _STOPWORDS and not prev_word.isdigit():
                prefix = prev_word + " "

        search_query = (prefix + canonical).strip()
        return category, search_query, canonical

    return None, None, None


def _extract_use_case(text_lower: str) -> Optional[str]:
    for pattern, label in _USE_CASE_PATTERNS:
        if re.search(pattern, text_lower):
            return label
    return None


def _extract_features(
    text_lower: str,
) -> tuple[list[str], list[str]]:
    """Return (requirements, preferences) based on feature keyword lists."""
    requirements: list[str] = []
    preferences: list[str] = []

    for feature in _HARD_FEATURES:
        # Multi-word features need a plain substring check; single words use \b.
        if " " in feature:
            if feature in text_lower:
                requirements.append(feature)
        elif re.search(rf"\b{re.escape(feature)}\b", text_lower):
            requirements.append(feature)

    for feature in _SOFT_FEATURES:
        if " " in feature:
            if feature in text_lower:
                preferences.append(feature)
        elif re.search(rf"\b{re.escape(feature)}\b", text_lower):
            preferences.append(feature)

    return requirements, preferences


def _build_hard_constraints(
    search_query: Optional[str],
    budget_min: Optional[float],
    budget_max: Optional[float],
) -> list[str]:
    constraints: list[str] = []
    if search_query:
        constraints.append(search_query)
    if budget_max is not None:
        constraints.append(f"budget <= {budget_max:.0f}")
    if budget_min is not None:
        constraints.append(f"budget >= {budget_min:.0f}")
    return constraints


# ===========================================================================
# Public API
# ===========================================================================


def extract_intent(user_message: str) -> BuyerIntent:
    """
    Convert a natural-language buyer message into a structured BuyerIntent.

    Parameters
    ----------
    user_message : str
        Raw buyer input (e.g. "I need a gaming headset under 4500").

    Returns
    -------
    BuyerIntent
        Structured intent.  All fields default to safe/empty values when
        nothing relevant is detected in the message.

    Notes
    -----
    This function is the STABLE CONTRACT for the intent pipeline.
    The current implementation is deterministic (no external calls).
    Future implementations may call an LLM inside this function — the
    signature and return type must not change.
    """
    if not user_message or not user_message.strip():
        # Return a default "browse" intent for empty input.
        return BuyerIntent(intent_type="browse")

    text_lower = user_message.lower().strip()

    # 1. Category, search query, and canonical product type ──────────────────
    category, search_query, product_type = _extract_category_and_query(text_lower)

    # 2. Budget ──────────────────────────────────────────────────────────────
    budget_min, budget_max = _extract_budget(text_lower)

    # 2b. Preferred price (optional) ────────────────────────────────────────
    preferred_price = _extract_preferred_price(text_lower)

    # 3. Quantity ────────────────────────────────────────────────────────────
    quantity = _extract_quantity(text_lower)

    # 4. Use case ────────────────────────────────────────────────────────────
    use_case = _extract_use_case(text_lower)

    # 5. Feature requirements / preferences ──────────────────────────────────
    requirements, preferences = _extract_features(text_lower)

    # Ensure the primary product type is always in requirements.
    if search_query and search_query not in requirements:
        requirements = [search_query] + requirements

    # Ensure the use-case is captured in preferences if not already.
    if use_case and use_case not in preferences:
        preferences.append(use_case)

    # 6. Hard constraints ────────────────────────────────────────────────────
    hard_constraints = _build_hard_constraints(search_query, budget_min, budget_max)

    return BuyerIntent(
        intent_type="purchase",
        category=category,
        product_type=product_type,
        search_query=search_query,
        budget_min=budget_min,
        budget_max=budget_max,
        preferred_price=preferred_price,
        use_case=use_case,
        requirements=requirements,
        hard_constraints=hard_constraints,
        preferences=preferences,
        urgency=None,
        quantity=quantity,
    )
