from rest_framework import serializers
from payments.models import PaymentTransaction

class TransactionCreateSerializer(serializers.Serializer):
    negotiation_id = serializers.UUIDField()

class TransactionDetailSerializer(serializers.ModelSerializer):
    negotiation_id = serializers.UUIDField(source='negotiation.id', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    buyer_name = serializers.CharField(source='negotiation.buyer_profile.name', read_only=True, default='')
    merchant_id = serializers.IntegerField(source='merchant.id', read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'negotiation_id', 'product_name', 'buyer_name', 'merchant_id',
            'agreed_amount', 'status', 'amount_minor_units', 'currency',
            'razorpay_order_id', 'razorpay_payment_id', 'receipt',
            'payment_verified', 'failure_reason', 'created_at', 'updated_at'
        ]

class TransactionVerifySerializer(serializers.Serializer):
    razorpay_payment_id = serializers.CharField()
    razorpay_signature = serializers.CharField()
