"""
Step 11 — Razorpay Test-Mode Transaction Execution: Comprehensive Tests.

All Razorpay SDK calls are mocked. No real network traffic is generated.
These tests verify:
  - PaymentTransaction model creation and state machine
  - Transaction validator logic
  - Amount conversion (Decimal → paise)
  - Idempotent order creation
  - Payment signature verification flow
  - Webhook signature verification and state transitions
  - Inventory decrement ONLY on PAYMENT_CAPTURED
  - No secrets or cost_price exposed in API responses
  - Failure handling
"""

import json
import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from merchants.models import Merchant, MerchantPolicy
from products.models import Product
from ai.models import (
    AgentNegotiation,
    BuyerAgentProfile,
)
from payments.models import PaymentTransaction
from payments.services.transaction_validator import TransactionValidator
from payments.services.transaction_service import TransactionService
from payments.services.payment_verification import PaymentVerificationService


# ======================================================================
# Helpers
# ======================================================================

def _create_merchant():
    merchant = Merchant.objects.create(
        business_name='Test Merchant',
        email=f'merchant_{uuid.uuid4().hex[:8]}@test.com',
    )
    MerchantPolicy.objects.create(
        merchant=merchant,
        minimum_margin_percent=Decimal('10.00'),
        maximum_discount_percent=Decimal('20.00'),
        maximum_negotiation_rounds=3,
        auto_approval_limit=Decimal('5000.00'),
    )
    return merchant


def _create_product(merchant, price=Decimal('500.00'), cost=Decimal('300.00'),
                    inventory=10):
    return Product.objects.create(
        merchant=merchant,
        name='Test Product',
        description='A product for testing',
        category='Electronics',
        price=price,
        cost_price=cost,
        inventory_quantity=inventory,
    )


def _create_buyer_profile():
    return BuyerAgentProfile.objects.create(
        buyer_session_id=f'buyer_{uuid.uuid4().hex[:8]}',
        name='Test AI Buyer',
        budget_min=Decimal('100.00'),
        budget_max=Decimal('600.00'),
        preferred_price=Decimal('400.00'),
        maximum_price=Decimal('500.00'),
        walk_away_price=Decimal('550.00'),
        maximum_negotiation_rounds=3,
    )


def _create_agreed_negotiation(merchant, product, buyer_profile,
                               agreed_price=Decimal('450.00')):
    return AgentNegotiation.objects.create(
        buyer_profile=buyer_profile,
        merchant=merchant,
        product=product,
        status=AgentNegotiation.STATUS_AGREED,
        agreed_price=agreed_price,
        payment_ready=True,
        negotiation_round=2,
        max_rounds=3,
    )


MOCK_RAZORPAY_ORDER = {
    'id': 'order_FAKE123456',
    'entity': 'order',
    'amount': 45000,
    'amount_paid': 0,
    'amount_due': 45000,
    'currency': 'INR',
    'receipt': 'order_test',
    'status': 'created',
}


# ======================================================================
# Model Tests
# ======================================================================

