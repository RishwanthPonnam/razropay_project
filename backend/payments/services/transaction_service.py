import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ai.models import AgentNegotiation
from payments.models import PaymentTransaction
from payments.services.razorpay_adapter import RazorpayAdapter
from payments.services.transaction_validator import TransactionValidator

class TransactionService:
    """Service handling creation and retrieval of Razorpay payment transactions.
    Ensures idempotency, correct amount handling, and atomicity.
    """

    def __init__(self):
        self.adapter = RazorpayAdapter()

    def _amount_to_minor(self, amount: Decimal) -> int:
        """Convert Decimal amount (e.g., 123.45) to integer minor units (paise).
        Uses quantize to avoid floating point errors.
        """
        # Ensure two decimal places
        quantized = amount.quantize(Decimal('0.01'))
        return int(quantized * 100)

    @transaction.atomic
    def create_or_get_transaction(self, negotiation_id: uuid.UUID) -> PaymentTransaction:
        """Create a PaymentTransaction for a given negotiation.
        If a transaction already exists and is beyond the CREATED state, it is returned.
        """
        try:
            negotiation = AgentNegotiation.objects.select_for_update().get(id=negotiation_id)
        except AgentNegotiation.DoesNotExist:
            raise ValidationError('Negotiation not found.')

        # Validate prerequisites
        validator = TransactionValidator(negotiation)
        existing = validator.validate()
        if existing:
            return existing

        # Compute amount in minor units
        amount_minor = self._amount_to_minor(negotiation.agreed_price)
        receipt = f"order_{negotiation.id}"  # simple receipt identifier

        # Create Razorpay order via adapter
        order_data = self.adapter.create_order(
            amount_minor_units=amount_minor,
            currency='INR',
            receipt=receipt,
            notes={'negotiation_id': str(negotiation.id)}
        )

        # Persist PaymentTransaction
        transaction_obj = PaymentTransaction.objects.create(
            negotiation=negotiation,
            merchant=negotiation.merchant,
            product=negotiation.product,
            agreed_amount=negotiation.agreed_price,
            currency='INR',
            razorpay_order_id=order_data['id'],
            status=PaymentTransaction.STATUS_ORDER_CREATED,
            amount_minor_units=amount_minor,
            receipt=receipt,
            metadata={'order_created_at': timezone.now().isoformat()},
        )
        return transaction_obj

    def get_transaction(self, transaction_id: uuid.UUID) -> PaymentTransaction:
        """Retrieve a transaction by its UUID."""
        return PaymentTransaction.objects.get(id=transaction_id)
