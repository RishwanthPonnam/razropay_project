import { api } from './client';

export const paymentsApi = {
  // List transactions (optionally filter by merchant)
  listTransactions: (merchantId) => {
    const params = merchantId ? `?merchant_id=${merchantId}` : '';
    return api.get(`/payments/transactions/${params}`);
  },
  getTransaction: (transactionId) =>
    api.get(`/payments/transactions/${transactionId}/`),
  createTransaction: (negotiationId) =>
    api.post('/payments/transactions/', { negotiation_id: negotiationId }),

  // Verify Razorpay signature and capture payment
  verifySignature: (transactionId, razorpayPaymentId, razorpaySignature) =>
    api.post(`/payments/transactions/${transactionId}/verify/`, {
      razorpay_payment_id: razorpayPaymentId,
      razorpay_signature: razorpaySignature,
    }),
};

/**
 * Ensure Razorpay checkout.js script is loaded.
 */
export function loadRazorpayScript() {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined' && window.Razorpay) {
      resolve(true);
      return;
    }
    const existing = document.querySelector('script[src*="checkout.razorpay.com"]');
    if (existing) {
      existing.addEventListener('load', () => resolve(true));
      existing.addEventListener('error', () => resolve(false));
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

/**
 * Launch Razorpay Standard Checkout modal in Test Mode.
 */
export async function launchRazorpayCheckout({ txn, onSuccess, onError, onDismiss }) {
  const loaded = await loadRazorpayScript();
  if (!loaded || !window.Razorpay) {
    onError && onError(new Error('Razorpay Checkout SDK could not be loaded. Please check your network connection.'));
    return;
  }

  if (!txn.razorpay_key_id) {
    onError && onError(new Error('Razorpay public key ID is missing.'));
    return;
  }
  if (!txn.razorpay_order_id) {
    onError && onError(new Error('Razorpay Order ID is missing.'));
    return;
  }

  const options = {
    key: txn.razorpay_key_id,
    amount: txn.amount_minor_units || Math.round(Number(txn.agreed_amount) * 100),
    currency: txn.currency || 'INR',
    name: 'Merchant OS AI',
    description: `${txn.product_name || 'Agreed Order'} — Autonomous Deal`,
    order_id: txn.razorpay_order_id,
    handler: async function (response) {
      try {
        const verifyRes = await paymentsApi.verifySignature(
          txn.id,
          response.razorpay_payment_id,
          response.razorpay_signature
        );
        onSuccess && onSuccess(verifyRes || {
          ...txn,
          status: 'PAYMENT_CAPTURED',
          razorpay_payment_id: response.razorpay_payment_id,
          payment_verified: true,
        });
      } catch (err) {
        onError && onError(err);
      }
    },
    prefill: {
      name: txn.buyer_name || 'AI Buyer',
      email: 'buyer@example.com',
      contact: '9999999999',
    },
    theme: {
      color: '#4361ee',
    },
    modal: {
      ondismiss: function () {
        onDismiss && onDismiss();
      },
    },
  };

  try {
    const rzp = new window.Razorpay(options);
    rzp.on('payment.failed', function (resp) {
      const msg = resp.error?.description || resp.error?.reason || 'Payment was not completed.';
      onError && onError(new Error(msg));
    });
    rzp.open();
  } catch (err) {
    onError && onError(err);
  }
}


