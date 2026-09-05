"""
URL patterns for the ai app.
Mounted at /api/ by the root URLconf.
"""

from django.urls import path

from .views import (
    AgentConversationDetailView,
    AgentConversationView,
    AgentMessageView,
    AgentNegotiationCreateView,
    AgentNegotiationDetailView,
    AgentNegotiationRunView,
    BuyerOfferEvaluationView,
    BuyerProfileView,
    BuyerSessionDetailView,
    BuyerSessionView,
    DecisionView,
    IntentView,
    OpportunityView,
)

urlpatterns = [
    path("ai/intent/",        IntentView.as_view(),       name="ai-intent"),
    path("ai/opportunities/", OpportunityView.as_view(),  name="ai-opportunities"),
    path("ai/decision/",      DecisionView.as_view(),     name="ai-decision"),

    # Step 8 Commerce Agent Endpoints
    path("ai/agent/conversations/",
         AgentConversationView.as_view(),
         name="ai-agent-conversations-list-create"),
    path("ai/agent/conversations/<uuid:conversation_id>/",
         AgentConversationDetailView.as_view(),
         name="ai-agent-conversations-detail"),
    path("ai/agent/conversations/<uuid:conversation_id>/messages/",
         AgentMessageView.as_view(),
         name="ai-agent-conversations-messages"),

    # Step 9 AI Buyer Agent Endpoints
    path("ai/buyer/profiles/",
         BuyerProfileView.as_view(),
         name="ai-buyer-profiles"),
    path("ai/buyer/sessions/",
         BuyerSessionView.as_view(),
         name="ai-buyer-sessions"),
    path("ai/buyer/sessions/<uuid:session_id>/",
         BuyerSessionDetailView.as_view(),
         name="ai-buyer-sessions-detail"),
    path("ai/buyer/sessions/<uuid:session_id>/offers/",
         BuyerOfferEvaluationView.as_view(),
         name="ai-buyer-sessions-offers"),

    # Step 10 Autonomous AI Buyer ↔ AI Merchant Negotiation Endpoints
    path("ai/negotiations/",
         AgentNegotiationCreateView.as_view(),
         name="ai-negotiations-create"),
    path("ai/negotiations/<uuid:negotiation_id>/run/",
         AgentNegotiationRunView.as_view(),
         name="ai-negotiations-run"),
    path("ai/negotiations/<uuid:negotiation_id>/",
         AgentNegotiationDetailView.as_view(),
         name="ai-negotiations-detail"),
]



