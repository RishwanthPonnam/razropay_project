"""
URL patterns for the payments app.
Mounted at /api/ by the root URLconf.
"""

from django.urls import path

from .views import (
    TransactionCreateView,
    TransactionDetailView,
    TransactionVerifyView,
    RazorpayWebhookView,
)

urlpatterns = [
    # Step 11 — Razorpay Test-Mode Transaction Execution
    path("payments/transactions/",
         TransactionCreateView.as_view(),
         name="payments-transaction-create"),
    path("payments/transactions/<uuid:transaction_id>/",
         TransactionDetailView.as_view(),
         name="payments-transaction-detail"),
    path("payments/transactions/<uuid:transaction_id>/verify/",
         TransactionVerifyView.as_view(),
         name="payments-transaction-verify"),
    path("payments/webhooks/razorpay/",
         RazorpayWebhookView.as_view(),
         name="payments-webhook-razorpay"),
]
