"""
ai/services/buyer_decision_engine.py
───────────────────────────────────
Buyer-side Economic Decision Engine.

Evaluates merchant product offers against a BuyerAgentProfile's budget,
preferred/maximum/walk-away prices, strategy modes, hard constraints,
and negotiation round limits.

Produces deterministic decisions (ACCEPT, COUNTER, REJECT, HOLD) along with
signals metadata and explainable decision traces.
"""

from decimal import Decimal
import re
from typing import Dict, Any, Optional, Tuple, List


def validate_product_requirements(
    product: Any,
    buyer_profile: Any
) -> Tuple[bool, str]:
    """
    Validate if product meets the buyer's hard requirements.

    Requirements can contain product category names or required keywords.
    """
    if not buyer_profile.requirements:
        return True, "No specific product requirements set."

    prod_name = (product.name or "").lower()
    prod_desc = (product.description or "").lower()
    prod_cat = (product.category or "").lower()
    full_text = f"{prod_name} {prod_desc} {prod_cat}"

    # Check each requirement
    for req in buyer_profile.requirements:
        req_clean = req.lower().strip()
        if not req_clean:
            continue
        
        # Check if requirement matches category or appears in product text
        if req_clean in prod_cat or req_clean in full_text:
            continue

        # Check individual words in requirement
        req_words = [w for w in re.sub(r'[^\w\s]', '', req_clean).split() if len(w) > 2]
        if req_words and not any(w in full_text for w in req_words):
            return False, f"Product '{product.name}' does not meet hard requirement '{req}'."

    return True, "Product satisfies all buyer requirements."


def calculate_buyer_counter_offer(
    merchant_offer: Decimal,
    buyer_profile: Any,
    current_round: int
) -> Decimal:
    """
    Calculate deterministic buyer counter-offer price.

    Formula:
      counter = preferred_price + alpha * (merchant_offer - preferred_price)

    Alpha values by strategy:
      - VALUE_SEEKER: 0.30 (aggressive counter closer to preferred price)
      - BALANCED: 0.50 (midpoint counter)
      - FAST_BUYER: 0.70 (conceding counter closer to merchant offer)

    Clamped to: preferred_price <= counter < merchant_offer and <= maximum_price.
    """
    preferred = Decimal(str(buyer_profile.preferred_price))
    maximum = Decimal(str(buyer_profile.maximum_price))
    strategy = buyer_profile.strategy

    if strategy == 'VALUE_SEEKER':
        alpha = Decimal('0.30')
    elif strategy == 'FAST_BUYER':
        alpha = Decimal('0.70')
    else:  # BALANCED
        alpha = Decimal('0.50')

    # Distance stepping
    diff = merchant_offer - preferred
    counter = preferred + (alpha * diff)
    counter = counter.quantize(Decimal('0.01'))

    # Clamping guards
    if counter >= merchant_offer:
        counter = merchant_offer - Decimal('1.00')

    counter = max(preferred, min(counter, maximum))
    return counter.quantize(Decimal('0.01'))


def calculate_buyer_signals(
    product: Any,
    merchant_offer: Decimal,
    buyer_profile: Any
) -> Dict[str, int]:
    """
    Computes deterministic buyer decision signals (0 to 100).
    """
    preferred = Decimal(str(buyer_profile.preferred_price))
    maximum = Decimal(str(buyer_profile.maximum_price))
    walk_away = Decimal(str(buyer_profile.walk_away_price))
    budget_max = Decimal(str(buyer_profile.budget_max))

    # 1. Price attractiveness
    if merchant_offer <= preferred:
        price_attr = 100
    elif merchant_offer >= walk_away:
        price_attr = 0
    else:
        # Linear scaling between preferred (100) and walk_away (0)
        span = walk_away - preferred
        if span > 0:
            ratio = (walk_away - merchant_offer) / span
            price_attr = int(ratio * Decimal('100'))
        else:
            price_attr = 50

    # 2. Budget fit
    if merchant_offer <= budget_max:
        budget_fit = 100
    else:
        budget_fit = 0

    # 3. Requirement match
    is_req_met, _ = validate_product_requirements(product, buyer_profile)
    req_match = 100 if is_req_met else 0

    # 4. Preference match
    pref_match = 50
    if buyer_profile.preferences and product:
        full_text = f"{(product.name or '')} {(product.description or '')}".lower()
        matched = sum(1 for pref in buyer_profile.preferences if pref.lower() in full_text)
        total = len(buyer_profile.preferences)
        if total > 0:
            pref_match = int((matched / total) * 100)

    # 5. Walk-away safety
    if merchant_offer <= maximum:
        walk_away_safety = 100
    elif merchant_offer <= walk_away:
        walk_away_safety = 50
    else:
        walk_away_safety = 0

    return {
        "price_attractiveness": max(0, min(100, price_attr)),
        "budget_fit": budget_fit,
        "requirement_match": req_match,
        "preference_match": pref_match,
        "walk_away_safety": walk_away_safety
    }


