"""
ai/services/agent_negotiation.py
───────────────────────────────
Orchestrator for Autonomous AI Buyer ↔ AI Merchant Commerce Negotiation.

Connects:
- BuyerAgent / BuyerDecisionEngine
- CommerceAgent / RevenueEngine / DecisionEngine / NegotiationEngine

Manages:
- AI-to-AI state machine (ACTIVE, BUYER_TURN, MERCHANT_TURN, AGREED, REJECTED, EXPIRED)
- Round definitions & effective round caps (min(buyer_max, merchant_max))
- Multi-step safety execution ceiling (max_steps) with pause & resume support
- Complete append-only audit event logging and machine-readable negotiation traces
"""

from decimal import Decimal
from typing import Dict, Any, Optional, List

from django.db import transaction

from merchants.models import Merchant, MerchantPolicy
from products.models import Product

from ai.models import (
    AgentNegotiation,
    AgentNegotiationEvent,
    BuyerAgentProfile
)
from ai.services.intent_engine import extract_intent
from ai.services.product_matcher import find_matching_products
from ai.services.revenue_engine import generate_opportunities
from ai.services.decision_engine import make_decision
from ai.services.negotiation_engine import NegotiationEngine
from ai.services.buyer_decision_engine import BuyerDecisionEngine


class InvalidNegotiationStateTransitionError(ValueError):
    """Raised when an illegal negotiation state machine transition is attempted."""
    pass


import json
import uuid as _uuid_module


def _json_safe(obj):
    """
    Recursively convert a structure to a JSON-serializable form.
    Decimal → str, UUID → str, others passed through.
    """
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, _uuid_module.UUID):
        return str(obj)
    return obj