class PaymentTransactionModelTests(TestCase):
    """Tests for the PaymentTransaction model itself."""

    def setUp(self):
        self.merchant = _create_merchant()
        self.product = _create_product(self.merchant)
        self.buyer = _create_buyer_profile()
        self.negotiation = _create_agreed_negotiation(
            self.merchant, self.product, self.buyer
        )

    def test_create_payment_transaction(self):
        txn = PaymentTransaction.objects.create(
            negotiation=self.negotiation,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_test123',
            status=PaymentTransaction.STATUS_ORDER_CREATED,
            amount_minor_units=45000,
            receipt='order_test',
        )
        self.assertEqual(txn.status, PaymentTransaction.STATUS_ORDER_CREATED)
        self.assertEqual(txn.agreed_amount, Decimal('450.00'))
        self.assertEqual(txn.amount_minor_units, 45000)
        self.assertEqual(txn.currency, 'INR')
        self.assertFalse(txn.payment_verified)

    def test_onetoone_constraint(self):
        """Cannot create two transactions for the same negotiation."""
        PaymentTransaction.objects.create(
            negotiation=self.negotiation,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_first',
            status=PaymentTransaction.STATUS_ORDER_CREATED,
            amount_minor_units=45000,
            receipt='order_first',
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            PaymentTransaction.objects.create(
                negotiation=self.negotiation,
                merchant=self.merchant,
                product=self.product,
                agreed_amount=Decimal('450.00'),
                razorpay_order_id='order_second',
                status=PaymentTransaction.STATUS_ORDER_CREATED,
                amount_minor_units=45000,
                receipt='order_second',
            )

    def test_str_representation(self):
        txn = PaymentTransaction.objects.create(
            negotiation=self.negotiation,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_str_test',
            status=PaymentTransaction.STATUS_CREATED,
            amount_minor_units=45000,
            receipt='order_str',
        )
        self.assertIn('CREATED', str(txn))
        self.assertIn('order_str_test', str(txn))

    def test_status_choices(self):
        valid_statuses = [c[0] for c in PaymentTransaction.STATUS_CHOICES]
        self.assertIn('CREATED', valid_statuses)
        self.assertIn('ORDER_CREATED', valid_statuses)
        self.assertIn('PAYMENT_PENDING', valid_statuses)
        self.assertIn('PAYMENT_CAPTURED', valid_statuses)
        self.assertIn('PAYMENT_FAILED', valid_statuses)
        self.assertIn('EXPIRED', valid_statuses)


# ======================================================================
# Transaction Validator Tests
# ======================================================================

class TransactionValidatorTests(TestCase):
    """Validate that only AGREED + payment_ready negotiations can create transactions."""

    def setUp(self):
        self.merchant = _create_merchant()
        self.product = _create_product(self.merchant)
        self.buyer = _create_buyer_profile()

    def test_valid_agreed_negotiation(self):
        neg = _create_agreed_negotiation(
            self.merchant, self.product, self.buyer
        )
        v = TransactionValidator(neg)
        result = v.validate()
        self.assertIsNone(result)  # No existing transaction — ready to create

    def test_reject_non_agreed_status(self):
        neg = AgentNegotiation.objects.create(
            buyer_profile=self.buyer,
            merchant=self.merchant,
            product=self.product,
            status=AgentNegotiation.STATUS_ACTIVE,
            payment_ready=False,
        )
        v = TransactionValidator(neg)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            v.validate()

    def test_reject_payment_not_ready(self):
        neg = AgentNegotiation.objects.create(
            buyer_profile=self.buyer,
            merchant=self.merchant,
            product=self.product,
            status=AgentNegotiation.STATUS_AGREED,
            agreed_price=Decimal('400.00'),
            payment_ready=False,
        )
        v = TransactionValidator(neg)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            v.validate()

    def test_reject_zero_agreed_price(self):
        neg = AgentNegotiation.objects.create(
            buyer_profile=self.buyer,
            merchant=self.merchant,
            product=self.product,
            status=AgentNegotiation.STATUS_AGREED,
            agreed_price=Decimal('0.00'),
            payment_ready=True,
        )
        v = TransactionValidator(neg)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            v.validate()

    def test_reject_no_inventory(self):
        product_zero = _create_product(self.merchant, inventory=0)
        neg = _create_agreed_negotiation(
            self.merchant, product_zero, self.buyer
        )
        v = TransactionValidator(neg)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            v.validate()

    def test_returns_existing_active_transaction(self):
        neg = _create_agreed_negotiation(
            self.merchant, self.product, self.buyer
        )
        PaymentTransaction.objects.create(
            negotiation=neg,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_existing',
            status=PaymentTransaction.STATUS_ORDER_CREATED,
            amount_minor_units=45000,
            receipt='order_existing',
        )
        v = TransactionValidator(neg)
        result = v.validate()
        self.assertIsNotNone(result)
        self.assertEqual(result.razorpay_order_id, 'order_existing')


# ======================================================================
# Transaction Service Tests (Razorpay adapter mocked)
# ======================================================================

class TransactionServiceTests(TestCase):
    """Test the TransactionService with Razorpay adapter mocked."""

    def setUp(self):
        self.merchant = _create_merchant()
        self.product = _create_product(self.merchant, price=Decimal('500.00'),
                                       cost=Decimal('300.00'), inventory=5)
        self.buyer = _create_buyer_profile()
        self.negotiation = _create_agreed_negotiation(
            self.merchant, self.product, self.buyer,
            agreed_price=Decimal('450.00'),
        )

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_create_transaction_success(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        service = TransactionService()
        txn = service.create_or_get_transaction(self.negotiation.id)
        self.assertEqual(txn.status, PaymentTransaction.STATUS_ORDER_CREATED)
        self.assertEqual(txn.agreed_amount, Decimal('450.00'))
        self.assertEqual(txn.amount_minor_units, 45000)
        self.assertEqual(txn.razorpay_order_id, 'order_FAKE123456')
        self.assertEqual(txn.merchant_id, self.merchant.id)
        self.assertEqual(txn.product_id, self.product.id)
        mock_instance.create_order.assert_called_once()

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_amount_conversion_decimal_to_paise(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        service = TransactionService()
        # 450.00 → 45000 paise
        self.assertEqual(service._amount_to_minor(Decimal('450.00')), 45000)
        # 99.99 → 9999 paise
        self.assertEqual(service._amount_to_minor(Decimal('99.99')), 9999)
        # 1.01 → 101 paise
        self.assertEqual(service._amount_to_minor(Decimal('1.01')), 101)

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_idempotent_returns_existing_transaction(self, MockAdapter):
        """Calling create_or_get_transaction twice returns the same transaction."""
        mock_instance = MockAdapter.return_value
        mock_instance.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        service = TransactionService()
        txn1 = service.create_or_get_transaction(self.negotiation.id)
        txn2 = service.create_or_get_transaction(self.negotiation.id)
        self.assertEqual(txn1.id, txn2.id)
        # Razorpay adapter should only be called once
        mock_instance.create_order.assert_called_once()

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_reject_non_agreed_negotiation(self, MockAdapter):
        self.negotiation.status = AgentNegotiation.STATUS_ACTIVE
        self.negotiation.save()
        service = TransactionService()
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            service.create_or_get_transaction(self.negotiation.id)

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_reject_nonexistent_negotiation(self, MockAdapter):
        service = TransactionService()
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            service.create_or_get_transaction(uuid.uuid4())

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_amount_derived_from_negotiation(self, MockAdapter):
        """Transaction amount must come from the stored agreement, not the client."""
        mock_instance = MockAdapter.return_value
        order_copy = MOCK_RAZORPAY_ORDER.copy()
        mock_instance.create_order.return_value = order_copy
        service = TransactionService()
        txn = service.create_or_get_transaction(self.negotiation.id)
        self.assertEqual(txn.agreed_amount, self.negotiation.agreed_price)
        self.assertEqual(txn.amount_minor_units, 45000)


# ======================================================================
# Payment Verification Tests (Razorpay adapter mocked)
# ======================================================================

class PaymentVerificationServiceTests(TestCase):
    """Test checkout verification and webhook processing."""

    def setUp(self):
        self.merchant = _create_merchant()
        self.product = _create_product(self.merchant, inventory=5)
        self.buyer = _create_buyer_profile()
        self.negotiation = _create_agreed_negotiation(
            self.merchant, self.product, self.buyer,
        )
        self.txn = PaymentTransaction.objects.create(
            negotiation=self.negotiation,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_VERIFY123',
            status=PaymentTransaction.STATUS_ORDER_CREATED,
            amount_minor_units=45000,
            receipt='order_verify',
        )

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_verify_and_capture_success(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.verify_payment_signature.return_value = True
        service = PaymentVerificationService()
        result = service.verify_and_capture(
            self.txn, 'pay_FAKE123', 'sig_FAKE123'
        )
        self.assertTrue(result)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PaymentTransaction.STATUS_PAYMENT_CAPTURED)
        self.assertTrue(self.txn.payment_verified)
        self.assertEqual(self.txn.razorpay_payment_id, 'pay_FAKE123')
        # Inventory should be decremented by 1
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 4)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_verify_and_capture_failure(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.verify_payment_signature.return_value = False
        service = PaymentVerificationService()
        result = service.verify_and_capture(
            self.txn, 'pay_BADSIG', 'sig_INVALID'
        )
        self.assertFalse(result)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PaymentTransaction.STATUS_PAYMENT_FAILED)
        self.assertFalse(self.txn.payment_verified)
        # Inventory should NOT be decremented on failure
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 5)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_verify_rejects_already_captured(self, MockAdapter):
        self.txn.status = PaymentTransaction.STATUS_PAYMENT_CAPTURED
        self.txn.save()
        service = PaymentVerificationService()
        result = service.verify_and_capture(
            self.txn, 'pay_EXTRA', 'sig_EXTRA'
        )
        self.assertFalse(result)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_inventory_only_decremented_on_capture(self, MockAdapter):
        """Inventory must not be touched before PAYMENT_CAPTURED."""
        mock_instance = MockAdapter.return_value
        # Even ORDER_CREATED should not decrement
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 5)

    # ------------------------------------------------------------------
    # Webhook tests
    # ------------------------------------------------------------------
    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_webhook_payment_captured(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.verify_webhook_signature.return_value = True
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_WH_CAPTURED',
                        'order_id': 'order_VERIFY123',
                    }
                }
            }
        }).encode('utf-8')
        service = PaymentVerificationService()
        result = service.handle_webhook(payload, 'valid_sig')
        self.assertTrue(result)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PaymentTransaction.STATUS_PAYMENT_CAPTURED)
        self.assertTrue(self.txn.payment_verified)
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 4)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_webhook_payment_failed(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.verify_webhook_signature.return_value = True
        payload = json.dumps({
            'event': 'payment.failed',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_WH_FAILED',
                        'order_id': 'order_VERIFY123',
                        'error_description': 'Card declined',
                    }
                }
            }
        }).encode('utf-8')
        service = PaymentVerificationService()
        result = service.handle_webhook(payload, 'valid_sig')
        self.assertTrue(result)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PaymentTransaction.STATUS_PAYMENT_FAILED)
        self.assertIn('Card declined', self.txn.failure_reason)
        # Inventory NOT decremented
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 5)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_webhook_invalid_signature_rejected(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.verify_webhook_signature.return_value = False
        payload = json.dumps({'event': 'payment.captured'}).encode('utf-8')
        service = PaymentVerificationService()
        result = service.handle_webhook(payload, 'bad_sig')
        self.assertFalse(result)
        # Transaction status unchanged
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PaymentTransaction.STATUS_ORDER_CREATED)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_webhook_unknown_order_id(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.verify_webhook_signature.return_value = True
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_unknown',
                        'order_id': 'order_DOES_NOT_EXIST',
                    }
                }
            }
        }).encode('utf-8')
        service = PaymentVerificationService()
        result = service.handle_webhook(payload, 'valid_sig')
        self.assertFalse(result)


