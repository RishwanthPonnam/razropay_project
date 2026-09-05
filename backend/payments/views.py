from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404

from .serializers import (
    TransactionCreateSerializer,
    TransactionDetailSerializer,
    TransactionVerifySerializer,
)
from .models import PaymentTransaction
from payments.services.transaction_service import TransactionService
from payments.services.payment_verification import PaymentVerificationService


class TransactionCreateView(APIView):
    """POST /api/payments/transactions/
    Create a Razorpay order for an agreed negotiation.
    Idempotent: if an order already exists for the negotiation it is returned.
    Never exposes RAZORPAY_KEY_SECRET or product cost_price.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        txns = PaymentTransaction.objects.select_related('negotiation', 'product', 'merchant').all()
        merchant_id = request.query_params.get("merchant_id")
        if merchant_id:
            txns = txns.filter(merchant_id=merchant_id)
        data = TransactionDetailSerializer(txns, many=True).data
        for item in data:
            item['razorpay_key_id'] = settings.RAZORPAY_KEY_ID
        return Response(data)

    def post(self, request, *args, **kwargs):
        serializer = TransactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        negotiation_id = serializer.validated_data['negotiation_id']
        try:
            service = TransactionService()
            transaction = service.create_or_get_transaction(negotiation_id)
        except ValidationError as e:
            return Response(
                {'error': str(e.message if hasattr(e, 'message') else e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        output = TransactionDetailSerializer(transaction).data
        # Include razorpay_key_id (public key — safe to expose) for client checkout
        output['razorpay_key_id'] = settings.RAZORPAY_KEY_ID
        return Response(output, status=status.HTTP_201_CREATED)


class TransactionDetailView(APIView):
    """GET /api/payments/transactions/<id>/
    Return transaction status. Never leaks secrets.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, transaction_id, *args, **kwargs):
        txn = get_object_or_404(PaymentTransaction, id=transaction_id)
        data = TransactionDetailSerializer(txn).data
        data['razorpay_key_id'] = settings.RAZORPAY_KEY_ID
        return Response(data)


class TransactionVerifyView(APIView):
    """POST /api/payments/transactions/<id>/verify/
    Verify Razorpay payment signature after checkout.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, transaction_id, *args, **kwargs):
        txn = get_object_or_404(PaymentTransaction, id=transaction_id)
        serializer = TransactionVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = PaymentVerificationService()
        verified = service.verify_and_capture(
            txn,
            serializer.validated_data['razorpay_payment_id'],
            serializer.validated_data['razorpay_signature'],
        )
        if verified:
            txn.refresh_from_db()
            return Response(
                TransactionDetailSerializer(txn).data,
                status=status.HTTP_200_OK,
            )
        txn.refresh_from_db()
        return Response(
            {'error': 'Payment verification failed',
             'transaction': TransactionDetailSerializer(txn).data},
            status=status.HTTP_400_BAD_REQUEST,
        )


class RazorpayWebhookView(APIView):
    """POST /api/payments/webhooks/razorpay/
    Receives async updates from Razorpay. Secured by webhook signature.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        payload = request.body
        signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE', '')
        service = PaymentVerificationService()
        service.handle_webhook(payload, signature)
        # Always return 200 to Razorpay to prevent retries
        return Response(status=status.HTTP_200_OK)
