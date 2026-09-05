"""
ai/services/negotiation_engine.py
───────────────────────────────
Negotiation Engine for Bounded Autonomous Commerce Agent.

Determines whether the merchant agent should ACCEPT, COUNTER, REJECT, or HOLD
in response to buyer messages and offers, enforcing MerchantPolicy limits.
"""

from decimal import Decimal, InvalidOperation
import re
from typing import Dict, Any, Optional, Tuple


def extract_buyer_proposed_price(message: str) -> Optional[Decimal]:
    """
    Deterministically extract buyer proposed price from a message if context indicates
    a price/budget proposal.

    Supports:
    - ₹3500, ₹ 3,500, Rs 3500, Rs. 3500, INR 3500, 3500
    - Context keywords: "can you do", "budget is", "ill pay", "i'll pay", "give it for",
      "offer", "for 3500", "deal at", "discount to", "how about"
    """
    if not message:
        return None

    msg_clean = message.lower().strip()
    msg_no_punct = re.sub(r'[^\w\s₹]', '', msg_clean).strip()

    # Explicit currency prefix patterns (e.g. ₹3500, Rs 3500, INR 3,500)
    currency_patterns = [
        r'(?:₹|rs\.?|inr)\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]{1,2})?)',
    ]

    for pat in currency_patterns:
        match = re.search(pat, msg_clean)
        if match:
            raw_num = match.group(1).replace(',', '')
            try:
                val = Decimal(raw_num)
                if val > 0:
                    return val
            except InvalidOperation:
                pass

    # Contextual price proposal patterns (e.g. "can you do 3500", "budget is 3500", "3500 deal")
    context_patterns = [
        r'(?:can\s+you\s+do|could\s+you\s+do|how\s+about|i\'?ll\s+pay|my\s+budget\s+is|give\s+it\s+for|for|at|offer)\s+([0-9]+(?:,[0-9]+)*(?:\.[0-9]{1,2})?)',
        r'([0-9]+(?:,[0-9]+)*(?:\.[0-9]{1,2})?)\s*(?:deal|okay|fine|final|possible)',
    ]

    for pat in context_patterns:
        match = re.search(pat, msg_clean)
        if match:
            raw_num = match.group(1).replace(',', '')
            try:
                val = Decimal(raw_num)
                if val > 100:  # avoid small numbers like quantity "1" or "2"
                    return val
            except InvalidOperation:
                pass

    # Standalone number if message is short and looks like a price quote (e.g. "3500?")
    standalone_match = re.fullmatch(r'\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]{1,2})?)\s*', msg_no_punct)
    if standalone_match:
        raw_num = standalone_match.group(1).replace(',', '')
        try:
            val = Decimal(raw_num)
            if val > 100:
                return val
        except InvalidOperation:
            pass

    return None


def classify_buyer_message(message: str) -> str:
    """
    Classify buyer message type:
    - ACCEPTANCE
    - REJECTION
    - OFFER
    - REQUIREMENT_CHANGE
    - SEARCH
    """
    if not message:
        return 'SEARCH'

    msg_clean = message.lower().strip()
    msg_no_punct = re.sub(r'[^\w\s]', ' ', msg_clean)
    words = set(msg_no_punct.split())

    # Exact or keyword acceptance
    acceptance_phrases = [
        'okay', 'ok', 'yes', 'deal', 'accepted', 'accept', "i'll take it",
        "ill take it", "that's fine", "thats fine", 'sure', 'sounds good',
        'done', 'fine', 'i agree', 'agreed'
    ]
    
    # Simple rejection keywords
    rejection_keywords = [
        'no', 'too expensive', 'forget it', "i don't want it", "dont want it",
        'nah', 'cancel', 'pass', 'not interested', 'no thanks', 'too high'
    ]

    # Requirement change keywords
    req_change_keywords = [
        'instead', 'looking for', 'show me', 'want a', 'need a', 'search',
        'different', 'other'
    ]

    proposed_price = extract_buyer_proposed_price(message)
    if proposed_price is not None:
        return 'OFFER'

    # Check rejection first if negative words present
    if any(rk in msg_clean for rk in rejection_keywords):
        return 'REJECTION'

    # Check acceptance
    if any(w in words for w in ['okay', 'ok', 'yes', 'deal', 'accepted', 'accept', 'sure', 'fine', 'done', 'agreed']):
        return 'ACCEPTANCE'
    if any(ap in msg_clean for ap in acceptance_phrases):
        return 'ACCEPTANCE'

    # Check for requirement change vs search
    if any(rk in msg_clean for rk in req_change_keywords):
        return 'REQUIREMENT_CHANGE'

    return 'SEARCH'


