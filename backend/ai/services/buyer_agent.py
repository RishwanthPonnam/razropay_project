"""
ai/services/buyer_agent.py
────────────────────────
Autonomous AI Buyer Agent Orchestration Service.

Manages BuyerAgentProfile creation, BuyerNegotiationSession state machine,
event logging, and calls buyer_decision_engine.py to evaluate merchant offers.
"""

from decimal import Decimal
from typing import Dict, Any, Optional

from django.db import transaction

from merchants.models import Merchant
from products.models import Product

from ai.models import (
    BuyerAgentProfile,
    BuyerNegotiationSession,
    BuyerNegotiationEvent
)
from ai.services.buyer_decision_engine import BuyerDecisionEngine


class InvalidBuyerStateTransitionError(ValueError):
    """Raised when an illegal buyer state transition is attempted."""
    pass


class BuyerAgent:
    """
    Autonomous AI Buyer Agent Service.
    """

    ALLOWED_TRANSITIONS = {
        BuyerNegotiationSession.STATUS_ACTIVE: {
            BuyerNegotiationSession.STATUS_OFFERED,
            BuyerNegotiationSession.STATUS_COUNTER_OFFERED,
            BuyerNegotiationSession.STATUS_ACCEPTED,
            BuyerNegotiationSession.STATUS_REJECTED,
            BuyerNegotiationSession.STATUS_EXPIRED
        },
        BuyerNegotiationSession.STATUS_OFFERED: {
            BuyerNegotiationSession.STATUS_OFFERED,
            BuyerNegotiationSession.STATUS_COUNTER_OFFERED,
            BuyerNegotiationSession.STATUS_ACCEPTED,
            BuyerNegotiationSession.STATUS_REJECTED,
            BuyerNegotiationSession.STATUS_EXPIRED
        },
        BuyerNegotiationSession.STATUS_COUNTER_OFFERED: {
            BuyerNegotiationSession.STATUS_OFFERED,
            BuyerNegotiationSession.STATUS_COUNTER_OFFERED,
            BuyerNegotiationSession.STATUS_ACCEPTED,
            BuyerNegotiationSession.STATUS_REJECTED,
            BuyerNegotiationSession.STATUS_EXPIRED
        },
        BuyerNegotiationSession.STATUS_ACCEPTED: set(),  # Terminal state
        BuyerNegotiationSession.STATUS_REJECTED: set(),  # Terminal state
        BuyerNegotiationSession.STATUS_EXPIRED: set(),   # Terminal state
    }

    @staticmethod
    def create_profile(
        buyer_session_id: str,
        name: str = "AI Buyer",
        requirements: Optional[list] = None,
        budget_min: Decimal = Decimal('0.00'),
        budget_max: Decimal = Decimal('10000.00'),
        preferred_price: Decimal = Decimal('5000.00'),
        maximum_price: Decimal = Decimal('7000.00'),
        walk_away_price: Decimal = Decimal('7000.00'),
        preferences: Optional[list] = None,
        negotiation_enabled: bool = True,
        maximum_negotiation_rounds: int = 3,
        strategy: str = BuyerAgentProfile.STRATEGY_BALANCED
    ) -> BuyerAgentProfile:
        """
        Create a new persistent BuyerAgentProfile.
        """
        profile = BuyerAgentProfile(
            buyer_session_id=buyer_session_id,
            name=name,
            requirements=requirements or [],
            budget_min=budget_min,
            budget_max=budget_max,
            preferred_price=preferred_price,
            maximum_price=maximum_price,
            walk_away_price=walk_away_price,
            preferences=preferences or [],
            negotiation_enabled=negotiation_enabled,
            maximum_negotiation_rounds=maximum_negotiation_rounds,
            strategy=strategy
        )
        profile.save()
        return profile

    @staticmethod
    def create_session(
        buyer_profile_id: str,
        merchant_id: int
    ) -> BuyerNegotiationSession:
        """
        Create a new BuyerNegotiationSession.
        """
        profile = BuyerAgentProfile.objects.get(pk=buyer_profile_id)
        merchant = Merchant.objects.get(pk=merchant_id)

        session = BuyerNegotiationSession.objects.create(
            buyer_profile=profile,
            merchant=merchant,
            status=BuyerNegotiationSession.STATUS_ACTIVE,
            negotiation_round=0
        )

        BuyerNegotiationEvent.objects.create(
            session=session,
            event_type=BuyerNegotiationEvent.EVENT_SYSTEM_EVENT,
            actor=BuyerNegotiationEvent.ACTOR_SYSTEM,
            message=f"Buyer negotiation session created for profile '{profile.name}' against merchant '{merchant.business_name}'."
        )

        return session

    @staticmethod
    def validate_transition(current_status: str, new_status: str) -> None:
        """
        Validate state transition allowed paths.
        """
        if current_status == new_status:
            return

        allowed = BuyerAgent.ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise InvalidBuyerStateTransitionError(
                f"Cannot transition buyer session from '{current_status}' to '{new_status}'."
            )

    @classmethod
    @transaction.atomic
    def evaluate_merchant_offer(
        cls,
        session: BuyerNegotiationSession,
        product: Product,
        merchant_offer: Decimal
    ) -> Dict[str, Any]:
        """
        Evaluate a merchant offer for a product in a buyer session.
        """
        # Guard terminal states
        if session.status in {
            BuyerNegotiationSession.STATUS_ACCEPTED,
            BuyerNegotiationSession.STATUS_REJECTED,
            BuyerNegotiationSession.STATUS_EXPIRED
        }:
            return {
                "session_id": str(session.id),
                "status": session.status,
                "message": f"Buyer session is already {session.status.lower()}. No further evaluation allowed.",
                "decision": "TERMINAL_STATE",
                "agreed_price": str(session.agreed_price) if session.agreed_price else None,
                "buyer_counter_offer": str(session.buyer_last_offer) if session.buyer_last_offer else None,
                "payment_ready": (session.status == BuyerNegotiationSession.STATUS_ACCEPTED),
                "negotiation_round": session.negotiation_round,
                "reason": f"Session reached terminal state '{session.status}'."
            }

        profile = session.buyer_profile

        # Log MERCHANT_OFFER event
        BuyerNegotiationEvent.objects.create(
            session=session,
            event_type=BuyerNegotiationEvent.EVENT_MERCHANT_OFFER,
            actor=BuyerNegotiationEvent.ACTOR_MERCHANT,
            message=f"Merchant offered '{product.name}' for ₹{merchant_offer:.2f}.",
            offered_price=merchant_offer
        )

        eval_res = BuyerDecisionEngine.evaluate_offer(
            product=product,
            merchant_offer=merchant_offer,
            buyer_profile=profile,
            current_round=session.negotiation_round
        )

        decision = eval_res['decision']
        session.product = product
        session.current_offer = merchant_offer

        if decision == 'ACCEPT':
            cls.validate_transition(session.status, BuyerNegotiationSession.STATUS_ACCEPTED)
            session.status = BuyerNegotiationSession.STATUS_ACCEPTED
            session.agreed_price = eval_res['agreed_price']
            session.save()

            BuyerNegotiationEvent.objects.create(
                session=session,
                event_type=BuyerNegotiationEvent.EVENT_ACCEPTANCE,
                actor=BuyerNegotiationEvent.ACTOR_BUYER,
                message=f"Buyer accepted merchant offer of ₹{merchant_offer:.2f} for '{product.name}'.",
                offered_price=merchant_offer,
                decision='ACCEPT',
                metadata={'payment_ready': True, 'signals': eval_res['signals']}
            )

            return {
                "session_id": str(session.id),
                "status": BuyerNegotiationSession.STATUS_ACCEPTED,
                "decision": "ACCEPT",
                "buyer_counter_offer": None,
                "agreed_price": str(eval_res['agreed_price']),
                "payment_ready": True,
                "negotiation_round": session.negotiation_round,
                "reason": eval_res['reason'],
                "signals": eval_res['signals'],
                "decision_trace": eval_res['decision_trace']
            }

        elif decision == 'COUNTER':
            session.negotiation_round += 1
            cls.validate_transition(session.status, BuyerNegotiationSession.STATUS_COUNTER_OFFERED)
            session.status = BuyerNegotiationSession.STATUS_COUNTER_OFFERED
            session.buyer_last_offer = eval_res['counter_offer']
            session.save()

            counter_price = eval_res['counter_offer']
            BuyerNegotiationEvent.objects.create(
                session=session,
                event_type=BuyerNegotiationEvent.EVENT_COUNTER_OFFER,
                actor=BuyerNegotiationEvent.ACTOR_BUYER,
                message=f"Buyer counter-offered ₹{counter_price:.2f} for '{product.name}'.",
                offered_price=counter_price,
                decision='COUNTER',
                metadata={'signals': eval_res['signals']}
            )

            return {
                "session_id": str(session.id),
                "status": BuyerNegotiationSession.STATUS_COUNTER_OFFERED,
                "decision": "COUNTER",
                "buyer_counter_offer": str(counter_price),
                "agreed_price": None,
                "payment_ready": False,
                "negotiation_round": session.negotiation_round,
                "reason": eval_res['reason'],
                "signals": eval_res['signals'],
                "decision_trace": eval_res['decision_trace']
            }

        else:  # REJECT
            cls.validate_transition(session.status, BuyerNegotiationSession.STATUS_REJECTED)
            session.status = BuyerNegotiationSession.STATUS_REJECTED
            session.save()

            customer_msg = eval_res.get('customer_message') or eval_res['reason']
            BuyerNegotiationEvent.objects.create(
                session=session,
                event_type=BuyerNegotiationEvent.EVENT_REJECTION,
                actor=BuyerNegotiationEvent.ACTOR_BUYER,
                message=customer_msg,
                offered_price=merchant_offer,
                decision='REJECT',
                metadata={'signals': eval_res['signals'], 'internal_reason': eval_res['reason']}
            )

            return {
                "session_id": str(session.id),
                "status": BuyerNegotiationSession.STATUS_REJECTED,
                "decision": "REJECT",
                "buyer_counter_offer": None,
                "agreed_price": None,
                "payment_ready": False,
                "negotiation_round": session.negotiation_round,
                "reason": eval_res['reason'],
                "customer_message": customer_msg,
                "message": customer_msg,
                "signals": eval_res['signals'],
                "decision_trace": eval_res['decision_trace']
            }

