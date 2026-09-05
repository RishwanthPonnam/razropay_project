"""
ai/services/commerce_agent.py
───────────────────────────
Bounded Autonomous Commerce Agent Service.

Orchestrates:
- intent_engine.py
- product_matcher.py
- revenue_engine.py
- decision_engine.py
- negotiation_engine.py

Maintains stateful CommerceConversation & append-only CommerceEvent log.
Enforces valid state machine transitions & MerchantPolicy boundaries.
"""

from decimal import Decimal
from typing import Dict, Any, Optional

from django.db import transaction

from merchants.models import Merchant, MerchantPolicy
from products.models import Product

from ai.models import CommerceConversation, CommerceEvent
from ai.services.intent_engine import extract_intent
from ai.services.product_matcher import find_matching_products
from ai.services.revenue_engine import generate_opportunities
from ai.services.decision_engine import make_decision
from ai.services.negotiation_engine import (
    NegotiationEngine,
    classify_buyer_message,
    extract_buyer_proposed_price
)


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state machine transition is attempted."""
    pass


class CommerceAgent:
    """
    Stateful Autonomous Commerce Agent.
    """

    ALLOWED_TRANSITIONS = {
        CommerceConversation.STATUS_ACTIVE: {
            CommerceConversation.STATUS_OFFERED,
            CommerceConversation.STATUS_COUNTER_OFFERED,
            CommerceConversation.STATUS_ACCEPTED,
            CommerceConversation.STATUS_REJECTED,
            CommerceConversation.STATUS_EXPIRED
        },
        CommerceConversation.STATUS_OFFERED: {
            CommerceConversation.STATUS_OFFERED,
            CommerceConversation.STATUS_COUNTER_OFFERED,
            CommerceConversation.STATUS_ACCEPTED,
            CommerceConversation.STATUS_REJECTED,
            CommerceConversation.STATUS_EXPIRED
        },
        CommerceConversation.STATUS_COUNTER_OFFERED: {
            CommerceConversation.STATUS_OFFERED,
            CommerceConversation.STATUS_COUNTER_OFFERED,
            CommerceConversation.STATUS_ACCEPTED,
            CommerceConversation.STATUS_REJECTED,
            CommerceConversation.STATUS_EXPIRED
        },
        CommerceConversation.STATUS_ACCEPTED: set(),  # Terminal state
        CommerceConversation.STATUS_REJECTED: set(),  # Terminal state
        CommerceConversation.STATUS_EXPIRED: set(),   # Terminal state
    }

    @staticmethod
    def create_conversation(
        merchant_id: Optional[int] = None,
        buyer_session_id: str = ''
    ) -> CommerceConversation:
        """
        Create a new persistent commerce conversation session.
        """
        if merchant_id:
            merchant = Merchant.objects.get(pk=merchant_id)
        else:
            merchant = Merchant.objects.first()
            if not merchant:
                raise ValueError("No Merchant found in system.")

        conversation = CommerceConversation.objects.create(
            merchant=merchant,
            buyer_session_id=buyer_session_id or '',
            status=CommerceConversation.STATUS_ACTIVE,
            negotiation_round=0
        )

        # Log system event
        CommerceEvent.objects.create(
            conversation=conversation,
            event_type=CommerceEvent.EVENT_SYSTEM_EVENT,
            actor=CommerceEvent.ACTOR_SYSTEM,
            message=f"Conversation created for merchant '{merchant.business_name}'."
        )

        return conversation

    @staticmethod
    def validate_transition(current_status: str, new_status: str) -> None:
        """
        Validate whether transitioning from current_status to new_status is allowed.
        """
        if current_status == new_status:
            return

        allowed = CommerceAgent.ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise InvalidStateTransitionError(
                f"Cannot transition conversation from '{current_status}' to '{new_status}'."
            )

    @classmethod
    @transaction.atomic
    def process_message(
        cls,
        conversation: CommerceConversation,
        message: str
    ) -> Dict[str, Any]:
        """
        Process a buyer message in a stateful conversation.

        Steps:
        1. Validate conversation status (block terminal states).
        2. Record BUYER_MESSAGE event.
        3. Extract price offer & classify buyer message.
        4. Re-evaluate Intent, Product Matching, Revenue & Decision Engines.
        5. Execute negotiation logic / policy evaluation.
        6. Record AGENT_MESSAGE event & update conversation state.
        """
        # Guard terminal states
        if conversation.status in {
            CommerceConversation.STATUS_ACCEPTED,
            CommerceConversation.STATUS_REJECTED,
            CommerceConversation.STATUS_EXPIRED
        }:
            return {
                'conversation_id': str(conversation.id),
                'status': conversation.status,
                'message': f"Conversation is already {conversation.status.lower()}. No further negotiation permitted.",
                'action': 'TERMINAL_STATE',
                'product': {
                    'id': conversation.current_product.id,
                    'name': conversation.current_product.name
                } if conversation.current_product else None,
                'offered_price': str(conversation.current_price) if conversation.current_price else None,
                'agreed_price': str(conversation.agreed_price) if conversation.agreed_price else None,
                'payment_ready': (conversation.status == CommerceConversation.STATUS_ACCEPTED),
                'negotiation_round': conversation.negotiation_round,
                'reason': f"Conversation reached terminal state '{conversation.status}'."
            }

        # 1. Record BUYER_MESSAGE event
        proposed_price_raw = extract_buyer_proposed_price(message)
        CommerceEvent.objects.create(
            conversation=conversation,
            event_type=CommerceEvent.EVENT_BUYER_MESSAGE,
            actor=CommerceEvent.ACTOR_BUYER,
            message=message,
            proposed_price=proposed_price_raw
        )

        msg_type = classify_buyer_message(message)
        merchant = conversation.merchant
        policy, _ = MerchantPolicy.objects.get_or_create(merchant=merchant)

        # 2. Handle ACCEPTANCE ("okay", "deal", "I'll take it")
        if msg_type == 'ACCEPTANCE':
            if conversation.current_product and conversation.current_price:
                cls.validate_transition(conversation.status, CommerceConversation.STATUS_ACCEPTED)
                conversation.status = CommerceConversation.STATUS_ACCEPTED
                conversation.agreed_price = conversation.current_price
                conversation.save()

                # Log events
                CommerceEvent.objects.create(
                    conversation=conversation,
                    event_type=CommerceEvent.EVENT_ACCEPTANCE,
                    actor=CommerceEvent.ACTOR_BUYER,
                    message=message,
                    proposed_price=conversation.current_price
                )

                agent_msg = f"Great! Commercial agreement reached for {conversation.current_product.name} at ₹{conversation.current_price:.2f}."
                CommerceEvent.objects.create(
                    conversation=conversation,
                    event_type=CommerceEvent.EVENT_AGENT_MESSAGE,
                    actor=CommerceEvent.ACTOR_AGENT,
                    message=agent_msg,
                    selected_action='ACCEPTED',
                    metadata={'payment_ready': True}
                )

                return {
                    'conversation_id': str(conversation.id),
                    'status': CommerceConversation.STATUS_ACCEPTED,
                    'message': agent_msg,
                    'action': 'ACCEPTED',
                    'product': {
                        'id': conversation.current_product.id,
                        'name': conversation.current_product.name
                    },
                    'offered_price': str(conversation.current_price),
                    'agreed_price': str(conversation.agreed_price),
                    'payment_ready': True,
                    'negotiation_round': conversation.negotiation_round,
                    'reason': "Buyer accepted current valid offer.",
                    'decision_trace': {
                        'agent_step': 'NEGOTIATION',
                        'buyer_message': message,
                        'decision': 'ACCEPTED',
                        'negotiation_round': conversation.negotiation_round,
                        'policy_validated': True,
                        'next_state': CommerceConversation.STATUS_ACCEPTED
                    }
                }

        # 3. Handle REJECTION ("no", "too expensive")
        if msg_type == 'REJECTION':
            cls.validate_transition(conversation.status, CommerceConversation.STATUS_REJECTED)
            conversation.status = CommerceConversation.STATUS_REJECTED
            conversation.save()

            CommerceEvent.objects.create(
                conversation=conversation,
                event_type=CommerceEvent.EVENT_REJECTION,
                actor=CommerceEvent.ACTOR_BUYER,
                message=message
            )

            agent_msg = "Understood. The negotiation has been closed. Let me know if you need anything else."
            CommerceEvent.objects.create(
                conversation=conversation,
                event_type=CommerceEvent.EVENT_AGENT_MESSAGE,
                actor=CommerceEvent.ACTOR_AGENT,
                message=agent_msg,
                selected_action='REJECTED'
            )

            return {
                'conversation_id': str(conversation.id),
                'status': CommerceConversation.STATUS_REJECTED,
                'message': agent_msg,
                'action': 'REJECTED',
                'product': {
                    'id': conversation.current_product.id,
                    'name': conversation.current_product.name
                } if conversation.current_product else None,
                'offered_price': str(conversation.current_price) if conversation.current_price else None,
                'agreed_price': None,
                'payment_ready': False,
                'negotiation_round': conversation.negotiation_round,
                'reason': "Buyer rejected the offer.",
                'decision_trace': {
                    'agent_step': 'NEGOTIATION',
                    'buyer_message': message,
                    'decision': 'REJECTED',
                    'negotiation_round': conversation.negotiation_round,
                    'next_state': CommerceConversation.STATUS_REJECTED
                }
            }

        # 4. Handle OFFER (buyer proposes price, e.g. "Can you do 3500?")
        if msg_type == 'OFFER' and proposed_price_raw is not None:
            # Check if we have a current product or need to match one
            if not conversation.current_product:
                intent = extract_intent(message)
                matches = find_matching_products(intent, merchant=merchant)
                if matches:
                    conversation.current_product = matches[0]
                    conversation.current_intent = intent.to_dict()

            if not conversation.current_product:
                agent_msg = "I couldn't identify the product you are making an offer for. Could you clarify what product you'd like to buy?"
                return {
                    'conversation_id': str(conversation.id),
                    'status': conversation.status,
                    'message': agent_msg,
                    'action': 'HOLD',
                    'product': None,
                    'offered_price': None,
                    'agreed_price': None,
                    'payment_ready': False,
                    'negotiation_round': conversation.negotiation_round,
                    'reason': "No product selected for buyer price offer."
                }

            product = conversation.current_product
            eval_res = NegotiationEngine.evaluate_offer(
                merchant_policy=policy,
                product=product,
                buyer_proposed_price=proposed_price_raw,
                current_round=conversation.negotiation_round
            )

            action = eval_res['action']

            if action == 'ACCEPT':
                cls.validate_transition(conversation.status, CommerceConversation.STATUS_ACCEPTED)
                conversation.status = CommerceConversation.STATUS_ACCEPTED
                conversation.agreed_price = eval_res['agreed_price']
                conversation.current_price = eval_res['agreed_price']
                conversation.save()

                agent_msg = f"I accept your offer of ₹{eval_res['agreed_price']:.2f} for {product.name}!"
                CommerceEvent.objects.create(
                    conversation=conversation,
                    event_type=CommerceEvent.EVENT_AGENT_MESSAGE,
                    actor=CommerceEvent.ACTOR_AGENT,
                    message=agent_msg,
                    proposed_price=eval_res['agreed_price'],
                    selected_action='ACCEPT_OFFER',
                    metadata={'payment_ready': True}
                )

                return {
                    'conversation_id': str(conversation.id),
                    'status': CommerceConversation.STATUS_ACCEPTED,
                    'message': agent_msg,
                    'action': 'ACCEPTED',
                    'product': {'id': product.id, 'name': product.name},
                    'offered_price': str(eval_res['agreed_price']),
                    'agreed_price': str(eval_res['agreed_price']),
                    'payment_ready': True,
                    'negotiation_round': conversation.negotiation_round,
                    'reason': eval_res['reason'],
                    'decision_trace': {
                        'agent_step': 'NEGOTIATION',
                        'buyer_message': message,
                        'buyer_offer': str(proposed_price_raw),
                        'decision': 'ACCEPT',
                        'negotiation_round': conversation.negotiation_round,
                        'policy_validated': True,
                        'next_state': CommerceConversation.STATUS_ACCEPTED
                    }
                }

            elif action == 'COUNTER':
                conversation.negotiation_round += 1
                cls.validate_transition(conversation.status, CommerceConversation.STATUS_COUNTER_OFFERED)
                conversation.status = CommerceConversation.STATUS_COUNTER_OFFERED
                conversation.current_price = eval_res['counter_price']
                conversation.save()

                counter_price = eval_res['counter_price']
                agent_msg = f"I can't do ₹{proposed_price_raw:.2f} under the merchant's pricing policy, but I can offer the {product.name} for ₹{counter_price:.2f}."

                CommerceEvent.objects.create(
                    conversation=conversation,
                    event_type=CommerceEvent.EVENT_COUNTER_OFFER,
                    actor=CommerceEvent.ACTOR_AGENT,
                    message=agent_msg,
                    proposed_price=counter_price,
                    selected_action='COUNTER_OFFER'
                )

                return {
                    'conversation_id': str(conversation.id),
                    'status': CommerceConversation.STATUS_COUNTER_OFFERED,
                    'message': agent_msg,
                    'action': 'COUNTER_OFFER',
                    'product': {'id': product.id, 'name': product.name},
                    'offered_price': str(counter_price),
                    'agreed_price': None,
                    'payment_ready': False,
                    'negotiation_round': conversation.negotiation_round,
                    'reason': eval_res['reason'],
                    'decision_trace': {
                        'agent_step': 'NEGOTIATION',
                        'buyer_message': message,
                        'buyer_offer': str(proposed_price_raw),
                        'counter_price': str(counter_price),
                        'decision': 'COUNTER_OFFER',
                        'negotiation_round': conversation.negotiation_round,
                        'policy_validated': True,
                        'next_state': CommerceConversation.STATUS_COUNTER_OFFERED
                    }
                }

            else:  # REJECT
                cls.validate_transition(conversation.status, CommerceConversation.STATUS_REJECTED)
                conversation.status = CommerceConversation.STATUS_REJECTED
                conversation.save()

                agent_msg = eval_res['reason']
                CommerceEvent.objects.create(
                    conversation=conversation,
                    event_type=CommerceEvent.EVENT_AGENT_MESSAGE,
                    actor=CommerceEvent.ACTOR_AGENT,
                    message=agent_msg,
                    selected_action='REJECT_OFFER'
                )

                return {
                    'conversation_id': str(conversation.id),
                    'status': CommerceConversation.STATUS_REJECTED,
                    'message': agent_msg,
                    'action': 'REJECTED',
                    'product': {'id': product.id, 'name': product.name},
                    'offered_price': str(conversation.current_price) if conversation.current_price else None,
                    'agreed_price': None,
                    'payment_ready': False,
                    'negotiation_round': conversation.negotiation_round,
                    'reason': eval_res['reason'],
                    'decision_trace': {
                        'agent_step': 'NEGOTIATION',
                        'buyer_message': message,
                        'buyer_offer': str(proposed_price_raw),
                        'decision': 'REJECT',
                        'negotiation_round': conversation.negotiation_round,
                        'policy_validated': False,
                        'next_state': CommerceConversation.STATUS_REJECTED
                    }
                }

        # 5. Handle SEARCH or REQUIREMENT_CHANGE
        intent = extract_intent(message)
        matched_candidates = find_matching_products(intent, merchant=merchant)

        if not matched_candidates:
            agent_msg = "I couldn't find any products in our catalog matching your request. Could you try a different search?"
            return {
                'conversation_id': str(conversation.id),
                'status': conversation.status,
                'message': agent_msg,
                'action': 'HOLD',
                'product': None,
                'offered_price': None,
                'agreed_price': None,
                'payment_ready': False,
                'negotiation_round': conversation.negotiation_round,
                'reason': "No candidate products found for buyer search."
            }

        # Run Revenue Opportunity Engine & Decision Engine
        candidate_products = matched_candidates
        opps = generate_opportunities(intent, candidate_products, policy)
        decision_result = make_decision(intent, opps, policy)

        selected_opp = decision_result.selected_opportunity
        selected_product = matched_candidates[0]
        if selected_opp and selected_opp.product_id:
            found = Product.objects.filter(pk=selected_opp.product_id).first()
            if found:
                selected_product = found

        proposed_price = selected_opp.proposed_price if selected_opp else selected_product.price

        # Update conversation state
        cls.validate_transition(conversation.status, CommerceConversation.STATUS_OFFERED)
        conversation.status = CommerceConversation.STATUS_OFFERED
        conversation.current_product = selected_product
        conversation.current_intent = intent.to_dict()
        conversation.current_price = proposed_price
        conversation.save()

        agent_msg = f"I recommend the {selected_product.name} for ₹{proposed_price:.2f}."
        CommerceEvent.objects.create(
            conversation=conversation,
            event_type=CommerceEvent.EVENT_OFFER,
            actor=CommerceEvent.ACTOR_AGENT,
            message=agent_msg,
            proposed_price=proposed_price,
            selected_action=decision_result.selected_action,
            metadata={
                'decision_trace': decision_result.decision_trace
            }
        )

        return {
            'conversation_id': str(conversation.id),
            'status': CommerceConversation.STATUS_OFFERED,
            'message': agent_msg,
            'action': decision_result.selected_action or 'RECOMMEND',
            'product': {
                'id': selected_product.id,
                'name': selected_product.name
            },
            'offered_price': str(proposed_price),
            'agreed_price': None,
            'payment_ready': False,
            'negotiation_round': conversation.negotiation_round,
            'reason': decision_result.reason,
            'decision_trace': {
                'agent_step': 'RECOMMENDATION',
                'buyer_message': message,
                'decision_engine_trace': decision_result.decision_trace,
                'next_state': CommerceConversation.STATUS_OFFERED
            }
        }
