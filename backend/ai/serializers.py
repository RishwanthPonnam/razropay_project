"""
DRF Serializers for the ai app.

IntentRequestSerializer      — validates POST /api/ai/intent/ request body.
ProductMatchSerializer       — serializes candidate products for buyer-facing
                               responses.  cost_price is intentionally excluded.
OpportunityRequestSerializer — validates POST /api/ai/opportunities/ request body.
RevenueOpportunitySerializer — serializes RevenueOpportunity dataclass instances
                               for merchant-side intelligence responses.
                               cost_price is intentionally excluded.
"""

from rest_framework import serializers

from products.models import Product


class IntentRequestSerializer(serializers.Serializer):
    """Validates the incoming intent request."""

    message = serializers.CharField(
        required=True,
        min_length=1,
        max_length=2000,
        error_messages={
            "blank":    "Message cannot be blank.",
            "required": "A message is required.",
        },
    )


class ProductMatchSerializer(serializers.ModelSerializer):
    """
    Buyer-facing product representation.

    IMPORTANT: cost_price is deliberately excluded from this serializer.
    Internal cost data must never be exposed to a buyer or an external
    AI buyer agent.
    """

    class Meta:
        model = Product
        fields = [
            "id",
            "merchant",
            "name",
            "description",
            "category",
            "price",
            "inventory_quantity",
            "is_active",
        ]
        # cost_price is NOT in fields — intentional omission.


class OpportunityRequestSerializer(serializers.Serializer):
    """
    Validates the incoming request for POST /api/ai/opportunities/.

    merchant_id is optional; when omitted the endpoint falls back to the
    demo NovaTech Store merchant.
    """

    message = serializers.CharField(
        required=True,
        min_length=1,
        max_length=2000,
        error_messages={
            "blank":    "Message cannot be blank.",
            "required": "A message is required.",
        },
    )
    merchant_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )


class RevenueOpportunitySerializer(serializers.Serializer):
    """
    Merchant-side opportunity representation.

    This serializer is used exclusively in the merchant-intelligence endpoint
    (/api/ai/opportunities/).  It is acceptable to include:
      - resulting_margin_percent  (merchant-side metric)
      - policy_compliant          (merchant-side metric)
      - metadata.signals          (explainability trace)

    IMPORTANT: cost_price is never included — it must not leak even in
    merchant-side responses served over the network.
    """

    action                   = serializers.CharField()
    product_id               = serializers.IntegerField()
    product_name             = serializers.CharField()
    base_product_id          = serializers.IntegerField()
    recommended_product_id   = serializers.IntegerField(allow_null=True)
    recommended_product_name = serializers.CharField(allow_null=True)
    current_price            = serializers.DecimalField(max_digits=12, decimal_places=2)
    proposed_price           = serializers.DecimalField(max_digits=12, decimal_places=2)
    price_difference         = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_amount          = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_percent         = serializers.DecimalField(max_digits=5, decimal_places=2)
    resulting_margin_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    opportunity_score        = serializers.IntegerField()
    policy_compliant         = serializers.BooleanField()
    reason                   = serializers.CharField()
    metadata                 = serializers.DictField()


class DecisionRequestSerializer(serializers.Serializer):
    """
    Validates POST /api/ai/decision/ request body.

    merchant_id is optional; falls back to demo NovaTech Store merchant.
    """

    message = serializers.CharField(
        required=True,
        min_length=1,
        max_length=2000,
        error_messages={
            "blank":    "Message cannot be blank.",
            "required": "A message is required.",
        },
    )
    merchant_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )


class RejectedOpportunitySerializer(serializers.Serializer):
    """
    Serializes a single rejected-opportunity record from DecisionResult.

    Each entry in DecisionResult.rejected_opportunities is a dict with keys:
        opportunity : RevenueOpportunity (we flatten key fields)
        stage       : str
        reason      : str

    IMPORTANT: cost_price is never included.
    """
    action                   = serializers.SerializerMethodField()
    product_id               = serializers.SerializerMethodField()
    product_name             = serializers.SerializerMethodField()
    opportunity_score        = serializers.SerializerMethodField()
    proposed_price           = serializers.SerializerMethodField()
    discount_percent         = serializers.SerializerMethodField()
    resulting_margin_percent = serializers.SerializerMethodField()
    stage                    = serializers.CharField()
    reason                   = serializers.CharField()

    def _opp(self, obj):
        return obj["opportunity"]

    def get_action(self, obj):                   return self._opp(obj).action
    def get_product_id(self, obj):               return self._opp(obj).product_id
    def get_product_name(self, obj):             return self._opp(obj).product_name
    def get_opportunity_score(self, obj):        return self._opp(obj).opportunity_score
    def get_proposed_price(self, obj):           return str(self._opp(obj).proposed_price)
    def get_discount_percent(self, obj):         return str(self._opp(obj).discount_percent)
    def get_resulting_margin_percent(self, obj): return str(self._opp(obj).resulting_margin_percent)