class AgentNegotiationOrchestrator:
    """
    AI-to-AI Negotiation Orchestrator.
    """

    ALLOWED_TRANSITIONS = {
        AgentNegotiation.STATUS_ACTIVE: {
            AgentNegotiation.STATUS_BUYER_TURN,
            AgentNegotiation.STATUS_MERCHANT_TURN,
            AgentNegotiation.STATUS_AGREED,
            AgentNegotiation.STATUS_REJECTED,
            AgentNegotiation.STATUS_EXPIRED
        },
        AgentNegotiation.STATUS_BUYER_TURN: {
            AgentNegotiation.STATUS_MERCHANT_TURN,
            AgentNegotiation.STATUS_AGREED,
            AgentNegotiation.STATUS_REJECTED,
            AgentNegotiation.STATUS_EXPIRED
        },
        AgentNegotiation.STATUS_MERCHANT_TURN: {
            AgentNegotiation.STATUS_BUYER_TURN,
            AgentNegotiation.STATUS_AGREED,
            AgentNegotiation.STATUS_REJECTED,
            AgentNegotiation.STATUS_EXPIRED
        },
        AgentNegotiation.STATUS_AGREED: set(),    # Terminal state
        AgentNegotiation.STATUS_REJECTED: set(),  # Terminal state
        AgentNegotiation.STATUS_EXPIRED: set(),   # Terminal state
    }

    @staticmethod
    def validate_transition(current_status: str, new_status: str) -> None:
        if current_status == new_status:
            return
        allowed = AgentNegotiationOrchestrator.ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise InvalidNegotiationStateTransitionError(
                f"Cannot transition negotiation from '{current_status}' to '{new_status}'."
            )

    @classmethod
    @transaction.atomic
    def create_negotiation(
        cls,
        buyer_profile_id: str,
        merchant_id: int,
        product_id: Optional[int] = None,
    ) -> AgentNegotiation:
        """
        Initialize an AI-to-AI commerce negotiation session.
        Matches buyer requirements against merchant catalog and determines max rounds.
        """
        buyer_profile = BuyerAgentProfile.objects.get(pk=buyer_profile_id)
        merchant = Merchant.objects.get(pk=merchant_id)
        policy, _ = MerchantPolicy.objects.get_or_create(merchant=merchant)

        effective_max_rounds = min(
            buyer_profile.maximum_negotiation_rounds,
            policy.maximum_negotiation_rounds
        )

        selected_product = None
        if product_id is not None:
            try:
                selected_product = Product.objects.get(
                    pk=product_id,
                    merchant=merchant,
                    is_active=True,
                    inventory_quantity__gt=0
                )
            except Product.DoesNotExist:
                selected_product = None

        if not selected_product:
            # Build query string from requirements
            req_query = " ".join(buyer_profile.requirements) if buyer_profile.requirements else "gaming product"
            intent = extract_intent(req_query)
            intent.budget_max = buyer_profile.budget_max
            intent.budget_min = buyer_profile.budget_min

            matches = find_matching_products(intent, merchant=merchant)

            if not matches:
                negotiation = AgentNegotiation.objects.create(
                    buyer_profile=buyer_profile,
                    merchant=merchant,
                    product=None,
                    status=AgentNegotiation.STATUS_REJECTED,
                    max_rounds=effective_max_rounds,
                    termination_reason="NO_MATCHING_PRODUCT"
                )
                AgentNegotiationEvent.objects.create(
                    negotiation=negotiation,
                    round_number=0,
                    actor=AgentNegotiationEvent.ACTOR_SYSTEM,
                    event_type=AgentNegotiationEvent.EVENT_NEGOTIATION_ENDED,
                    decision="NO_MATCHING_PRODUCT",
                    message="No products in merchant catalog matched buyer hard requirements."
                )
                return negotiation

            selected_product = matches[0]

        negotiation = AgentNegotiation.objects.create(
            buyer_profile=buyer_profile,
            merchant=merchant,
            product=selected_product,
            status=AgentNegotiation.STATUS_ACTIVE,
            max_rounds=effective_max_rounds,
            current_price=selected_product.price
        )

        AgentNegotiationEvent.objects.create(
            negotiation=negotiation,
            round_number=0,
            actor=AgentNegotiationEvent.ACTOR_SYSTEM,
            event_type=AgentNegotiationEvent.EVENT_NEGOTIATION_STARTED,
            message=f"AI Negotiation initialized between Buyer '{buyer_profile.name}' and Merchant '{merchant.business_name}'."
        )

        AgentNegotiationEvent.objects.create(
            negotiation=negotiation,
            round_number=0,
            actor=AgentNegotiationEvent.ACTOR_SYSTEM,
            event_type=AgentNegotiationEvent.EVENT_PRODUCT_SELECTED,
            proposed_price=selected_product.price,
            message=f"Product selected for negotiation: '{selected_product.name}' (Catalog Price: ₹{selected_product.price:.2f})."
        )

        return negotiation

    @classmethod
    @transaction.atomic
    def run_negotiation(
        cls,
        negotiation: AgentNegotiation,
        max_steps: int = 10
    ) -> Dict[str, Any]:
        """
        Executes AI-to-AI negotiation loop for up to max_steps execution steps.
        Resumable if paused before reaching terminal state.
        """
        # Guard terminal state
        if negotiation.status in {
            AgentNegotiation.STATUS_AGREED,
            AgentNegotiation.STATUS_REJECTED,
            AgentNegotiation.STATUS_EXPIRED
        }:
            return cls._build_negotiation_summary(negotiation)

        buyer_profile = negotiation.buyer_profile
        merchant = negotiation.merchant
        policy, _ = MerchantPolicy.objects.get_or_create(merchant=merchant)
        product = negotiation.product

        if not product:
            cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_REJECTED)
            negotiation.status = AgentNegotiation.STATUS_REJECTED
            negotiation.termination_reason = "NO_MATCHING_PRODUCT"
            negotiation.save()
            return cls._build_negotiation_summary(negotiation)

        steps_taken = 0

        while steps_taken < max_steps:
            # Check round limits (allow Buyer to evaluate the merchant's final round offer)
            if negotiation.negotiation_round >= negotiation.max_rounds and negotiation.status != AgentNegotiation.STATUS_BUYER_TURN:
                cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_EXPIRED)
                negotiation.status = AgentNegotiation.STATUS_EXPIRED
                negotiation.termination_reason = "MAX_ROUNDS_EXHAUSTED"
                negotiation.save()

                AgentNegotiationEvent.objects.create(
                    negotiation=negotiation,
                    round_number=negotiation.negotiation_round,
                    actor=AgentNegotiationEvent.ACTOR_SYSTEM,
                    event_type=AgentNegotiationEvent.EVENT_NEGOTIATION_ENDED,
                    decision="EXPIRED",
                    message=f"Maximum negotiation rounds ({negotiation.max_rounds}) reached without agreement."
                )
                break

            # ── Turn A: Merchant Initial Offer ──────────────────────────────
            if negotiation.status in {AgentNegotiation.STATUS_ACTIVE, AgentNegotiation.STATUS_MERCHANT_TURN} and negotiation.merchant_last_offer is None:
                steps_taken += 1
                req_query = " ".join(buyer_profile.requirements) if buyer_profile.requirements else product.name
                intent = extract_intent(req_query)
                intent.budget_max = buyer_profile.budget_max

                opps = generate_opportunities(intent, [product], policy)
                decision_res = make_decision(intent, opps, policy)

                if decision_res.selected_opportunity:
                    merchant_offer = decision_res.selected_opportunity.proposed_price
                else:
                    merchant_offer = product.price

                cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_BUYER_TURN)
                negotiation.status = AgentNegotiation.STATUS_BUYER_TURN
                negotiation.merchant_last_offer = merchant_offer
                negotiation.current_price = merchant_offer
                negotiation.save()

                AgentNegotiationEvent.objects.create(
                    negotiation=negotiation,
                    round_number=negotiation.negotiation_round,
                    actor=AgentNegotiationEvent.ACTOR_AI_MERCHANT,
                    event_type=AgentNegotiationEvent.EVENT_MERCHANT_OFFER,
                    proposed_price=merchant_offer,
                    decision=decision_res.selected_action or 'OFFER',
                    message=f"AI Merchant offered '{product.name}' for ₹{merchant_offer:.2f}.",
                    metadata=_json_safe({
                        'selected_action': decision_res.selected_action,
                        'decision_trace': decision_res.decision_trace
                    })
                )

            # ── Turn B: Buyer Evaluates Merchant Offer ──────────────────────
            if negotiation.status == AgentNegotiation.STATUS_BUYER_TURN:
                steps_taken += 1
                merchant_offer = negotiation.merchant_last_offer

                buyer_eval = BuyerDecisionEngine.evaluate_offer(
                    product=product,
                    merchant_offer=merchant_offer,
                    buyer_profile=buyer_profile,
                    current_round=negotiation.negotiation_round
                )

                buyer_dec = buyer_eval['decision']

                if buyer_dec == 'ACCEPT':
                    cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_AGREED)
                    negotiation.status = AgentNegotiation.STATUS_AGREED
                    negotiation.agreed_price = buyer_eval['agreed_price']
                    negotiation.payment_ready = True
                    negotiation.termination_reason = "BUYER_ACCEPTED"
                    negotiation.save()

                    AgentNegotiationEvent.objects.create(
                        negotiation=negotiation,
                        round_number=negotiation.negotiation_round,
                        actor=AgentNegotiationEvent.ACTOR_AI_BUYER,
                        event_type=AgentNegotiationEvent.EVENT_BUYER_ACCEPT,
                        proposed_price=buyer_eval['agreed_price'],
                        decision='ACCEPT',
                        message=f"AI Buyer accepted merchant offer of ₹{buyer_eval['agreed_price']:.2f}.",
                        metadata=_json_safe({'signals': buyer_eval['signals'], 'decision_trace': buyer_eval['decision_trace']})
                    )

                    AgentNegotiationEvent.objects.create(
                        negotiation=negotiation,
                        round_number=negotiation.negotiation_round,
                        actor=AgentNegotiationEvent.ACTOR_SYSTEM,
                        event_type=AgentNegotiationEvent.EVENT_AGREEMENT_REACHED,
                        proposed_price=buyer_eval['agreed_price'],
                        decision='AGREED',
                        message=f"Commercial agreement reached at ₹{buyer_eval['agreed_price']:.2f}."
                    )
                    break

                elif buyer_dec == 'REJECT':
                    cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_REJECTED)
                    negotiation.status = AgentNegotiation.STATUS_REJECTED
                    negotiation.termination_reason = buyer_eval['reason']
                    negotiation.save()

                    customer_msg = buyer_eval.get('customer_message') or buyer_eval['reason']
                    AgentNegotiationEvent.objects.create(
                        negotiation=negotiation,
                        round_number=negotiation.negotiation_round,
                        actor=AgentNegotiationEvent.ACTOR_AI_BUYER,
                        event_type=AgentNegotiationEvent.EVENT_BUYER_REJECT,
                        decision='REJECT',
                        message=customer_msg,
                        metadata=_json_safe({
                            'signals': buyer_eval['signals'],
                            'internal_reason': buyer_eval['reason'],
                            'decision_trace': buyer_eval.get('decision_trace'),
                        })
                    )
                    break

                elif buyer_dec == 'COUNTER':
                    buyer_counter = buyer_eval['counter_offer']
                    cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_MERCHANT_TURN)
                    negotiation.status = AgentNegotiation.STATUS_MERCHANT_TURN
                    negotiation.buyer_last_offer = buyer_counter
                    negotiation.current_price = buyer_counter
                    negotiation.save()

                    AgentNegotiationEvent.objects.create(
                        negotiation=negotiation,
                        round_number=negotiation.negotiation_round,
                        actor=AgentNegotiationEvent.ACTOR_AI_BUYER,
                        event_type=AgentNegotiationEvent.EVENT_BUYER_COUNTER,
                        proposed_price=buyer_counter,
                        decision='COUNTER',
                        message=f"AI Buyer counter-offered ₹{buyer_counter:.2f}.",
                        metadata=_json_safe({'signals': buyer_eval['signals'], 'decision_trace': buyer_eval['decision_trace']})
                    )

            # ── Turn C: Merchant Evaluates Buyer Counteroffer ──────────────
            if negotiation.status == AgentNegotiation.STATUS_MERCHANT_TURN:
                steps_taken += 1
                buyer_counter = negotiation.buyer_last_offer

                merch_eval = NegotiationEngine.evaluate_offer(
                    merchant_policy=policy,
                    product=product,
                    buyer_proposed_price=buyer_counter,
                    current_round=negotiation.negotiation_round,
                    previous_merchant_offer=negotiation.merchant_last_offer
                )

                merch_dec = merch_eval['action']

                if merch_dec == 'ACCEPT':
                    cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_AGREED)
                    negotiation.status = AgentNegotiation.STATUS_AGREED
                    negotiation.agreed_price = merch_eval['agreed_price']
                    negotiation.payment_ready = True
                    negotiation.termination_reason = "MERCHANT_ACCEPTED"
                    negotiation.save()

                    AgentNegotiationEvent.objects.create(
                        negotiation=negotiation,
                        round_number=negotiation.negotiation_round,
                        actor=AgentNegotiationEvent.ACTOR_AI_MERCHANT,
                        event_type=AgentNegotiationEvent.EVENT_MERCHANT_ACCEPT,
                        proposed_price=merch_eval['agreed_price'],
                        decision='ACCEPT',
                        message=f"AI Merchant accepted buyer offer of ₹{merch_eval['agreed_price']:.2f}."
                    )

                    AgentNegotiationEvent.objects.create(
                        negotiation=negotiation,
                        round_number=negotiation.negotiation_round,
                        actor=AgentNegotiationEvent.ACTOR_SYSTEM,
                        event_type=AgentNegotiationEvent.EVENT_AGREEMENT_REACHED,
                        proposed_price=merch_eval['agreed_price'],
                        decision='AGREED',
                        message=f"Commercial agreement reached at ₹{merch_eval['agreed_price']:.2f}."
                    )
                    break

                elif merch_dec == 'REJECT':
                    cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_REJECTED)
                    negotiation.status = AgentNegotiation.STATUS_REJECTED
                    negotiation.termination_reason = merch_eval['reason']
                    negotiation.save()

                    customer_msg = merch_eval.get('customer_message') or merch_eval['reason']
                    AgentNegotiationEvent.objects.create(
                        negotiation=negotiation,
                        round_number=negotiation.negotiation_round,
                        actor=AgentNegotiationEvent.ACTOR_AI_MERCHANT,
                        event_type=AgentNegotiationEvent.EVENT_MERCHANT_REJECT,
                        decision='REJECT',
                        message=customer_msg,
                        metadata=_json_safe({
                            'internal_reason': merch_eval['reason'],
                            'metrics': merch_eval.get('metrics')
                        })
                    )
                    break

                elif merch_dec == 'COUNTER':
                    negotiation.negotiation_round += 1
                    merchant_counter = merch_eval['counter_price']
                    cls.validate_transition(negotiation.status, AgentNegotiation.STATUS_BUYER_TURN)
                    negotiation.status = AgentNegotiation.STATUS_BUYER_TURN
                    negotiation.merchant_last_offer = merchant_counter
                    negotiation.current_price = merchant_counter
                    negotiation.save()

                    AgentNegotiationEvent.objects.create(
                        negotiation=negotiation,
                        round_number=negotiation.negotiation_round,
                        actor=AgentNegotiationEvent.ACTOR_AI_MERCHANT,
                        event_type=AgentNegotiationEvent.EVENT_MERCHANT_COUNTER,
                        proposed_price=merchant_counter,
                        decision='COUNTER_OFFER',
                        message=f"AI Merchant counter-offered ₹{merchant_counter:.2f}."
                    )

        return cls._build_negotiation_summary(negotiation)

    @classmethod
    def _build_negotiation_summary(cls, negotiation: AgentNegotiation) -> Dict[str, Any]:
        """
        Builds a structured, safe, machine-readable summary and decision trace for a negotiation.
        Excludes cost_price.
        """
        events = negotiation.events.all()
        rounds_list = []
        
        # Build round-by-round trace
        current_round_data = {}
        for evt in events:
            if evt.event_type in {AgentNegotiationEvent.EVENT_MERCHANT_OFFER, AgentNegotiationEvent.EVENT_MERCHANT_COUNTER}:
                current_round_data = {
                    "round": evt.round_number,
                    "merchant_offer": str(evt.proposed_price) if evt.proposed_price else None,
                    "merchant_decision": evt.decision
                }
            elif evt.event_type == AgentNegotiationEvent.EVENT_BUYER_COUNTER:
                current_round_data["buyer_decision"] = "COUNTER"
                current_round_data["buyer_counter"] = str(evt.proposed_price) if evt.proposed_price else None
                rounds_list.append(dict(current_round_data))
                current_round_data = {}
            elif evt.event_type == AgentNegotiationEvent.EVENT_BUYER_ACCEPT:
                current_round_data["buyer_decision"] = "ACCEPT"
                rounds_list.append(dict(current_round_data))
                current_round_data = {}
            elif evt.event_type == AgentNegotiationEvent.EVENT_BUYER_REJECT:
                current_round_data["buyer_decision"] = "REJECT"
                rounds_list.append(dict(current_round_data))
                current_round_data = {}

        return {
            "negotiation_id": str(negotiation.id),
            "status": negotiation.status,
            "product": {
                "id": negotiation.product.id,
                "name": negotiation.product.name,
                "category": negotiation.product.category,
                "catalog_price": str(negotiation.product.price)
            } if negotiation.product else None,
            "starting_price": str(negotiation.product.price) if negotiation.product else None,
            "final_price": str(negotiation.agreed_price) if negotiation.agreed_price else (str(negotiation.current_price) if negotiation.current_price else None),
            "agreed_price": str(negotiation.agreed_price) if negotiation.agreed_price else None,
            "payment_ready": negotiation.payment_ready,
            "rounds_used": negotiation.negotiation_round,
            "max_rounds": negotiation.max_rounds,
            "buyer_strategy": negotiation.buyer_profile.strategy,
            "termination_reason": negotiation.termination_reason,
            "trace": {
                "negotiation_id": str(negotiation.id),
                "rounds": rounds_list,
                "final_status": negotiation.status,
                "agreed_price": str(negotiation.agreed_price) if negotiation.agreed_price else None
            }
        }