class BuyerDecisionEngine:
    """
    Buyer-side Economic Decision Engine.
    """

    @staticmethod
    def evaluate_offer(
        product: Any,
        merchant_offer: Decimal,
        buyer_profile: Any,
        current_round: int
    ) -> Dict[str, Any]:
        """
        Evaluates a merchant offer against buyer profile constraints and strategy.

        Returns dict:
        - decision: 'ACCEPT' | 'COUNTER' | 'REJECT' | 'HOLD'
        - counter_offer: Decimal or None
        - agreed_price: Decimal or None
        - reason: str
        - signals: dict
        - decision_trace: dict
        """
        preferred = Decimal(str(buyer_profile.preferred_price))
        maximum = Decimal(str(buyer_profile.maximum_price))
        walk_away = Decimal(str(buyer_profile.walk_away_price))
        max_rounds = int(buyer_profile.maximum_negotiation_rounds)
        strategy = buyer_profile.strategy

        signals = calculate_buyer_signals(product, merchant_offer, buyer_profile)

        # 1. Product requirement validation
        req_met, req_reason = validate_product_requirements(product, buyer_profile)
        if not req_met:
            customer_message = "Thank you for the offer, but this product does not meet my required specifications."
            trace = {
                "agent": "AI_BUYER",
                "decision": "REJECT",
                "merchant_offer": str(merchant_offer),
                "preferred_price": str(preferred),
                "maximum_price": str(maximum),
                "walk_away_price": str(walk_away),
                "negotiation_round": current_round,
                "policy_validated": False,
                "reason": req_reason,
                "customer_message": customer_message,
                "signals": signals
            }
            return {
                "decision": "REJECT",
                "counter_offer": None,
                "agreed_price": None,
                "reason": req_reason,
                "customer_message": customer_message,
                "message": customer_message,
                "signals": signals,
                "decision_trace": trace
            }

        # 2. Walk-away price validation (IMMEDIATE REJECT)
        if merchant_offer > walk_away:
            reason = f"Merchant offer ₹{merchant_offer:.2f} exceeds walk-away price ₹{walk_away:.2f}."
            customer_message = (
                f"Sorry! ₹{merchant_offer:,.2f} is our best and final price. "
                f"We've already applied the maximum discount we can offer. "
                f"If this doesn't fit your budget, we completely understand."
            )
            trace = {
                "agent": "AI_BUYER",
                "decision": "REJECT",
                "merchant_offer": str(merchant_offer),
                "preferred_price": str(preferred),
                "maximum_price": str(maximum),
                "walk_away_price": str(walk_away),
                "negotiation_round": current_round,
                "policy_validated": False,
                "reason": reason,
                "customer_message": customer_message,
                "signals": signals
            }
            return {
                "decision": "REJECT",
                "counter_offer": None,
                "agreed_price": None,
                "reason": reason,
                "customer_message": customer_message,
                "message": customer_message,
                "signals": signals,
                "decision_trace": trace
            }

        # 3. Direct Acceptance if offer <= preferred price
        if merchant_offer <= preferred:
            reason = f"Merchant offer ₹{merchant_offer:.2f} is at or below preferred price ₹{preferred:.2f}."
            trace = {
                "agent": "AI_BUYER",
                "decision": "ACCEPT",
                "merchant_offer": str(merchant_offer),
                "preferred_price": str(preferred),
                "maximum_price": str(maximum),
                "walk_away_price": str(walk_away),
                "negotiation_round": current_round,
                "policy_validated": True,
                "reason": reason,
                "signals": signals
            }
            return {
                "decision": "ACCEPT",
                "counter_offer": None,
                "agreed_price": merchant_offer,
                "reason": reason,
                "signals": signals,
                "decision_trace": trace
            }

        # 3. Evaluate negotiation capability & strategy
        next_round = current_round + 1
        can_counter = buyer_profile.negotiation_enabled and (next_round <= max_rounds)

        if merchant_offer <= maximum:
            if strategy == 'FAST_BUYER':
                reason = f"Fast Buyer strategy accepted offer ₹{merchant_offer:.2f} (within maximum price ₹{maximum:.2f})."
                trace = {
                    "agent": "AI_BUYER",
                    "decision": "ACCEPT",
                    "merchant_offer": str(merchant_offer),
                    "preferred_price": str(preferred),
                    "maximum_price": str(maximum),
                    "walk_away_price": str(walk_away),
                    "negotiation_round": current_round,
                    "policy_validated": True,
                    "reason": reason,
                    "signals": signals
                }
                return {
                    "decision": "ACCEPT",
                    "counter_offer": None,
                    "agreed_price": merchant_offer,
                    "reason": reason,
                    "signals": signals,
                    "decision_trace": trace
                }

            elif strategy == 'BALANCED':
                # Accept if within lower half of preferred..maximum span OR if rounds exhausted
                midpoint = preferred + (Decimal('0.50') * (maximum - preferred))
                if merchant_offer <= midpoint or not can_counter:
                    reason = f"Balanced strategy accepted offer ₹{merchant_offer:.2f} (within price threshold)."
                    trace = {
                        "agent": "AI_BUYER",
                        "decision": "ACCEPT",
                        "merchant_offer": str(merchant_offer),
                        "preferred_price": str(preferred),
                        "maximum_price": str(maximum),
                        "walk_away_price": str(walk_away),
                        "negotiation_round": current_round,
                        "policy_validated": True,
                        "reason": reason,
                        "signals": signals
                    }
                    return {
                        "decision": "ACCEPT",
                        "counter_offer": None,
                        "agreed_price": merchant_offer,
                        "reason": reason,
                        "signals": signals,
                        "decision_trace": trace
                    }

            elif strategy == 'VALUE_SEEKER':
                if not can_counter:
                    reason = f"Value Seeker strategy accepted offer ₹{merchant_offer:.2f} after max negotiation rounds reached."
                    trace = {
                        "agent": "AI_BUYER",
                        "decision": "ACCEPT",
                        "merchant_offer": str(merchant_offer),
                        "preferred_price": str(preferred),
                        "maximum_price": str(maximum),
                        "walk_away_price": str(walk_away),
                        "negotiation_round": current_round,
                        "policy_validated": True,
                        "reason": reason,
                        "signals": signals
                    }
                    return {
                        "decision": "ACCEPT",
                        "counter_offer": None,
                        "agreed_price": merchant_offer,
                        "reason": reason,
                        "signals": signals,
                        "decision_trace": trace
                    }

        # 4. If offer > maximum or strategy demands counteroffer, and we can counter
        if can_counter:
            counter_price = calculate_buyer_counter_offer(
                merchant_offer=merchant_offer,
                buyer_profile=buyer_profile,
                current_round=current_round
            )
            reason = f"Offer ₹{merchant_offer:.2f} is above preferred price ₹{preferred:.2f}. Counter-offering ₹{counter_price:.2f}."
            trace = {
                "agent": "AI_BUYER",
                "decision": "COUNTER",
                "merchant_offer": str(merchant_offer),
                "buyer_counter_offer": str(counter_price),
                "preferred_price": str(preferred),
                "maximum_price": str(maximum),
                "walk_away_price": str(walk_away),
                "negotiation_round": next_round,
                "policy_validated": True,
                "reason": reason,
                "signals": signals
            }
            return {
                "decision": "COUNTER",
                "counter_offer": counter_price,
                "agreed_price": None,
                "reason": reason,
                "signals": signals,
                "decision_trace": trace
            }

        # 5. Rounds exhausted and offer <= walk_away -> ACCEPT, else REJECT
        if merchant_offer <= walk_away:
            reason = f"Accepted merchant final offer ₹{merchant_offer:.2f} (within walk-away ceiling ₹{walk_away:.2f})."
            trace = {
                "agent": "AI_BUYER",
                "decision": "ACCEPT",
                "merchant_offer": str(merchant_offer),
                "preferred_price": str(preferred),
                "maximum_price": str(maximum),
                "walk_away_price": str(walk_away),
                "negotiation_round": current_round,
                "policy_validated": True,
                "reason": reason,
                "signals": signals
            }
            return {
                "decision": "ACCEPT",
                "counter_offer": None,
                "agreed_price": merchant_offer,
                "reason": reason,
                "signals": signals,
                "decision_trace": trace
            }

        # Offer strictly exceeds walk_away price and no more rounds left -> REJECT
        reason = f"Offer ₹{merchant_offer:.2f} exceeds walk-away price ₹{walk_away:.2f}."
        customer_message = (
            f"Sorry! ₹{merchant_offer:,.2f} is our best and final price. "
            f"We've already applied the maximum discount we can offer. "
            f"If this doesn't fit your budget, we completely understand."
        )
        trace = {
            "agent": "AI_BUYER",
            "decision": "REJECT",
            "merchant_offer": str(merchant_offer),
            "preferred_price": str(preferred),
            "maximum_price": str(maximum),
            "walk_away_price": str(walk_away),
            "negotiation_round": current_round,
            "policy_validated": False,
            "reason": reason,
            "customer_message": customer_message,
            "signals": signals
        }
        return {
            "decision": "REJECT",
            "counter_offer": None,
            "agreed_price": None,
            "reason": reason,
            "customer_message": customer_message,
            "message": customer_message,
            "signals": signals,
            "decision_trace": trace
        }
