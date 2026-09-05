"""
API views for the ai app.

POST /api/ai/intent/
    Accepts a natural-language buyer message, returns structured intent
    and matching candidate products.

POST /api/ai/opportunities/
    Accepts a natural-language buyer message and optional merchant_id.
    Returns structured intent and a ranked list of merchant-economic
    revenue opportunities (deterministic heuristic scoring).
    This is a merchant-side intelligence endpoint; it may include
    resulting_margin_percent and policy_compliant but never cost_price.

POST /api/ai/decision/
    Accepts a natural-language buyer message and optional merchant_id.
    Runs the full pipeline: intent -> product match -> opportunities ->
    decision engine.  Returns the selected decision, alternatives,
    rejected candidates, and a machine-readable decision trace.
    Merchant-side endpoint; never exposes cost_price.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    DecisionRequestSerializer,
    DecisionResultSerializer,
    IntentRequestSerializer,
    OpportunityRequestSerializer,
    ProductMatchSerializer,
    RevenueOpportunitySerializer,
)
from .services.decision_engine import make_decision
from .services.intent_engine import extract_intent
from .services.product_matcher import find_matching_products
from .services.revenue_engine import generate_opportunities


class IntentView(APIView):
    """
    POST /api/ai/intent/

    Request body:
        { "message": "I need a gaming keyboard under 4500" }

    Response:
        {
            "intent":  { ...structured BuyerIntent... },
            "matches": [ ...candidate products (no cost_price)... ]
        }

    Business-logic layers involved (in order):
        1. IntentRequestSerializer  — input validation
        2. extract_intent()         — NL -> BuyerIntent  (intent_engine)
        3. find_matching_products() — BuyerIntent -> QuerySet (product_matcher)
        4. ProductMatchSerializer   — QuerySet -> JSON (no cost_price)
    """

    def post(self, request):
        # 1. Validate request
        serializer = IntentRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        message: str = serializer.validated_data["message"]

        # 2. Extract structured intent
        intent = extract_intent(message)

        # 3. Find matching products (global search — no merchant scope)
        matches = find_matching_products(intent)

        # 4. Serialize and return
        match_data = ProductMatchSerializer(matches, many=True).data

        return Response(
            {
                "intent":  intent.to_dict(),
                "matches": list(match_data),
            }
        )


class OpportunityView(APIView):
    """
    POST /api/ai/opportunities/

    Request body:
        { "message": "I need a gaming keyboard under 4500" }

        Optionally:
        { "merchant_id": 1, "message": "I need a gaming keyboard under 4500" }

    Response:
        {
            "intent":  { ...structured BuyerIntent... },
            "merchant_id": <int>,
            "opportunities": [ ...ranked RevenueOpportunity objects... ]
        }

    Merchant-side intelligence endpoint.  Exposes:
        - resulting_margin_percent  (acceptable for merchant-side view)
        - policy_compliant          (acceptable for merchant-side view)
        - metadata.signals          (explainability / AI decision trace)

    NEVER exposes:
        - cost_price
        - internal margin arithmetic that would reveal cost to a buyer

    Business-logic layers (in order):
        1. OpportunityRequestSerializer — input validation
        2. Merchant resolution          — explicit ID or demo merchant fallback
        3. MerchantPolicy load          — guardrails for the engine
        4. extract_intent()             — NL -> BuyerIntent
        5. find_matching_products()     — BuyerIntent + merchant -> Products
        6. generate_opportunities()     — Products + Policy -> opportunities
        7. RevenueOpportunitySerializer — opportunities -> JSON
    """

    def post(self, request):
        from merchants.models import Merchant, MerchantPolicy

        # 1. Validate request
        serializer = OpportunityRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        message: str     = serializer.validated_data["message"]
        merchant_id: int = serializer.validated_data.get("merchant_id")

        # 2. Resolve merchant
        if merchant_id is not None:
            try:
                merchant = Merchant.objects.get(pk=merchant_id)
            except Merchant.DoesNotExist:
                return Response(
                    {"error": f"Merchant {merchant_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            # Fall back to demo merchant (NovaTech Store)
            merchant = Merchant.objects.filter(
                email="demo@novatech.test"
            ).first()
            if merchant is None:
                return Response(
                    {
                        "error": (
                            "No merchant_id provided and demo merchant not found. "
                            "Run `python manage.py seed_demo` first."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        # 3. Load MerchantPolicy
        try:
            policy = merchant.policy
        except MerchantPolicy.DoesNotExist:
            return Response(
                {
                    "error": (
                        f"Merchant '{merchant.business_name}' has no policy configured. "
                        "Please create a MerchantPolicy for this merchant."
                    )
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # 4. Extract structured intent
        intent = extract_intent(message)

        # 5. Find matching products scoped to this merchant
        products = find_matching_products(intent, merchant=merchant)

        # 6. Generate ranked opportunities
        opportunities = generate_opportunities(intent, products, policy)

        # 7. Serialize and return
        opp_data = RevenueOpportunitySerializer(
            [vars(o) for o in opportunities], many=True
        ).data

        return Response(
            {
                "intent":        intent.to_dict(),
                "merchant_id":   merchant.pk,
                "opportunities": list(opp_data),
            }
        )


class DecisionView(APIView):
    """
    POST /api/ai/decision/

    Request body:
        { "message": "I need a gaming keyboard under 4500" }

        Optionally:
        { "merchant_id": 1, "message": "I need a gaming keyboard under 4500" }

    Response:
        {
            "intent":           { ...structured BuyerIntent... },
            "merchant_id":      <int>,
            "selected_decision": { ...DecisionResult fields... },
        }

    Full pipeline (in order):
        1. DecisionRequestSerializer  — input validation
        2. Merchant resolution         — explicit ID or demo fallback
        3. MerchantPolicy load         — guardrails
        4. extract_intent()            — NL -> BuyerIntent
        5. find_matching_products()    — BuyerIntent + merchant -> Products
        6. generate_opportunities()    — Products + Policy -> opportunities
        7. make_decision()             — opportunities -> DecisionResult
        8. DecisionResultSerializer    — DecisionResult -> JSON

    NEVER exposes cost_price.
    requires_approval = True means RECOMMENDED but NOT AUTHORIZED for execution.
    """

    def post(self, request):
        from merchants.models import Merchant, MerchantPolicy

        # 1. Validate request
        serializer = DecisionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        message: str     = serializer.validated_data["message"]
        merchant_id: int = serializer.validated_data.get("merchant_id")

        # 2. Resolve merchant
        if merchant_id is not None:
            try:
                merchant = Merchant.objects.get(pk=merchant_id)
            except Merchant.DoesNotExist:
                return Response(
                    {"error": f"Merchant {merchant_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            merchant = Merchant.objects.filter(email="demo@novatech.test").first()
            if merchant is None:
                return Response(
                    {
                        "error": (
                            "No merchant_id provided and demo merchant not found. "
                            "Run `python manage.py seed_demo` first."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        # 3. Load MerchantPolicy
        try:
            policy = merchant.policy
        except MerchantPolicy.DoesNotExist:
            return Response(
                {
                    "error": (
                        f"Merchant '{merchant.business_name}' has no policy configured."
                    )
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # 4. Extract intent
        intent = extract_intent(message)

        # 5. Find matching products scoped to this merchant
        products = find_matching_products(intent, merchant=merchant)

        # 6. Generate ranked opportunities
        opportunities = generate_opportunities(intent, products, policy)

        # 7. Run decision engine
        decision = make_decision(intent, opportunities, policy)

        # 8. Serialize — selected_opportunity and alternatives need dict conversion
        def opp_to_dict(opp):
            return vars(opp) if opp else None

        decision_data = {
            "selected_action":       decision.selected_action,
            "decision_score":        decision.decision_score,
            "confidence":            decision.confidence,
            "reason":                decision.reason,
            "requires_approval":     decision.requires_approval,
            "selected_opportunity":  opp_to_dict(decision.selected_opportunity),
            "alternatives":          [opp_to_dict(a) for a in decision.alternatives],
            "rejected_opportunities": decision.rejected_opportunities,
            "decision_trace":         decision.decision_trace,
        }
        result_serializer = DecisionResultSerializer(data=decision_data)
        result_serializer.is_valid(raise_exception=True)

        return Response(
            {
                "intent":            intent.to_dict(),
                "merchant_id":       merchant.pk,
                "selected_decision": result_serializer.validated_data,
            }
        )


# ===========================================================================
# STEP 8 VIEWS — Bounded Autonomous Commerce Agent
# ===========================================================================

from .models import CommerceConversation
from .serializers import (
    AgentMessageRequestSerializer,
    CommerceConversationSerializer,
    CreateConversationRequestSerializer,
)
from .services.commerce_agent import CommerceAgent


class AgentConversationView(APIView):
    """
    POST /api/ai/agent/conversations/
    Creates a new stateful commerce conversation session.
    """

    def post(self, request, *args, **kwargs):
        serializer = CreateConversationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        merchant_id = serializer.validated_data.get("merchant_id")
        buyer_session_id = serializer.validated_data.get("buyer_session_id", "")

        try:
            conversation = CommerceAgent.create_conversation(
                merchant_id=merchant_id,
                buyer_session_id=buyer_session_id
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "conversation_id": str(conversation.id),
                "status": conversation.status,
                "merchant_id": conversation.merchant_id,
            },
            status=status.HTTP_201_CREATED,
        )


class AgentConversationDetailView(APIView):
    """
    GET /api/ai/agent/conversations/<uuid:conversation_id>/
    Retrieves current conversation state and append-only event log.
    """

    def get(self, request, conversation_id, *args, **kwargs):
        try:
            conversation = CommerceConversation.objects.get(pk=conversation_id)
        except CommerceConversation.DoesNotExist:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CommerceConversationSerializer(conversation)
        return Response(serializer.data)


class AgentMessageView(APIView):
    """
    POST /api/ai/agent/conversations/<uuid:conversation_id>/messages/
    Processes a buyer message within a stateful conversation session.
    """

    def post(self, request, conversation_id, *args, **kwargs):
        try:
            conversation = CommerceConversation.objects.get(pk=conversation_id)
        except CommerceConversation.DoesNotExist:
            return Response(
                {"error": "Conversation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AgentMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = serializer.validated_data["message"]
        result = CommerceAgent.process_message(conversation, message)

        return Response(
            {
                "conversation_id": str(conversation.id),
                "status": result["status"],
                "agent_response": result,
                "decision": result.get("decision_trace", {}),
            },
            status=status.HTTP_200_OK,
        )


# ===========================================================================
# STEP 9 VIEWS — Autonomous AI Buyer Agent
# ===========================================================================

from products.models import Product
from .models import BuyerAgentProfile, BuyerNegotiationSession
from .serializers import (
    BuyerAgentProfileSerializer,
    BuyerNegotiationSessionSerializer,
    CreateBuyerSessionRequestSerializer,
    OfferEvaluationRequestSerializer,
)
from .services.buyer_agent import BuyerAgent


class BuyerProfileView(APIView):
    """
    POST /api/ai/buyer/profiles/
    Creates a new BuyerAgentProfile.
    """

    def post(self, request, *args, **kwargs):
        serializer = BuyerAgentProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()

        return Response(
            {
                "id": str(profile.id),
                "buyer_session_id": profile.buyer_session_id,
                "status": "ACTIVE",
                "profile": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class BuyerSessionView(APIView):
    """
    POST /api/ai/buyer/sessions/
    Creates a new BuyerNegotiationSession.
    """

    def post(self, request, *args, **kwargs):
        serializer = CreateBuyerSessionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        buyer_profile_id = serializer.validated_data["buyer_profile_id"]
        merchant_id = serializer.validated_data["merchant_id"]

        try:
            session = BuyerAgent.create_session(buyer_profile_id, merchant_id)
        except (BuyerAgentProfile.DoesNotExist, ValueError) as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "session_id": str(session.id),
                "status": session.status,
                "merchant_id": session.merchant_id,
            },
            status=status.HTTP_201_CREATED,
        )


class BuyerSessionDetailView(APIView):
    """
    GET /api/ai/buyer/sessions/<uuid:session_id>/
    Retrieves full state and event history of a buyer negotiation session.
    """

    def get(self, request, session_id, *args, **kwargs):
        try:
            session = BuyerNegotiationSession.objects.get(pk=session_id)
        except BuyerNegotiationSession.DoesNotExist:
            return Response(
                {"error": "Buyer session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = BuyerNegotiationSessionSerializer(session)
        return Response(serializer.data)


class BuyerOfferEvaluationView(APIView):
    """
    POST /api/ai/buyer/sessions/<uuid:session_id>/offers/
    Evaluates a merchant offer using the buyer decision engine.
    """

    def post(self, request, session_id, *args, **kwargs):
        try:
            session = BuyerNegotiationSession.objects.get(pk=session_id)
        except BuyerNegotiationSession.DoesNotExist:
            return Response(
                {"error": "Buyer session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = OfferEvaluationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_id = serializer.validated_data["product_id"]
        merchant_offer = serializer.validated_data["merchant_offer"]

        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response(
                {"error": f"Product with ID {product_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = BuyerAgent.evaluate_merchant_offer(session, product, merchant_offer)

        return Response(result, status=status.HTTP_200_OK)


# ===========================================================================
# STEP 10 VIEWS — Autonomous AI-to-AI Commerce Negotiation
# ===========================================================================

from .models import AgentNegotiation
from .serializers import (
    AgentNegotiationSerializer,
    CreateAgentNegotiationSerializer,
    RunAgentNegotiationSerializer,
)
from .services.agent_negotiation import AgentNegotiationOrchestrator


class AgentNegotiationCreateView(APIView):
    """
    POST /api/ai/negotiations/
    Initializes an AI Buyer ↔ AI Merchant negotiation session.
    GET /api/ai/negotiations/
    Lists all AI Buyer ↔ AI Merchant negotiation sessions.
    """

    def get(self, request, *args, **kwargs):
        negotiations = AgentNegotiation.objects.select_related(
            'product', 'merchant', 'buyer_profile'
        ).prefetch_related('events').all()
        merchant_id = request.query_params.get("merchant_id")
        if merchant_id:
            negotiations = negotiations.filter(merchant_id=merchant_id)
        serializer = AgentNegotiationSerializer(negotiations, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        serializer = CreateAgentNegotiationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        buyer_profile_id = serializer.validated_data["buyer_profile_id"]
        merchant_id = serializer.validated_data["merchant_id"]
        product_id = serializer.validated_data.get("product_id")

        try:
            negotiation = AgentNegotiationOrchestrator.create_negotiation(
                buyer_profile_id=buyer_profile_id,
                merchant_id=merchant_id,
                product_id=product_id,
            )
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "id": str(negotiation.id),
                "negotiation_id": str(negotiation.id),
                "status": negotiation.status,
                "merchant_id": negotiation.merchant_id,
                "product_id": negotiation.product_id if negotiation.product else None,
            },
            status=status.HTTP_201_CREATED,
        )


class AgentNegotiationRunView(APIView):
    """
    POST /api/ai/negotiations/<uuid:negotiation_id>/run/
    Executes negotiation exchanges between AI Buyer and AI Merchant.
    Resumable if paused before reaching terminal state.
    """

    def post(self, request, negotiation_id, *args, **kwargs):
        try:
            negotiation = AgentNegotiation.objects.get(pk=negotiation_id)
        except AgentNegotiation.DoesNotExist:
            return Response(
                {"error": "Negotiation session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = RunAgentNegotiationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        max_steps = serializer.validated_data.get("max_steps", 10)
        summary = AgentNegotiationOrchestrator.run_negotiation(negotiation, max_steps=max_steps)

        return Response(summary, status=status.HTTP_200_OK)


class AgentNegotiationDetailView(APIView):
    """
    GET /api/ai/negotiations/<uuid:negotiation_id>/
    Retrieves complete negotiation summary, full history, and trace. Excludes cost_price.
    """

    def get(self, request, negotiation_id, *args, **kwargs):
        try:
            negotiation = AgentNegotiation.objects.get(pk=negotiation_id)
        except AgentNegotiation.DoesNotExist:
            return Response(
                {"error": "Negotiation session not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = AgentNegotiationSerializer(negotiation)
        summary = AgentNegotiationOrchestrator._build_negotiation_summary(negotiation)
        
        data = serializer.data
        data["summary"] = summary
        return Response(data)



