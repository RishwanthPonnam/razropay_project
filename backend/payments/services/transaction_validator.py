from decimal import Decimal
from django.core.exceptions import ValidationError
from ai.models import AgentNegotiation
from payments.models import PaymentTransaction

class TransactionValidator:
    """Validate prerequisites for creating a Razorpay transaction.
    Ensures the negotiation is in AGREED state, payment_ready flag is True,
    and the amount matches the agreed_price. Also checks inventory availability.
    """

    def __init__(self, negotiation: AgentNegotiation):
        self.negotiation = negotiation

    def validate(self):
        # 1. Negotiation status must be AGREED
        if self.negotiation.status != AgentNegotiation.STATUS_AGREED:
            raise ValidationError('Negotiation is not in AGREED state.')
        # 2. payment_ready flag must be True
        if not getattr(self.negotiation, 'payment_ready', False):
            raise ValidationError('Negotiation is not marked payment_ready.')
        # 3. Agreed amount must be present and positive
        if not self.negotiation.agreed_price or self.negotiation.agreed_price <= Decimal('0'):
            raise ValidationError('Negotiation has invalid agreed_price.')
        # 4. Ensure product inventory is sufficient (do not decrement yet)
        product = self.negotiation.product
        if product and product.inventory_quantity < 1:
            raise ValidationError('Product inventory insufficient for transaction.')
        # 5. Ensure no existing successful transaction for this negotiation
        existing = getattr(self.negotiation, 'payment_transaction', None)
        if existing and existing.status in [PaymentTransaction.STATUS_PAYMENT_CAPTURED, PaymentTransaction.STATUS_ORDER_CREATED, PaymentTransaction.STATUS_PAYMENT_PENDING]:
            # Idempotent: we allow reuse of existing transaction
            return existing
        return None