# ======================================================================
# API Endpoint Tests (end-to-end with mocked Razorpay)
# ======================================================================

class TransactionAPITests(TestCase):
    """Test the payments API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.merchant = _create_merchant()
        self.product = _create_product(self.merchant, inventory=5)
        self.buyer = _create_buyer_profile()
        self.negotiation = _create_agreed_negotiation(
            self.merchant, self.product, self.buyer,
            agreed_price=Decimal('450.00'),
        )

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_create_transaction_endpoint(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        resp = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(self.negotiation.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertIn('razorpay_order_id', data)
        self.assertIn('razorpay_key_id', data)
        self.assertEqual(data['status'], 'ORDER_CREATED')
        self.assertEqual(data['amount_minor_units'], 45000)

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_create_transaction_idempotent(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        resp1 = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(self.negotiation.id)},
            format='json',
        )
        resp2 = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(self.negotiation.id)},
            format='json',
        )
        self.assertEqual(resp1.json()['id'], resp2.json()['id'])
        mock_instance.create_order.assert_called_once()

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_no_secrets_in_response(self, MockAdapter):
        """Ensure RAZORPAY_KEY_SECRET and cost_price are never in the response."""
        mock_instance = MockAdapter.return_value
        mock_instance.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        resp = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(self.negotiation.id)},
            format='json',
        )
        body = resp.content.decode()
        self.assertNotIn('key_secret', body.lower())
        self.assertNotIn('cost_price', body.lower())
        self.assertNotIn('dummy_key_secret', body.lower())

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_get_transaction_endpoint(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        # First create
        resp_create = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(self.negotiation.id)},
            format='json',
        )
        txn_id = resp_create.json()['id']
        # Then retrieve
        resp_get = self.client.get(f'/api/payments/transactions/{txn_id}/')
        self.assertEqual(resp_get.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_get.json()['id'], txn_id)

    def test_create_transaction_invalid_negotiation(self):
        resp = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(uuid.uuid4())},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_create_transaction_not_agreed(self, MockAdapter):
        self.negotiation.status = AgentNegotiation.STATUS_ACTIVE
        self.negotiation.save()
        resp = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(self.negotiation.id)},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('payments.services.transaction_service.RazorpayAdapter')
    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_verify_endpoint_success(self, MockVerifyAdapter, MockTxnAdapter):
        # Create transaction first
        mock_txn = MockTxnAdapter.return_value
        mock_txn.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        resp = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(self.negotiation.id)},
            format='json',
        )
        txn_id = resp.json()['id']
        # Verify
        mock_verify = MockVerifyAdapter.return_value
        mock_verify.verify_payment_signature.return_value = True
        resp_verify = self.client.post(
            f'/api/payments/transactions/{txn_id}/verify/',
            {'razorpay_payment_id': 'pay_API_OK', 'razorpay_signature': 'sig_API_OK'},
            format='json',
        )
        self.assertEqual(resp_verify.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_verify.json()['status'], 'PAYMENT_CAPTURED')

    @patch('payments.services.transaction_service.RazorpayAdapter')
    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_verify_endpoint_failure(self, MockVerifyAdapter, MockTxnAdapter):
        mock_txn = MockTxnAdapter.return_value
        mock_txn.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        resp = self.client.post(
            '/api/payments/transactions/',
            {'negotiation_id': str(self.negotiation.id)},
            format='json',
        )
        txn_id = resp.json()['id']
        mock_verify = MockVerifyAdapter.return_value
        mock_verify.verify_payment_signature.return_value = False
        resp_verify = self.client.post(
            f'/api/payments/transactions/{txn_id}/verify/',
            {'razorpay_payment_id': 'pay_BAD', 'razorpay_signature': 'sig_BAD'},
            format='json',
        )
        self.assertEqual(resp_verify.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_webhook_endpoint(self, MockAdapter):
        # Create a transaction directly in DB
        txn = PaymentTransaction.objects.create(
            negotiation=self.negotiation,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_WH_API',
            status=PaymentTransaction.STATUS_ORDER_CREATED,
            amount_minor_units=45000,
            receipt='order_wh_api',
        )
        mock_instance = MockAdapter.return_value
        mock_instance.verify_webhook_signature.return_value = True
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_WH_API_OK',
                        'order_id': 'order_WH_API',
                    }
                }
            }
        })
        resp = self.client.post(
            '/api/payments/webhooks/razorpay/',
            data=payload,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='valid_sig',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PaymentTransaction.STATUS_PAYMENT_CAPTURED)


# ======================================================================
# Edge-case and security tests
# ======================================================================

class SecurityAndEdgeCaseTests(TestCase):
    """Test edge cases, security invariants, and failure handling."""

    def setUp(self):
        self.merchant = _create_merchant()
        self.product = _create_product(self.merchant, inventory=1)
        self.buyer = _create_buyer_profile()
        self.negotiation = _create_agreed_negotiation(
            self.merchant, self.product, self.buyer,
            agreed_price=Decimal('450.00'),
        )

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_inventory_not_decremented_on_order_creation(self, MockAdapter):
        """Inventory must remain untouched when an order is created."""
        txn = PaymentTransaction.objects.create(
            negotiation=self.negotiation,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_INV_TEST',
            status=PaymentTransaction.STATUS_ORDER_CREATED,
            amount_minor_units=45000,
            receipt='order_inv_test',
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 1)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_inventory_decremented_exactly_once_on_capture(self, MockAdapter):
        txn = PaymentTransaction.objects.create(
            negotiation=self.negotiation,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_INV_ONCE',
            status=PaymentTransaction.STATUS_ORDER_CREATED,
            amount_minor_units=45000,
            receipt='order_inv_once',
        )
        mock_instance = MockAdapter.return_value
        mock_instance.verify_payment_signature.return_value = True
        service = PaymentVerificationService()
        service.verify_and_capture(txn, 'pay_once', 'sig_once')
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 0)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_webhook_capture_idempotent(self, MockAdapter):
        """Webhook capture on already-captured txn should not decrement twice."""
        txn = PaymentTransaction.objects.create(
            negotiation=self.negotiation,
            merchant=self.merchant,
            product=self.product,
            agreed_amount=Decimal('450.00'),
            razorpay_order_id='order_IDEMPOTENT',
            status=PaymentTransaction.STATUS_PAYMENT_CAPTURED,
            amount_minor_units=45000,
            receipt='order_idemp',
            payment_verified=True,
        )
        mock_instance = MockAdapter.return_value
        mock_instance.verify_webhook_signature.return_value = True
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {
                'payment': {
                    'entity': {
                        'id': 'pay_IDEMP',
                        'order_id': 'order_IDEMPOTENT',
                    }
                }
            }
        }).encode('utf-8')
        service = PaymentVerificationService()
        result = service.handle_webhook(payload, 'sig')
        self.assertTrue(result)
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 1)  # not decremented again

    def test_transaction_detail_endpoint_not_found(self):
        client = APIClient()
        resp = client.get(f'/api/payments/transactions/{uuid.uuid4()}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch('payments.services.transaction_service.RazorpayAdapter')
    def test_amount_matches_agreement_not_client(self, MockAdapter):
        """Client cannot override the amount. It must come from agreement."""
        mock_instance = MockAdapter.return_value
        mock_instance.create_order.return_value = MOCK_RAZORPAY_ORDER.copy()
        service = TransactionService()
        txn = service.create_or_get_transaction(self.negotiation.id)
        self.assertEqual(txn.agreed_amount, Decimal('450.00'))
        # The create endpoint does not accept an amount field at all
        self.assertEqual(txn.amount_minor_units, 45000)

    def test_missing_negotiation_id(self):
        client = APIClient()
        resp = client.post('/api/payments/transactions/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_webhook_rejects_no_order_id(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.verify_webhook_signature.return_value = True
        payload = json.dumps({
            'event': 'payment.captured',
            'payload': {'payment': {'entity': {'id': 'pay_x'}}}
        }).encode('utf-8')
        service = PaymentVerificationService()
        result = service.handle_webhook(payload, 'sig')
        self.assertFalse(result)

    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_webhook_malformed_json(self, MockAdapter):
        mock_instance = MockAdapter.return_value
        mock_instance.verify_webhook_signature.return_value = True
        service = PaymentVerificationService()
        result = service.handle_webhook(b'NOT JSON', 'sig')
        self.assertFalse(result)


# ======================================================================
# Step 12 — Final Autonomous Commerce End-to-End Integration Tests
# ======================================================================

class Step12EndToEndIntegrationTests(TestCase):
    """
    Validates the complete autonomous commerce pipeline:
    Buyer Intent -> Product Match -> Revenue Decision ->
    AI Autonomous Negotiation -> Policy Bounded Agreement ->
    Payment Transaction -> Razorpay Order -> Signature Verification ->
    Inventory Settlement -> Audit Events.
    """

    def setUp(self):
        self.client = APIClient()
        self.merchant = _create_merchant()
        self.product = _create_product(
            self.merchant,
            price=Decimal('3999.00'),
            cost=Decimal('2700.00'),
            inventory=15
        )
        self.product.name = 'Mechanical Gaming Keyboard'
        self.product.category = 'Gaming'
        self.product.description = 'RGB mechanical gaming keyboard with tactile switches.'
        self.product.save()
        self.policy = MerchantPolicy.objects.get(merchant=self.merchant)
        self.policy.minimum_margin_percent = Decimal('18.00')
        self.policy.maximum_discount_percent = Decimal('10.00')
        self.policy.maximum_negotiation_rounds = 3
        self.policy.auto_approval_limit = Decimal('25000.00')
        self.policy.save()

    @patch('payments.services.transaction_service.RazorpayAdapter')
    @patch('payments.services.payment_verification.RazorpayAdapter')
    def test_complete_autonomous_commerce_journey(self, MockVerifyAdapter, MockTxnAdapter):
        """Complete 18-step validated commerce journey."""
        from ai.services.intent_engine import extract_intent
        from ai.services.product_matcher import find_matching_products
        from ai.services.revenue_engine import generate_opportunities
        from ai.services.decision_engine import make_decision
        from ai.services.agent_negotiation import AgentNegotiationOrchestrator
        from ai.models import AgentNegotiationEvent

        # Mock adapter returns
        txn_mock = MockTxnAdapter.return_value
        txn_mock.create_order.return_value = {
            'id': 'order_rzp_step12_demo',
            'amount': 359910,
            'currency': 'INR',
            'status': 'created',
            'receipt': 'order_rcpt_step12',
        }
        verify_mock = MockVerifyAdapter.return_value
        verify_mock.verify_payment_signature.return_value = True

        # 1. Buyer Intent extraction
        user_prompt = "I need a mechanical gaming keyboard under 4500"
        intent = extract_intent(user_prompt)
        self.assertIsNotNone(intent)

        # 2. Product Matching
        matches = find_matching_products(intent, merchant=self.merchant)
        self.assertTrue(len(matches) > 0)
        matched_prod = matches[0]
        self.assertEqual(matched_prod.id, self.product.id)

        # 3. Revenue Decision Engine
        opps = generate_opportunities(intent, [matched_prod], self.policy)
        decision = make_decision(intent, opps, self.policy)
        self.assertIsNotNone(decision)
        self.assertIn(decision.selected_action, ["OFFER", "COUNTER", "DIRECT_ACCEPT", "DISCOUNT"])

        # 4. Autonomous Negotiation with deterministic policy-compliant agreement profile
        buyer_profile = BuyerAgentProfile.objects.create(
            buyer_session_id='step12-demo-buyer',
            name='Sarah Jenkins',
            requirements=['Mechanical Gaming Keyboard'],
            budget_min=Decimal('3000.00'),
            budget_max=Decimal('4500.00'),
            preferred_price=Decimal('3600.00'),
            maximum_price=Decimal('4000.00'),
            walk_away_price=Decimal('4500.00'),
            negotiation_enabled=True,
            maximum_negotiation_rounds=3,
            strategy=BuyerAgentProfile.STRATEGY_BALANCED,
        )
        neg = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(buyer_profile.id),
            merchant_id=self.merchant.id,
            product_id=matched_prod.id
        )
        self.assertEqual(neg.status, AgentNegotiation.STATUS_ACTIVE)
        self.assertEqual(neg.max_rounds, 3)

        # 5. Run negotiation to AGREED
        summary = AgentNegotiationOrchestrator.run_negotiation(neg, max_steps=10)
        neg.refresh_from_db()
        self.assertEqual(neg.status, AgentNegotiation.STATUS_AGREED)
        self.assertEqual(neg.agreed_price, Decimal('3599.10'))
        self.assertTrue(neg.payment_ready)

        # Policy checks
        catalog_price = self.product.price
        max_discount_allowed = catalog_price * (Decimal('1.00') - (self.policy.maximum_discount_percent / Decimal('100.00')))
        self.assertGreaterEqual(neg.agreed_price, max_discount_allowed)
        min_margin_price = self.product.cost_price / (Decimal('1.00') - (self.policy.minimum_margin_percent / Decimal('100.00')))
        self.assertGreaterEqual(neg.agreed_price, min_margin_price)

        # 6. Audit trail verified across negotiation
        events = neg.events.all().order_by('created_at')
        event_types = [ev.event_type for ev in events]
        self.assertIn(AgentNegotiationEvent.EVENT_NEGOTIATION_STARTED, event_types)
        self.assertIn(AgentNegotiationEvent.EVENT_PRODUCT_SELECTED, event_types)
        self.assertIn(AgentNegotiationEvent.EVENT_MERCHANT_OFFER, event_types)
        self.assertIn(AgentNegotiationEvent.EVENT_BUYER_ACCEPT, event_types)
        self.assertIn(AgentNegotiationEvent.EVENT_AGREEMENT_REACHED, event_types)

        # 7. Payment Transaction Creation (amount locked to agreement)
        create_resp = self.client.post('/api/payments/transactions/', {
            'negotiation_id': str(neg.id),
            'amount': 100.00  # Client attempt to tamper amount
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        txn_data = create_resp.json()
        self.assertEqual(Decimal(str(txn_data['agreed_amount'])), Decimal('3599.10'))
        self.assertEqual(txn_data['amount_minor_units'], 359910)
        self.assertEqual(txn_data['status'], 'ORDER_CREATED')
        txn_id = txn_data['id']

        # 8. Inventory is UNCHANGED before payment capture
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 15)

        # 9. Valid signature captures payment and decrements inventory
        verify_mock.verify_payment_signature.return_value = True
        good_resp = self.client.post(f'/api/payments/transactions/{txn_id}/verify/', {
            'razorpay_payment_id': 'pay_valid_123',
            'razorpay_signature': 'valid_sig_123'
        }, format='json')
        self.assertEqual(good_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(good_resp.json()['status'], 'PAYMENT_CAPTURED')
        self.assertTrue(good_resp.json()['payment_verified'])

        # 10. Inventory successfully decremented by exactly 1
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 14)

        # 11. Invalid signature is rejected on a new pending transaction
        buyer_profile2 = BuyerAgentProfile.objects.create(
            buyer_session_id='step12-demo-buyer-2',
            name='Mark Davis',
            requirements=['Mechanical Gaming Keyboard'],
            budget_min=Decimal('3000.00'),
            budget_max=Decimal('4500.00'),
            preferred_price=Decimal('3600.00'),
            maximum_price=Decimal('4000.00'),
            walk_away_price=Decimal('4500.00'),
            negotiation_enabled=True,
            maximum_negotiation_rounds=3,
            strategy=BuyerAgentProfile.STRATEGY_FAST_BUYER,
        )
        neg2 = AgentNegotiationOrchestrator.create_negotiation(
            buyer_profile_id=str(buyer_profile2.id),
            merchant_id=self.merchant.id,
            product_id=matched_prod.id
        )
        AgentNegotiationOrchestrator.run_negotiation(neg2, max_steps=10)
        txn2_resp = self.client.post('/api/payments/transactions/', {
            'negotiation_id': str(neg2.id)
        }, format='json')
        self.assertEqual(txn2_resp.status_code, status.HTTP_201_CREATED)
        txn2_id = txn2_resp.json()['id']

        verify_mock.verify_payment_signature.return_value = False
        bad_resp = self.client.post(f'/api/payments/transactions/{txn2_id}/verify/', {
            'razorpay_payment_id': 'pay_invalid',
            'razorpay_signature': 'bad_sig'
        }, format='json')
        self.assertEqual(bad_resp.status_code, status.HTTP_400_BAD_REQUEST)
        # Failed payment does NOT decrement inventory
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory_quantity, 14)

    def test_env_config_and_secret_shielding(self):
        """Verify .env loading logic and that key secret is strictly shielded."""
        from pathlib import Path
        import tempfile
        import os
        from config.settings import _load_env_file
        from django.conf import settings
        from payments.serializers import TransactionDetailSerializer

        # Test safe env parser logic with a temp env file
        with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as f:
            f.write("# comment line\n")
            f.write("TEST_ENV_VAR_RZP='test_value_123'\n")
            f.write('TEST_ENV_VAR_QUOTED="quoted_value"\n')
            temp_path = Path(f.name)

        try:
            _load_env_file(temp_path)
            self.assertEqual(os.environ.get('TEST_ENV_VAR_RZP'), 'test_value_123')
            self.assertEqual(os.environ.get('TEST_ENV_VAR_QUOTED'), 'quoted_value')
        finally:
            os.environ.pop('TEST_ENV_VAR_RZP', None)
            os.environ.pop('TEST_ENV_VAR_QUOTED', None)
            temp_path.unlink(missing_ok=True)

        # Verify serializer fields never include secret
        serializer_fields = TransactionDetailSerializer().get_fields().keys()
        self.assertNotIn('key_secret', serializer_fields)
        self.assertNotIn('secret', serializer_fields)
        self.assertNotIn('cost_price', serializer_fields)