class NegotiationEngine:
    """
    Bounded Negotiation Engine.
    Enforces MerchantPolicy constraints on buyer price offers.
    """

    @staticmethod
    def evaluate_offer(
        merchant_policy: Any,
        product: Any,
        buyer_proposed_price: Decimal,
        current_round: int,
        previous_merchant_offer: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Evaluates a buyer proposed price against MerchantPolicy and product cost/price.

        Returns dict with:
        - action: 'ACCEPT' | 'COUNTER' | 'REJECT'
        - agreed_price: Decimal or None
        - counter_price: Decimal or None
        - reason: str
        - is_policy_compliant: bool
        """
        catalog_price = Decimal(str(product.price))
        cost_price = Decimal(str(product.cost_price))
        max_discount_pct = Decimal(str(merchant_policy.maximum_discount_percent))
        min_margin_pct = Decimal(str(merchant_policy.minimum_margin_percent))
        max_rounds = int(merchant_policy.maximum_negotiation_rounds)

        # Calculate buyer proposal discount & margin
        if catalog_price > 0:
            discount_amount = catalog_price - buyer_proposed_price
            discount_pct = (discount_amount / catalog_price) * Decimal('100')
        else:
            discount_pct = Decimal('0')

        if buyer_proposed_price > 0:
            margin_amount = buyer_proposed_price - cost_price
            margin_pct = (margin_amount / buyer_proposed_price) * Decimal('100')
        else:
            margin_pct = Decimal('-100')

        # Check policy compliance of buyer proposal
        buyer_offer_compliant = (
            buyer_proposed_price >= cost_price and
            discount_pct <= max_discount_pct and
            margin_pct >= min_margin_pct
        )

        # 1. If buyer proposal is fully policy compliant -> ACCEPT!
        if buyer_offer_compliant:
            return {
                'action': 'ACCEPT',
                'agreed_price': buyer_proposed_price,
                'counter_price': None,
                'reason': f"Buyer offer of ₹{buyer_proposed_price:.2f} complies with merchant policy.",
                'is_policy_compliant': True,
                'metrics': {
                    'discount_pct': float(discount_pct),
                    'margin_pct': float(margin_pct)
                }
            }

        # 2. Buyer proposal violates policy -> Can we counter?
        next_round = current_round + 1
        if next_round > max_rounds:
            reason = f"Maximum negotiation rounds ({max_rounds}) reached. Offered price ₹{buyer_proposed_price:.2f} violates merchant policy."
            customer_msg = (
                f"Sorry! ₹{previous_merchant_offer:,.2f} is our best and final price. "
                f"We've already applied the maximum discount we can offer. "
                f"If this doesn't fit your budget, we completely understand."
            ) if previous_merchant_offer else "Sorry! We've reached the maximum negotiation rounds for this session."
            return {
                'action': 'REJECT',
                'agreed_price': None,
                'counter_price': None,
                'reason': reason,
                'customer_message': customer_msg,
                'is_policy_compliant': False,
                'metrics': {
                    'discount_pct': float(discount_pct),
                    'margin_pct': float(margin_pct)
                }
            }

        # Find best valid counteroffer price
        counter_price = NegotiationEngine.find_optimal_counter_price(
            catalog_price=catalog_price,
            cost_price=cost_price,
            max_discount_pct=max_discount_pct,
            min_margin_pct=min_margin_pct,
            buyer_proposed_price=buyer_proposed_price
        )

        # Enforce monotonic merchant concession: merchant never increases price after offering a lower one
        if counter_price is not None and previous_merchant_offer is not None:
            if counter_price > previous_merchant_offer:
                counter_price = previous_merchant_offer

        if counter_price is not None and counter_price > buyer_proposed_price:
            # Check policy compliance of counter_price
            c_discount = ((catalog_price - counter_price) / catalog_price) * Decimal('100')
            c_margin = ((counter_price - cost_price) / counter_price) * Decimal('100')
            return {
                'action': 'COUNTER',
                'agreed_price': None,
                'counter_price': counter_price,
                'reason': f"Buyer proposed price ₹{buyer_proposed_price:.2f} violates policy. Counter-offering best policy-compliant price ₹{counter_price:.2f}.",
                'is_policy_compliant': True,
                'metrics': {
                    'counter_discount_pct': float(c_discount),
                    'counter_margin_pct': float(c_margin)
                }
            }
        else:
            reason = f"Buyer offer of ₹{buyer_proposed_price:.2f} is below minimum allowed margin ({min_margin_pct}%). No valid counter-offer available."
            customer_msg = (
                f"Sorry! ₹{previous_merchant_offer:,.2f} is our best and final price. "
                f"We've already applied the maximum discount we can offer. "
                f"If this doesn't fit your budget, we completely understand."
            ) if previous_merchant_offer else f"Sorry! We are unable to meet an offer of ₹{buyer_proposed_price:,.2f} as that exceeds our maximum possible discount."
            return {
                'action': 'REJECT',
                'agreed_price': None,
                'counter_price': None,
                'reason': reason,
                'customer_message': customer_msg,
                'is_policy_compliant': False,
                'metrics': {
                    'discount_pct': float(discount_pct),
                    'margin_pct': float(margin_pct)
                }
            }

    @staticmethod
    def find_optimal_counter_price(
        catalog_price: Decimal,
        cost_price: Decimal,
        max_discount_pct: Decimal,
        min_margin_pct: Decimal,
        buyer_proposed_price: Decimal
    ) -> Optional[Decimal]:
        """
        Finds the lowest valid price between catalog_price and buyer_proposed_price that
        strictly satisfies both max_discount_pct and min_margin_pct.
        """
        # Price constraint from max discount:
        # P >= catalog_price * (1 - max_discount_pct / 100)
        min_price_by_discount = catalog_price * (Decimal('1') - (max_discount_pct / Decimal('100')))

        # Price constraint from min margin:
        # (P - cost_price) / P >= min_margin_pct / 100
        # P * (1 - min_margin_pct / 100) >= cost_price
        # P >= cost_price / (1 - min_margin_pct / 100)
        margin_factor = Decimal('1') - (min_margin_pct / Decimal('100'))
        if margin_factor <= 0:
            return None
        min_price_by_margin = cost_price / margin_factor

        lowest_allowed_price = max(min_price_by_discount, min_price_by_margin)

        # Round up to 2 decimal places to be safe
        lowest_allowed_price = lowest_allowed_price.quantize(Decimal('0.01'))

        if lowest_allowed_price > catalog_price:
            # If lowest allowed price is higher than catalog price (e.g. min margin requires > catalog),
            # catalog price itself cannot provide a valid discount; cap at catalog_price
            return catalog_price

        # Standard case: return lowest policy-compliant price
        return lowest_allowed_price
