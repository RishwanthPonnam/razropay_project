import uuid
from django.db import models


class PaymentTransaction(models.Model):
    """
    Stateful execution model for Razorpay Test-Mode transactions originating
    from an agreed AI-to-AI commercial negotiation.
    """
    STATUS_CREATED          = 'CREATED'
    STATUS_ORDER_CREATED    = 'ORDER_CREATED'
    STATUS_PAYMENT_PENDING  = 'PAYMENT_PENDING'
    STATUS_PAYMENT_CAPTURED = 'PAYMENT_CAPTURED'
    STATUS_PAYMENT_FAILED   = 'PAYMENT_FAILED'
    STATUS_EXPIRED          = 'EXPIRED'

    STATUS_CHOICES = [
        (STATUS_CREATED,          'Created'),
        (STATUS_ORDER_CREATED,    'Order Created'),
        (STATUS_PAYMENT_PENDING,  'Payment Pending'),
        (STATUS_PAYMENT_CAPTURED, 'Payment Captured'),
        (STATUS_PAYMENT_FAILED,   'Payment Failed'),
        (STATUS_EXPIRED,          'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    negotiation = models.OneToOneField(
        'ai.AgentNegotiation',
        on_delete=models.PROTECT,
        related_name='payment_transaction'
    )
    merchant = models.ForeignKey(
        'merchants.Merchant',
        on_delete=models.CASCADE,
        related_name='payment_transactions'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='payment_transactions'
    )
    agreed_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    razorpay_order_id = models.CharField(max_length=255, db_index=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_CREATED
    )
    amount_minor_units = models.IntegerField()
    receipt = models.CharField(max_length=255)
    payment_verified = models.BooleanField(default=False)
    failure_reason = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PaymentTransaction {self.id} [{self.status}] - Order {self.razorpay_order_id}"