class DecisionResultSerializer(serializers.Serializer):
    """
    Serializes a DecisionResult for POST /api/ai/decision/ response.

    Merchant-side intelligence endpoint — may expose:
        - resulting_margin_percent
        - policy_compliant
        - requires_approval
        - decision_trace (for explainability)

    NEVER exposes cost_price.
    """
    selected_action      = serializers.CharField()
    decision_score       = serializers.IntegerField()
    confidence           = serializers.FloatField()
    reason               = serializers.CharField()
    requires_approval    = serializers.BooleanField()
    selected_opportunity = RevenueOpportunitySerializer(allow_null=True)
    alternatives         = RevenueOpportunitySerializer(many=True)
    rejected_opportunities = RejectedOpportunitySerializer(many=True)
    decision_trace       = serializers.DictField()


# ===========================================================================
# STEP 8 SERIALIZERS — Bounded Autonomous Commerce Agent
# ===========================================================================

from .models import CommerceConversation, CommerceEvent


class CreateConversationRequestSerializer(serializers.Serializer):
    merchant_id = serializers.IntegerField(required=False, allow_null=True)
    buyer_session_id = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CommerceEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommerceEvent
        fields = [
            'id',
            'event_type',
            'actor',
            'message',
            'proposed_price',
            'selected_action',
            'metadata',
            'created_at',
        ]


class CommerceConversationSerializer(serializers.ModelSerializer):
    events = CommerceEventSerializer(many=True, read_only=True)
    product_name = serializers.ReadOnlyField(source='current_product.name')

    class Meta:
        model = CommerceConversation
        fields = [
            'id',
            'merchant',
            'status',
            'buyer_session_id',
            'current_product',
            'product_name',
            'current_intent',
            'current_price',
            'agreed_price',
            'negotiation_round',
            'events',
            'created_at',
            'updated_at',
        ]


class AgentMessageRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        min_length=1,
        max_length=2000,
        error_messages={
            "blank": "Message cannot be blank.",
            "required": "A message is required.",
        },
    )


# ===========================================================================
# STEP 9 SERIALIZERS — Autonomous AI Buyer Agent
# ===========================================================================

from .models import BuyerAgentProfile, BuyerNegotiationSession, BuyerNegotiationEvent


class BuyerAgentProfileSerializer(serializers.ModelSerializer):
    buyer_session_id = serializers.CharField(required=False, allow_blank=True, max_length=255)
    preferred_price = serializers.DecimalField(required=False, max_digits=12, decimal_places=2)
    maximum_price = serializers.DecimalField(required=False, max_digits=12, decimal_places=2)
    walk_away_price = serializers.DecimalField(required=False, max_digits=12, decimal_places=2)
    price_sensitivity = serializers.CharField(required=False, write_only=True)
    loyalty_tier = serializers.CharField(required=False, write_only=True)
    product = serializers.IntegerField(required=False, write_only=True)
    merchant = serializers.IntegerField(required=False, write_only=True)

    class Meta:
        model = BuyerAgentProfile
        fields = [
            'id',
            'buyer_session_id',
            'name',
            'requirements',
            'budget_min',
            'budget_max',
            'preferred_price',
            'maximum_price',
            'walk_away_price',
            'preferences',
            'negotiation_enabled',
            'maximum_negotiation_rounds',
            'strategy',
            'price_sensitivity',
            'loyalty_tier',
            'product',
            'merchant',
            'created_at',
            'updated_at',
        ]

    def validate(self, attrs):
        import uuid
        from decimal import Decimal

        if not attrs.get('buyer_session_id'):
            attrs['buyer_session_id'] = f"buyer-session-{uuid.uuid4().hex[:8]}"

        price_sensitivity = attrs.pop('price_sensitivity', None)
        attrs.pop('loyalty_tier', None)
        attrs.pop('merchant', None)
        product_id = attrs.pop('product', None)

        if not attrs.get('strategy'):
            if price_sensitivity:
                sens = str(price_sensitivity).upper()
                if sens == 'HIGH':
                    attrs['strategy'] = BuyerAgentProfile.STRATEGY_VALUE_SEEKER
                elif sens == 'LOW':
                    attrs['strategy'] = BuyerAgentProfile.STRATEGY_FAST_BUYER
                else:
                    attrs['strategy'] = BuyerAgentProfile.STRATEGY_BALANCED
            else:
                attrs['strategy'] = BuyerAgentProfile.STRATEGY_BALANCED

        if product_id and not attrs.get('requirements'):
            from products.models import Product
            try:
                prod = Product.objects.get(pk=product_id)
                attrs['requirements'] = [prod.name]
            except Product.DoesNotExist:
                pass

        budget_max = attrs.get('budget_max')
        if budget_max is not None:
            budget_max = Decimal(str(budget_max))
            if attrs.get('budget_min') is None:
                attrs['budget_min'] = Decimal('0.00')
            else:
                attrs['budget_min'] = Decimal(str(attrs['budget_min']))

            if attrs.get('walk_away_price') is None:
                attrs['walk_away_price'] = budget_max
            else:
                attrs['walk_away_price'] = Decimal(str(attrs['walk_away_price']))

            if attrs.get('maximum_price') is None:
                attrs['maximum_price'] = min(budget_max, attrs['walk_away_price'])
            else:
                attrs['maximum_price'] = Decimal(str(attrs['maximum_price']))

            if attrs.get('preferred_price') is None:
                strategy = attrs.get('strategy', BuyerAgentProfile.STRATEGY_BALANCED)
                if strategy == BuyerAgentProfile.STRATEGY_VALUE_SEEKER:
                    factor = Decimal('0.80')
                elif strategy == BuyerAgentProfile.STRATEGY_FAST_BUYER:
                    factor = Decimal('0.90')
                else:
                    factor = Decimal('0.85')
                calc_pref = (attrs['maximum_price'] * factor).quantize(Decimal('0.01'))
                attrs['preferred_price'] = max(attrs['budget_min'], min(calc_pref, attrs['maximum_price']))
            else:
                attrs['preferred_price'] = Decimal(str(attrs['preferred_price']))

        return attrs


