import uuid
from django.core.exceptions import ValidationError
from django.db import models


class CommerceConversation(models.Model):
    """
    Stores persistent state for a buyer-merchant commerce agent session.
    """
    STATUS_ACTIVE          = 'ACTIVE'
    STATUS_OFFERED         = 'OFFERED'
    STATUS_COUNTER_OFFERED = 'COUNTER_OFFERED'
    STATUS_ACCEPTED        = 'ACCEPTED'
    STATUS_REJECTED        = 'REJECTED'
    STATUS_EXPIRED         = 'EXPIRED'

    STATUS_CHOICES = [
        (STATUS_ACTIVE,          'Active'),
        (STATUS_OFFERED,         'Offered'),
        (STATUS_COUNTER_OFFERED, 'Counter Offered'),
        (STATUS_ACCEPTED,        'Accepted'),
        (STATUS_REJECTED,        'Rejected'),
        (STATUS_EXPIRED,         'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        'merchants.Merchant',
        on_delete=models.CASCADE,
        related_name='conversations'
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE
    )
    buyer_session_id = models.CharField(max_length=255, blank=True, default='')
    current_product = models.ForeignKey(
        'products.Product',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='conversations'
    )
    current_intent = models.JSONField(null=True, blank=True, default=dict)
    current_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    agreed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    negotiation_round = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation {self.id} [{self.status}] - Merchant {self.merchant_id}"


class CommerceEvent(models.Model):
    """
    Append-only audit log of events during a CommerceConversation negotiation.
    """
    EVENT_BUYER_MESSAGE  = 'BUYER_MESSAGE'
    EVENT_AGENT_MESSAGE  = 'AGENT_MESSAGE'
    EVENT_OFFER          = 'OFFER'
    EVENT_COUNTER_OFFER  = 'COUNTER_OFFER'
    EVENT_DECISION       = 'DECISION'
    EVENT_ACCEPTANCE     = 'ACCEPTANCE'
    EVENT_REJECTION      = 'REJECTION'
    EVENT_SYSTEM_EVENT   = 'SYSTEM_EVENT'

    EVENT_TYPE_CHOICES = [
        (EVENT_BUYER_MESSAGE,  'Buyer Message'),
        (EVENT_AGENT_MESSAGE,  'Agent Message'),
        (EVENT_OFFER,          'Offer'),
        (EVENT_COUNTER_OFFER,  'Counter Offer'),
        (EVENT_DECISION,       'Decision'),
        (EVENT_ACCEPTANCE,     'Acceptance'),
        (EVENT_REJECTION,      'Rejection'),
        (EVENT_SYSTEM_EVENT,   'System Event'),
    ]

    ACTOR_BUYER  = 'BUYER'
    ACTOR_AGENT  = 'AGENT'
    ACTOR_SYSTEM = 'SYSTEM'

    ACTOR_CHOICES = [
        (ACTOR_BUYER,  'Buyer'),
        (ACTOR_AGENT,  'Agent'),
        (ACTOR_SYSTEM, 'System'),
    ]

    conversation = models.ForeignKey(
        CommerceConversation,
        on_delete=models.CASCADE,
        related_name='events'
    )
    event_type = models.CharField(max_length=32, choices=EVENT_TYPE_CHOICES)
    actor = models.CharField(max_length=32, choices=ACTOR_CHOICES)
    message = models.TextField(blank=True, default='')
    proposed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    selected_action = models.CharField(max_length=64, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Event {self.id} [{self.event_type}] by {self.actor} in {self.conversation_id}"


# ===========================================================================
# STEP 9 MODELS — Autonomous AI Buyer Agent Domain
# ===========================================================================

class BuyerAgentProfile(models.Model):
    """
    Persistent profile & strategy configuration for an Autonomous AI Buyer Agent.
    """
    STRATEGY_VALUE_SEEKER = 'VALUE_SEEKER'
    STRATEGY_BALANCED     = 'BALANCED'
    STRATEGY_FAST_BUYER   = 'FAST_BUYER'

    STRATEGY_CHOICES = [
        (STRATEGY_VALUE_SEEKER, 'Value Seeker'),
        (STRATEGY_BALANCED,     'Balanced'),
        (STRATEGY_FAST_BUYER,   'Fast Buyer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer_session_id = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=255, default="AI Buyer")
    requirements = models.JSONField(default=list, blank=True)
    budget_min = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    budget_max = models.DecimalField(max_digits=12, decimal_places=2)
    preferred_price = models.DecimalField(max_digits=12, decimal_places=2)
    maximum_price = models.DecimalField(max_digits=12, decimal_places=2)
    walk_away_price = models.DecimalField(max_digits=12, decimal_places=2)
    preferences = models.JSONField(default=list, blank=True)
    negotiation_enabled = models.BooleanField(default=True)
    maximum_negotiation_rounds = models.IntegerField(default=3)
    strategy = models.CharField(
        max_length=32,
        choices=STRATEGY_CHOICES,
        default=STRATEGY_BALANCED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.budget_min < 0:
            raise ValidationError({'budget_min': 'budget_min cannot be negative.'})
        if self.budget_max < 0:
            raise ValidationError({'budget_max': 'budget_max cannot be negative.'})
        if self.preferred_price < 0:
            raise ValidationError({'preferred_price': 'preferred_price cannot be negative.'})
        if self.maximum_price < 0:
            raise ValidationError({'maximum_price': 'maximum_price cannot be negative.'})
        if self.walk_away_price < 0:
            raise ValidationError({'walk_away_price': 'walk_away_price cannot be negative.'})
        if self.maximum_negotiation_rounds < 1:
            raise ValidationError({'maximum_negotiation_rounds': 'maximum_negotiation_rounds must be at least 1.'})
        if self.budget_min > self.preferred_price:
            raise ValidationError({'budget_min': 'budget_min cannot exceed preferred_price.'})
        if self.preferred_price > self.maximum_price:
            raise ValidationError({'preferred_price': 'preferred_price cannot exceed maximum_price.'})
        if self.maximum_price > self.walk_away_price:
            raise ValidationError({'maximum_price': 'maximum_price cannot exceed walk_away_price.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"BuyerProfile {self.id} [{self.name}] ({self.strategy})"


class BuyerNegotiationSession(models.Model):
    """
    Persistent state for an active buyer-side negotiation session against a merchant.
    """
    STATUS_ACTIVE          = 'ACTIVE'
    STATUS_OFFERED         = 'OFFERED'
    STATUS_COUNTER_OFFERED = 'COUNTER_OFFERED'
    STATUS_ACCEPTED        = 'ACCEPTED'
    STATUS_REJECTED        = 'REJECTED'
    STATUS_EXPIRED         = 'EXPIRED'

    STATUS_CHOICES = [
        (STATUS_ACTIVE,          'Active'),
        (STATUS_OFFERED,         'Offered'),
        (STATUS_COUNTER_OFFERED, 'Counter Offered'),
        (STATUS_ACCEPTED,        'Accepted'),
        (STATUS_REJECTED,        'Rejected'),
        (STATUS_EXPIRED,         'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer_profile = models.ForeignKey(
        BuyerAgentProfile,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    merchant = models.ForeignKey(
        'merchants.Merchant',
        on_delete=models.CASCADE,
        related_name='buyer_sessions'
    )
    product = models.ForeignKey(
        'products.Product',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='buyer_sessions'
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE
    )
    current_offer = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    buyer_last_offer = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    agreed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    negotiation_round = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"BuyerSession {self.id} [{self.status}] - Profile {self.buyer_profile_id}"


class BuyerNegotiationEvent(models.Model):
    """
    Append-only audit log of events during a BuyerNegotiationSession.
    """
    EVENT_BUYER_REQUEST  = 'BUYER_REQUEST'
    EVENT_MERCHANT_OFFER = 'MERCHANT_OFFER'
    EVENT_BUYER_OFFER    = 'BUYER_OFFER'
    EVENT_BUYER_DECISION = 'BUYER_DECISION'
    EVENT_COUNTER_OFFER  = 'COUNTER_OFFER'
    EVENT_ACCEPTANCE     = 'ACCEPTANCE'
    EVENT_REJECTION      = 'REJECTION'
    EVENT_SYSTEM_EVENT   = 'SYSTEM_EVENT'

    EVENT_TYPE_CHOICES = [
        (EVENT_BUYER_REQUEST,  'Buyer Request'),
        (EVENT_MERCHANT_OFFER, 'Merchant Offer'),
        (EVENT_BUYER_OFFER,    'Buyer Offer'),
        (EVENT_BUYER_DECISION, 'Buyer Decision'),
        (EVENT_COUNTER_OFFER,  'Counter Offer'),
        (EVENT_ACCEPTANCE,     'Acceptance'),
        (EVENT_REJECTION,      'Rejection'),
        (EVENT_SYSTEM_EVENT,   'System Event'),
    ]

    ACTOR_BUYER    = 'BUYER'
    ACTOR_MERCHANT = 'MERCHANT'
    ACTOR_SYSTEM   = 'SYSTEM'

    ACTOR_CHOICES = [
        (ACTOR_BUYER,    'Buyer'),
        (ACTOR_MERCHANT, 'Merchant'),
        (ACTOR_SYSTEM,   'System'),
    ]

    session = models.ForeignKey(
        BuyerNegotiationSession,
        on_delete=models.CASCADE,
        related_name='events'
    )
    event_type = models.CharField(max_length=32, choices=EVENT_TYPE_CHOICES)
    actor = models.CharField(max_length=32, choices=ACTOR_CHOICES)
    message = models.TextField(blank=True, default='')
    offered_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    decision = models.CharField(max_length=64, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"BuyerEvent {self.id} [{self.event_type}] in session {self.session_id}"


# ===========================================================================
# STEP 10 MODELS — Autonomous AI-to-AI Commerce Negotiation
# ===========================================================================

class AgentNegotiation(models.Model):
    """
    Persistent state for an autonomous AI Buyer ↔ AI Merchant negotiation.
    """
    STATUS_ACTIVE        = 'ACTIVE'
    STATUS_BUYER_TURN    = 'BUYER_TURN'
    STATUS_MERCHANT_TURN = 'MERCHANT_TURN'
    STATUS_AGREED        = 'AGREED'
    STATUS_REJECTED      = 'REJECTED'
    STATUS_EXPIRED       = 'EXPIRED'

    STATUS_CHOICES = [
        (STATUS_ACTIVE,        'Active'),
        (STATUS_BUYER_TURN,    'Buyer Turn'),
        (STATUS_MERCHANT_TURN, 'Merchant Turn'),
        (STATUS_AGREED,        'Agreed'),
        (STATUS_REJECTED,      'Rejected'),
        (STATUS_EXPIRED,       'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer_profile = models.ForeignKey(
        BuyerAgentProfile,
        on_delete=models.CASCADE,
        related_name='ai_negotiations'
    )
    merchant = models.ForeignKey(
        'merchants.Merchant',
        on_delete=models.CASCADE,
        related_name='ai_negotiations'
    )
    product = models.ForeignKey(
        'products.Product',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ai_negotiations'
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE
    )
    current_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    buyer_last_offer = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    merchant_last_offer = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    negotiation_round = models.IntegerField(default=0)
    max_rounds = models.IntegerField(default=3)
    agreed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_ready = models.BooleanField(default=False)
    termination_reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"AgentNegotiation {self.id} [{self.status}] - Round {self.negotiation_round}"


class AgentNegotiationEvent(models.Model):
    """
    Append-only audit log of events in an AgentNegotiation.
    """
    ACTOR_AI_BUYER    = 'AI_BUYER'
    ACTOR_AI_MERCHANT = 'AI_MERCHANT'
    ACTOR_SYSTEM      = 'SYSTEM'

    ACTOR_CHOICES = [
        (ACTOR_AI_BUYER,    'AI Buyer'),
        (ACTOR_AI_MERCHANT, 'AI Merchant'),
        (ACTOR_SYSTEM,      'System'),
    ]

    EVENT_NEGOTIATION_STARTED = 'NEGOTIATION_STARTED'
    EVENT_PRODUCT_SELECTED    = 'PRODUCT_SELECTED'
    EVENT_MERCHANT_OFFER      = 'MERCHANT_OFFER'
    EVENT_BUYER_COUNTER       = 'BUYER_COUNTER'
    EVENT_BUYER_ACCEPT        = 'BUYER_ACCEPT'
    EVENT_BUYER_REJECT        = 'BUYER_REJECT'
    EVENT_MERCHANT_COUNTER    = 'MERCHANT_COUNTER'
    EVENT_MERCHANT_ACCEPT     = 'MERCHANT_ACCEPT'
    EVENT_MERCHANT_REJECT     = 'MERCHANT_REJECT'
    EVENT_AGREEMENT_REACHED   = 'AGREEMENT_REACHED'
    EVENT_NEGOTIATION_ENDED   = 'NEGOTIATION_ENDED'
    EVENT_SYSTEM_EVENT        = 'SYSTEM_EVENT'

    EVENT_TYPE_CHOICES = [
        (EVENT_NEGOTIATION_STARTED, 'Negotiation Started'),
        (EVENT_PRODUCT_SELECTED,    'Product Selected'),
        (EVENT_MERCHANT_OFFER,      'Merchant Offer'),
        (EVENT_BUYER_COUNTER,       'Buyer Counter'),
        (EVENT_BUYER_ACCEPT,        'Buyer Accept'),
        (EVENT_BUYER_REJECT,        'Buyer Reject'),
        (EVENT_MERCHANT_COUNTER,    'Merchant Counter'),
        (EVENT_MERCHANT_ACCEPT,     'Merchant Accept'),
        (EVENT_MERCHANT_REJECT,     'Merchant Reject'),
        (EVENT_AGREEMENT_REACHED,   'Agreement Reached'),
        (EVENT_NEGOTIATION_ENDED,   'Negotiation Ended'),
        (EVENT_SYSTEM_EVENT,        'System Event'),
    ]

    negotiation = models.ForeignKey(
        AgentNegotiation,
        on_delete=models.CASCADE,
        related_name='events'
    )
    round_number = models.IntegerField(default=0)
    actor = models.CharField(max_length=32, choices=ACTOR_CHOICES)
    event_type = models.CharField(max_length=32, choices=EVENT_TYPE_CHOICES)
    proposed_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    decision = models.CharField(max_length=64, blank=True, default='')
    message = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"NegotiationEvent {self.id} [{self.event_type}] by {self.actor} in {self.negotiation_id}"

