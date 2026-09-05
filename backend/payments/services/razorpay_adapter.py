import hmac
import hashlib
import razorpay
from django.conf import settings


class RazorpayAdapter:
    """Thin wrapper around Razorpay SDK for test mode.
    Isolates third-party calls so the rest of the codebase never touches
    the SDK directly, making it trivial to mock in unit tests.
    """

    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
        self.client.set_app_details({"title": "Merchant OS AI", "version": "1.0"})

    # ------------------------------------------------------------------
    # Order
    # ------------------------------------------------------------------
    def create_order(self, amount_minor_units: int, currency: str = "INR",
                     receipt: str = "order_rcpt_1", notes: dict = None) -> dict:
        """Create a Razorpay order.
        Args:
            amount_minor_units: Amount in paise (e.g., 1000 = INR 10.00).
            currency: Currency code, default INR.
            receipt: Unique receipt identifier.
            notes: Optional dict of notes.
        Returns:
            dict with order response containing 'id', 'amount', etc.
        """
        data = {
            "amount": amount_minor_units,
            "currency": currency,
            "receipt": receipt,
            "payment_capture": 1,  # auto-capture on successful payment
        }
        if notes:
            data["notes"] = notes
        try:
            return self.client.order.create(data)
        except razorpay.errors.BadRequestError as e:
            if "Authentication failed" in str(e):
                from django.core.exceptions import ValidationError
                raise ValidationError("Razorpay Test Mode credentials are not configured.")
            raise

    # ------------------------------------------------------------------
    # Payment signature verification (checkout flow)
    # ------------------------------------------------------------------
    def verify_payment_signature(self, razorpay_order_id: str,
                                 razorpay_payment_id: str,
                                 razorpay_signature: str) -> bool:
        """Validate Razorpay payment signature using the key secret.
        Returns True if signature is valid, False otherwise.
        """
        try:
            self.client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            })
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    # ------------------------------------------------------------------
    # Webhook signature verification
    # ------------------------------------------------------------------
    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Validate a Razorpay webhook payload signature.
        Uses HMAC-SHA256 with the webhook secret.
        Returns True if valid, False otherwise.
        """
        try:
            self.client.utility.verify_webhook_signature(
                body.decode('utf-8') if isinstance(body, bytes) else body,
                signature,
                self.webhook_secret
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False