class CreateBuyerSessionRequestSerializer(serializers.Serializer):
    buyer_profile_id = serializers.UUIDField(required=True)
    merchant_id = serializers.IntegerField(required=True)


class BuyerNegotiationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuyerNegotiationEvent
        fields = [
            'id',
            'event_type',
            'actor',
            'message',
            'offered_price',
            'decision',
            'metadata',
            'created_at',
        ]


class BuyerNegotiationSessionSerializer(serializers.ModelSerializer):
    events = BuyerNegotiationEventSerializer(many=True, read_only=True)
    buyer_profile = BuyerAgentProfileSerializer(read_only=True)
    product_name = serializers.ReadOnlyField(source='product.name')

    class Meta:
        model = BuyerNegotiationSession
        fields = [
            'id',
            'buyer_profile',
            'merchant',
            'product',
            'product_name',
            'status',
            'current_offer',
            'buyer_last_offer',
            'agreed_price',
            'negotiation_round',
            'events',
            'created_at',
            'updated_at',
        ]


class OfferEvaluationRequestSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(required=True)
    merchant_offer = serializers.DecimalField(required=True, max_digits=12, decimal_places=2)


# ===========================================================================
# STEP 10 SERIALIZERS — Autonomous AI-to-AI Commerce Negotiation
# ===========================================================================

from .models import AgentNegotiation, AgentNegotiationEvent


class CreateAgentNegotiationSerializer(serializers.Serializer):
    buyer_profile_id = serializers.UUIDField(required=True)
    merchant_id = serializers.IntegerField(required=True)
    product_id = serializers.IntegerField(required=False, allow_null=True)


class RunAgentNegotiationSerializer(serializers.Serializer):
    max_steps = serializers.IntegerField(required=False, default=10, min_value=1, max_value=50)


class AgentNegotiationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentNegotiationEvent
        fields = [
            'id',
            'round_number',
            'actor',
            'event_type',
            'proposed_price',
            'decision',
            'message',
            'metadata',
            'created_at',
        ]


class AgentNegotiationSerializer(serializers.ModelSerializer):
    events = AgentNegotiationEventSerializer(many=True, read_only=True)
    buyer_profile = BuyerAgentProfileSerializer(read_only=True)
    product_name = serializers.ReadOnlyField(source='product.name')

    class Meta:
        model = AgentNegotiation
        fields = [
            'id',
            'buyer_profile',
            'merchant',
            'product',
            'product_name',
            'status',
            'current_price',
            'buyer_last_offer',
            'merchant_last_offer',
            'negotiation_round',
            'max_rounds',
            'agreed_price',
            'payment_ready',
            'termination_reason',
            'events',
            'created_at',
            'updated_at',
        ]




