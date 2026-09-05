import json
import logging

from django.db import transaction

from payments.models import PaymentTransaction
from payments.services.razorpay_adapter import RazorpayAdapter

logger = logging.getLogger(__name__)


class PaymentVerificationService:
    """Handles Razorpay payment signature verification (checkout flow)
    and webhook-based state transitions.
    Inventory is ONLY decremented on PAYMENT_CAPTURED.
    """

    def __init__(self):
        self.adapter = RazorpayAdapter()

    # ------------------------------------------------------------------
    # Checkout-flow verification (client calls back after payment)
    # ------------------------------------------------------------------
    @transaction.atomic
    def verify_and_capture(self, payment_transaction: PaymentTransaction,
                           razorpay_payment_id: str,
                           razorpay_signature: str) -> bool:
        """Verify Razorpay signature after checkout and finalize the
        transaction if valid.  Decrements inventory on capture.
        Returns True on success, False if verification fails.
        """
        if payment_transaction.status not in (
            PaymentTransaction.STATUS_ORDER_CREATED,
            PaymentTransaction.STATUS_PAYMENT_PENDING,
        ):
            logger.warning(
                "Verify called on transaction %s with invalid status %s",
                payment_transaction.id, payment_transaction.status,
            )
            return False

        is_valid = self.adapter.verify_payment_signature(
            razorpay_order_id=payment_transaction.razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
        )

        if is_valid:
            payment_transaction.razorpay_payment_id = razorpay_payment_id
            payment_transaction.razorpay_signature = razorpay_signature
            payment_transaction.payment_verified = True
            payment_transaction.status = PaymentTransaction.STATUS_PAYMENT_CAPTURED
            payment_transaction.save()
            # Decrement inventory ONLY on successful capture
            self._decrement_inventory(payment_transaction)
            return True
        else:
            payment_transaction.razorpay_payment_id = razorpay_payment_id
            payment_transaction.status = PaymentTransaction.STATUS_PAYMENT_FAILED
            payment_transaction.failure_reason = 'Signature verification failed'
            payment_transaction.save()
            return False

    # ------------------------------------------------------------------
    # Webhook handler
    # ------------------------------------------------------------------
    def handle_webhook(self, payload: bytes, signature: str) -> bool:
        """Process Razorpay webhook events (payment.captured / payment.failed).
        1. Verify webhook signature.
        2. Extract event + payment details.
        3. Transition the PaymentTransaction to the correct state.
        4. Decrement inventory only on capture.
        Returns True if processed successfully, False otherwise.
        """
        # 1. Verify webhook signature
        if not self.adapter.verify_webhook_signature(payload, signature):
            logger.warning("Webhook signature verification failed.")
            return False

        # 2. Parse payload
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            logger.error("Webhook payload is not valid JSON.")
            return False

        event = data.get('event', '')
        payment_entity = (
            data.get('payload', {})
                .get('payment', {})
                .get('entity', {})
        )
        razorpay_order_id = payment_entity.get('order_id', '')
        razorpay_payment_id = payment_entity.get('id', '')

        if not razorpay_order_id:
            logger.warning("Webhook missing order_id in payload.")
            return False

        # 3. Find the matching transaction
        try:
            txn = PaymentTransaction.objects.select_for_update().get(
                razorpay_order_id=razorpay_order_id
            )
        except PaymentTransaction.DoesNotExist:
            logger.warning("No transaction found for order_id %s", razorpay_order_id)
            return False

        # 4. State transition based on event type
        if event == 'payment.captured':
            if txn.status in (
                PaymentTransaction.STATUS_ORDER_CREATED,
                PaymentTransaction.STATUS_PAYMENT_PENDING,
            ):
                txn.razorpay_payment_id = razorpay_payment_id
                txn.payment_verified = True
                txn.status = PaymentTransaction.STATUS_PAYMENT_CAPTURED
                txn.save()
                self._decrement_inventory(txn)
                return True
            else:
                logger.info("Transaction %s already in status %s, skipping.", txn.id, txn.status)
                return True  # idempotent — already captured

        elif event == 'payment.failed':
            if txn.status not in (PaymentTransaction.STATUS_PAYMENT_CAPTURED,):
                txn.razorpay_payment_id = razorpay_payment_id
                txn.status = PaymentTransaction.STATUS_PAYMENT_FAILED
                txn.failure_reason = payment_entity.get('error_description', 'Payment failed')
                txn.save()
            return True

        logger.info("Unhandled webhook event: %s", event)
        return True  # acknowledge but no action

    # ------------------------------------------------------------------
    # Inventory management
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def _decrement_inventory(payment_transaction: PaymentTransaction):
        """Decrement the product inventory by 1 after successful capture.
        Uses select_for_update to prevent race conditions.
        """
        product = payment_transaction.product
        if product is None:
            return
        from products.models import Product
        prod = Product.objects.select_for_update().get(id=product.id)
        if prod.inventory_quantity >= 1:
            prod.inventory_quantity -= 1
            prod.save()
        else:
            logger.warning(
                "Product %s inventory already 0 at capture time for transaction %s",
                prod.id, payment_transaction.id,
            )
