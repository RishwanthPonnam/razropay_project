import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles, Search, ShoppingBag, ArrowRight, Bot, Store,
  CheckCircle2, CreditCard, ShieldCheck, AlertCircle,
  Package, Check, RotateCcw, CheckCheck, XCircle, RefreshCw,
  DollarSign, X
} from 'lucide-react';
import { aiApi } from '../api/ai';
import { paymentsApi, launchRazorpayCheckout } from '../api/payments';
import ErrorBanner from '../components/ErrorBanner';
import LoadingSpinner from '../components/LoadingSpinner';

// ─── Constants ─────────────────────────────────────────────────────────────
const SUGGESTED_QUERIES = [
  "I want a gaming keyboard under ₹3,600",
  "Looking for wireless ANC headphones under ₹5,000",
  "Gaming mouse with RGB under ₹1,800",
  "High performance laptop under ₹60,000",
];

// ─── State Machine ──────────────────────────────────────────────────────────
const STAGE = {
  REQUEST: 'REQUEST',
  MATCHING: 'MATCHING',
  MATCHED: 'MATCHED',
  NEGOTIATING: 'NEGOTIATING',
  AGREED: 'AGREED',
  PAYING: 'PAYING',
  PAID: 'PAID',
  COMPLETE: 'COMPLETE',
  ERROR: 'ERROR',
};

// ─── Helpers ────────────────────────────────────────────────────────────────
const extractBudgetFromIntent = (intent, queryText) => {
  if (intent?.budget_max && !isNaN(parseFloat(intent.budget_max))) {
    return parseFloat(intent.budget_max);
  }
  if (queryText) {
    const m = queryText.match(
      /(?:under|below|less than|no more than|within|budget|max|maximum|upto|up to|at most)\s*(?:[₹\s]|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)/i
    );
    if (m?.[1]) {
      const parsed = parseFloat(m[1].replace(/,/g, ''));
      if (!isNaN(parsed) && parsed > 0) return parsed;
    }
  }
  return null;
};

const safeCustomerMessage = (ev) => {
  const raw = ev?.customer_message || ev?.message || '';
  const hasLeak = /walk-away|margin\s*floor|cost\s*price|economic\s*constitution|internal_reason/i.test(raw);
  if (hasLeak && ev?.proposed_price) {
    return `Sorry! ₹${Number(ev.proposed_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })} is our best and final price. We've already applied the maximum discount we can offer. If this doesn't fit your budget, we completely understand.`;
  }
  if (hasLeak) {
    return "Sorry! That's our best and final offer. We've applied the maximum discount we can offer. If this doesn't fit your budget, we completely understand.";
  }
  return raw;
};


// ─── Product Card ───────────────────────────────────────────────────────────
function ProductCard({ product, budget, preferredPrice, onNegotiate, negotiating }) {
  const inStock = (product.inventory_quantity || 0) > 0;
  const merchantFloor = (Number(product.price) * 0.90).toFixed(2);

  return (
    <div className="card" style={{
      padding: '24px', border: '2px solid var(--primary)',
      borderRadius: 'var(--r-lg)', background: '#fff',
      boxShadow: '0 8px 24px rgba(67,97,238,0.12)',
      position: 'relative',
    }}>
      <div style={{ position: 'absolute', top: -10, right: 20, background: 'var(--primary)', color: '#fff', fontSize: 10, fontWeight: 800, padding: '3px 10px', borderRadius: 12, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        Best Match
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--primary)', background: 'var(--primary-dim)', padding: '3px 10px', borderRadius: 20, textTransform: 'uppercase' }}>
          {product.category}
        </span>
        <span className={`badge badge-${inStock ? 'success' : 'danger'}`} style={{ fontSize: 11, padding: '3px 8px' }}>
          {inStock ? `In Stock (${product.inventory_quantity})` : 'Out of Stock'}
        </span>
      </div>

      <h3 style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 8, letterSpacing: '-0.3px' }}>
        {product.name}
      </h3>

      <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.55, marginBottom: 14 }}>
        {product.description}
      </p>

      {/* Economics Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 8, margin: '12px 0 16px', padding: '10px 12px', background: 'var(--bg-subtle)', borderRadius: 'var(--r-md)', border: '1px solid var(--border-subtle)' }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, textTransform: 'uppercase' }}>Catalog Price</div>
          <div style={{ fontSize: 14, fontWeight: 900, color: 'var(--text-primary)' }}>
            ₹{Number(product.price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>
        {budget ? (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, textTransform: 'uppercase' }}>Buyer Max Budget</div>
            <div style={{ fontSize: 14, fontWeight: 900, color: 'var(--success)' }}>
              ₹{Number(budget).toLocaleString('en-IN')}
            </div>
          </div>
        ) : null}
        {preferredPrice ? (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, textTransform: 'uppercase' }}>Buyer Target</div>
            <div style={{ fontSize: 14, fontWeight: 900, color: 'var(--primary)' }}>
              ₹{Number(preferredPrice).toLocaleString('en-IN')}
            </div>
          </div>
        ) : null}
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 700, textTransform: 'uppercase' }}>Merchant Floor</div>
          <div style={{ fontSize: 14, fontWeight: 900, color: 'var(--indigo)' }}>
            ₹{Number(merchantFloor).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingTop: 14, borderTop: '1px solid var(--border-subtle)' }}>
        {inStock && (
          <button
            className="btn btn-primary"
            style={{ width: '100%', padding: '12px 22px', fontSize: 14, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 10, boxShadow: '0 4px 12px rgba(67,97,238,0.25)' }}
            onClick={() => onNegotiate(product)}
            disabled={negotiating}
          >
            <Bot size={16} />
            <span>{negotiating ? 'Negotiating…' : 'Negotiate Best Deal'}</span>
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Progress Stepper ───────────────────────────────────────────────────────
function ProgressStepper({ stage }) {
  const steps = [
    { key: 'REQUEST', label: '1. Request Intent' },
    { key: 'MATCHED', label: '2. Product Match' },
    { key: 'NEGOTIATING', label: '3. AI-to-AI Negotiation' },
    { key: 'AGREED', label: '4. Deal Agreed' },
    { key: 'COMPLETE', label: '5. Order Complete' },
  ];

  const getStepStatus = (stepKey) => {
    if (stage === STAGE.COMPLETE && stepKey === 'COMPLETE') return 'active';
    if (stage === STAGE.PAID && stepKey === 'COMPLETE') return 'active';
    if (stage === STAGE.PAYING && stepKey === 'AGREED') return 'active';
    if (stage === STAGE.AGREED && stepKey === 'AGREED') return 'active';
    if (stage === STAGE.NEGOTIATING && stepKey === 'NEGOTIATING') return 'active';
    if (stage === STAGE.MATCHED && stepKey === 'MATCHED') return 'active';
    if (stage === STAGE.MATCHING && stepKey === 'REQUEST') return 'active';
    if (stage === STAGE.REQUEST && stepKey === 'REQUEST') return 'active';

    const order = ['REQUEST', 'MATCHED', 'NEGOTIATING', 'AGREED', 'COMPLETE'];
    const currentIdx = order.indexOf(
      stage === STAGE.MATCHING ? 'REQUEST' :
        stage === STAGE.PAYING ? 'AGREED' :
          stage === STAGE.PAID ? 'COMPLETE' :
            stage
    );
    const stepIdx = order.indexOf(stepKey);
    return stepIdx < currentIdx ? 'done' : 'pending';
  };

  return (
    <div style={{ background: '#fff', borderBottom: '1px solid var(--border)', padding: '12px 24px' }}>
      <div style={{ maxWidth: 880, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        {steps.map((s, idx) => {
          const status = getStepStatus(s.key);
          const isDone = status === 'done';
          const isActive = status === 'active';
          return (
            <React.Fragment key={s.key}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{
                  width: 22, height: 22, borderRadius: '50%', fontSize: 11, fontWeight: 800,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: isDone ? 'var(--success)' : isActive ? 'var(--primary)' : 'var(--bg-subtle)',
                  color: isDone || isActive ? '#fff' : 'var(--text-tertiary)',
                  border: isDone || isActive ? 'none' : '1px solid var(--border)',
                }}>
                  {isDone ? <Check size={12} strokeWidth={3} /> : idx + 1}
                </div>
                <span style={{
                  fontSize: 12, fontWeight: isActive ? 800 : isDone ? 700 : 500,
                  color: isActive ? 'var(--primary)' : isDone ? 'var(--text-primary)' : 'var(--text-tertiary)',
                  whiteSpace: 'nowrap',
                }}>
                  {s.label}
                </span>
              </div>
              {idx < steps.length - 1 && (
                <div style={{ flex: 1, height: 2, background: isDone ? 'var(--success)' : 'var(--border-subtle)', margin: '0 4px', minWidth: 16 }} />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

// ─── Deal Preferences Modal ─────────────────────────────────────────────────
function DealPreferencesModal({
  isOpen,
  onClose,
  product,
  budgetMax,
  setBudgetMax,
  preferredPrice,
  setPreferredPrice,
  onConfirm,
  validationError
}) {
  if (!isOpen || !product) return null;

  const catalogPrice = Number(product.price) || 0;
  const currentBudget = parseFloat(budgetMax) || 0;
  const currentPref = parseFloat(preferredPrice) || 0;

  const discountPercent = currentBudget > 0 && currentPref > 0 && currentPref < catalogPrice
    ? (((catalogPrice - currentPref) / catalogPrice) * 100).toFixed(0)
    : null;

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(15, 23, 42, 0.65)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16
    }}>
      <div style={{
        background: '#fff', borderRadius: 'var(--r-xl)', maxWidth: 480, width: '100%',
        boxShadow: '0 25px 50px -12px rgba(0,0,0,0.25)', border: '1px solid var(--border)',
        overflow: 'hidden', animation: 'fadeInScale 0.2s ease-out'
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 24px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'linear-gradient(135deg, #f8faff 0%, #ffffff 100%)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%', background: 'var(--primary-dim)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--primary)'
            }}>
              <Bot size={20} />
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-primary)' }}>Set Your Deal Preferences</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Guide your Buyer AI's negotiation bounds</div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-tertiary)', padding: 4, borderRadius: 6, display: 'flex'
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* Target Product Summary */}
          <div style={{
            background: 'var(--bg-subtle)', borderRadius: 'var(--r-md)', padding: '14px 16px',
            border: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
          }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Selected Product</div>
              <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)', marginTop: 2 }}>{product.name}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Catalog Price</div>
              <div style={{ fontSize: 16, fontWeight: 900, color: 'var(--text-primary)', marginTop: 2 }}>
                ₹{catalogPrice.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
            </div>
          </div>

          {/* Validation Error */}
          {validationError && (
            <div style={{
              background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 'var(--r-md)', padding: '10px 14px', fontSize: 12, color: 'var(--danger)',
              fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8
            }}>
              <AlertCircle size={15} />
              <span>{validationError}</span>
            </div>
          )}

          {/* Input 1: Maximum Budget */}
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
              Maximum Budget (Ceiling) <span style={{ color: 'var(--danger)' }}>*</span>
            </label>
            <div style={{
              display: 'flex', alignItems: 'center', border: '1.5px solid var(--border)',
              borderRadius: 'var(--r-md)', padding: '0 12px', background: '#fff',
              boxShadow: 'var(--shadow-xs)'
            }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-tertiary)', marginRight: 6 }}>₹</span>
              <input
                type="number"
                placeholder={`e.g. ${catalogPrice}`}
                value={budgetMax}
                onChange={(e) => setBudgetMax(e.target.value)}
                style={{
                  border: 'none', outline: 'none', padding: '12px 0', fontSize: 15,
                  fontWeight: 700, color: 'var(--text-primary)', width: '100%', background: 'transparent'
                }}
              />
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
              The absolute maximum you are willing to pay. The Buyer AI will walk away above this price.
            </div>
          </div>

          {/* Input 2: Preferred / Target Price */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <label style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                Target / Preferred Price (Optional)
              </label>
              {discountPercent && discountPercent > 0 && (
                <span style={{
                  fontSize: 11, fontWeight: 800, background: 'var(--success-dim)',
                  color: 'var(--success)', padding: '2px 8px', borderRadius: 12
                }}>
                  {discountPercent}% Target Discount
                </span>
              )}
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', border: '1.5px solid var(--border)',
              borderRadius: 'var(--r-md)', padding: '0 12px', background: '#fff',
              boxShadow: 'var(--shadow-xs)'
            }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-tertiary)', marginRight: 6 }}>₹</span>
              <input
                type="number"
                placeholder={`e.g. ${(catalogPrice * 0.85).toFixed(0)}`}
                value={preferredPrice}
                onChange={(e) => setPreferredPrice(e.target.value)}
                style={{
                  border: 'none', outline: 'none', padding: '12px 0', fontSize: 15,
                  fontWeight: 700, color: 'var(--text-primary)', width: '100%', background: 'transparent'
                }}
              />
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
              Your ideal dream price. If left blank, the Buyer AI will target 15% below maximum budget.
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div style={{
          padding: '16px 24px', background: 'var(--bg-subtle)', borderTop: '1px solid var(--border)',
          display: 'flex', justifyContent: 'flex-end', gap: 12
        }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            style={{ fontSize: 13, padding: '10px 18px' }}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onConfirm}
            style={{ fontSize: 13, fontWeight: 700, padding: '10px 22px', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Bot size={15} />
            <span>Start AI Negotiation</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────
export default function BuyerPortal({ merchant, onSwitchToMerchant }) {
  const merchantId = merchant?.id || 2;

  // ── State Machine ─────────────────────────────────────────────────────────
  const [stage, setStage] = useState(STAGE.REQUEST);
  const [query, setQuery] = useState('');
  const [error, setError] = useState(null);

  // MATCHED stage data
  const [intentData, setIntentData] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);

  // NEGOTIATING / AGREED stage data
  const [negSession, setNegSession] = useState(null);
  const [negEvents, setNegEvents] = useState([]);
  const [negStatus, setNegStatus] = useState(null);
  const [agreedPrice, setAgreedPrice] = useState(null);

  // PAYING / PAID stage data
  const [paySuccess, setPaySuccess] = useState(null);

  // ── Deal Preferences Modal state ─────────────────────────────────────────
  const [showDealModal, setShowDealModal] = useState(false);
  const [pendingProduct, setPendingProduct] = useState(null);
  const [modalBudgetMax, setModalBudgetMax] = useState('');
  const [modalPreferredPrice, setModalPreferredPrice] = useState('');
  const [modalValidationError, setModalValidationError] = useState(null);
  const [confirmedBudget, setConfirmedBudget] = useState(null);
  const [confirmedPreferredPrice, setConfirmedPreferredPrice] = useState(null);

  // ── Derived display values ────────────────────────────────────────────────
  const budget = extractBudgetFromIntent(intentData?.intent, query);
  const dispQuery = intentData?.intent?.search_query || intentData?.intent?.product_type || query;

  // ── Reset ─────────────────────────────────────────────────────────────────
  const matchedRef = useRef(null);
  const dealRef = useRef(null);

  useEffect(() => {
    if (stage === STAGE.MATCHED && matchedRef.current) {
      matchedRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (stage === STAGE.AGREED && dealRef.current) {
      dealRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [stage]);

  const handleReset = () => {
    setStage(STAGE.REQUEST);
    setQuery('');
    setError(null);
    setIntentData(null);
    setSelectedProduct(null);
    setNegSession(null);
    setNegEvents([]);
    setNegStatus(null);
    setAgreedPrice(null);
    setPaySuccess(null);
    setShowDealModal(false);
    setPendingProduct(null);
    setModalBudgetMax('');
    setModalPreferredPrice('');
    setModalValidationError(null);
    setConfirmedBudget(null);
    setConfirmedPreferredPrice(null);
  };

  // ── STEP 1: Find & Match ──────────────────────────────────────────────────
  const handleFindAndMatch = async (overrideQuery) => {
    const q = (overrideQuery || query || '').trim();
    if (!q) return;

    setStage(STAGE.MATCHING);
    setError(null);
    setIntentData(null);
    setSelectedProduct(null);
    setNegSession(null);
    setNegEvents([]);
    setNegStatus(null);
    setAgreedPrice(null);
    setPaySuccess(null);

    try {
      const res = await aiApi.extractIntent(q);
      if (!res?.intent) {
        setError("Sorry, we couldn't understand that request. Try describing the product and budget.");
        setStage(STAGE.ERROR);
        return;
      }
      setIntentData(res);
      if ((res.matches || []).length === 0) {
        setStage(STAGE.MATCHED);
      } else {
        setSelectedProduct(res.matches[0]);
        setStage(STAGE.MATCHED);
      }
    } catch (err) {
      if (err?.status >= 500 || err?.status === 0) {
        setError("AI matching is temporarily unavailable. Please try again.");
      } else if (err?.status === 400) {
        setError("Sorry, we couldn't understand that request. Try describing the product and budget.");
      } else {
        setError(err.message || "Sorry, we couldn't find a matching product.");
      }
      setStage(STAGE.ERROR);
    }
  };

  // ── STEP 2: Autonomous Negotiation Core Execution ─────────────────────────
  const executeNegotiation = async (product, budgetVal, prefVal) => {
    if (!product) return;

    // Close modal and transition
    setShowDealModal(false);
    setSelectedProduct(product);
    setConfirmedBudget(budgetVal);
    setConfirmedPreferredPrice(prefVal && !isNaN(prefVal) ? prefVal : null);
    setStage(STAGE.NEGOTIATING);
    setError(null);
    setNegSession(null);
    setNegEvents([]);
    setNegStatus(null);
    setAgreedPrice(null);
    setPaySuccess(null);

    try {
      const { session, result } = await aiApi.startNegotiation(
        product.merchant || merchantId,
        product.id,
        {
          name: 'Shopper AI Assistant',
          budget: budgetVal,
          preferred_price: prefVal && !isNaN(prefVal) ? prefVal : undefined,
          productName: product.name,
          price_sensitivity: 'LOW',
          loyalty: 'RETURNING',
        }
      );

      setNegSession(session);

      // Fetch full event log
      let fullStatus = result?.status || session?.status;
      let fullAgreedPrice = result?.agreed_price || session?.agreed_price;
      let events = [];

      if (session?.id) {
        try {
          const fullNeg = await aiApi.getNegotiation(session.id);
          events = fullNeg?.events || [];
          if (fullNeg?.status) fullStatus = fullNeg.status;
          if (fullNeg?.agreed_price) fullAgreedPrice = fullNeg.agreed_price;
        } catch (_) { /* non-fatal */ }
      }

      setNegEvents(events);
      setNegStatus(fullStatus);
      setAgreedPrice(fullAgreedPrice);

      if (fullStatus === 'AGREED') {
        setStage(STAGE.AGREED);
      } else {
        setError(
          fullStatus === 'REJECTED'
            ? "I couldn't reach a deal within your budget this time. You can try a different product or adjust your budget."
            : "Negotiation expired without an agreement. Try adjusting your budget."
        );
        setStage(STAGE.MATCHED);
      }
    } catch (err) {
      setError(err.message || "I couldn't reach a deal this time. You can try another product.");
      setStage(STAGE.MATCHED);
    }
  };

  const handleNegotiate = (product) => {
    const naturalBudget = budget || extractBudgetFromIntent(intentData?.intent, query);
    if (naturalBudget) {
      // Natural language budget is present — proceed immediately
      executeNegotiation(
        product,
        naturalBudget,
        intentData?.intent?.preferred_price || parseFloat((naturalBudget * 0.85).toFixed(2))
      );
    } else {
      // No natural language budget — prompt user in modal
      setPendingProduct(product);
      setModalBudgetMax('');
      setModalPreferredPrice('');
      setModalValidationError(null);
      setShowDealModal(true);
    }
  };

  const handleStartNegotiation = () => {
    const bMax = parseFloat(modalBudgetMax);
    if (!bMax || isNaN(bMax) || bMax <= 0) {
      setModalValidationError('Please enter a valid maximum budget greater than 0.');
      return;
    }
    const pPref = modalPreferredPrice ? parseFloat(modalPreferredPrice) : null;
    if (pPref !== null && (!isNaN(pPref) && (pPref <= 0 || pPref > bMax))) {
      setModalValidationError('Preferred price must be greater than 0 and not exceed your maximum budget.');
      return;
    }
    executeNegotiation(pendingProduct, bMax, pPref);
  };

  // ── STEP 3: Razorpay Checkout ─────────────────────────────────────────────
  const handlePayment = async () => {
    if (!negSession?.id) return;
    setStage(STAGE.PAYING);
    setError(null);

    try {
      // Calls POST /api/payments/transactions/ (same as existing pipeline)
      const txn = await aiApi.initiatePayment(negSession.id);

      await launchRazorpayCheckout({
        txn,
        onSuccess: (verifiedTxn) => {
          setPaySuccess(verifiedTxn);
          setStage(STAGE.COMPLETE);
        },
        onError: (err) => {
          setError(err.message || "We couldn't complete the payment. Please try again.");
          setStage(STAGE.AGREED);  // Back to deal screen
        },
        onDismiss: () => {
          setStage(STAGE.AGREED);  // Keep deal, let user retry
        },
      });
    } catch (err) {
      setError(err.message || "We couldn't start the payment. Please try again.");
      setStage(STAGE.AGREED);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-root)', display: 'flex', flexDirection: 'column' }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header style={{ background: '#fff', borderBottom: '1px solid var(--border)', padding: '0 32px', height: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, zIndex: 50 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 38, height: 38, borderRadius: 'var(--r-md)', background: 'linear-gradient(135deg, var(--primary) 0%, #3a0ca3 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', boxShadow: '0 2px 8px rgba(67,97,238,0.25)' }}>
            <ShoppingBag size={20} />
          </div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.3px', display: 'flex', alignItems: 'center', gap: 8 }}>
              Merchant OS <span style={{ fontSize: 11, background: 'var(--primary-dim)', color: 'var(--primary)', padding: '2px 8px', borderRadius: 20, fontWeight: 700 }}>BUYER PORTAL</span>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Autonomous AI-to-AI Shopping Concierge</div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)', background: 'var(--bg-subtle)', padding: '6px 12px', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
            <Store size={14} color="var(--indigo)" />
            <span>Store: <strong>{merchant?.business_name || 'NovaTech Store'}</strong></span>
          </div>
          <button className="btn btn-secondary" onClick={onSwitchToMerchant} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600 }}>
            🏢 Switch to Merchant Control Center
          </button>
        </div>
      </header>

      {/* ── Progress Stepper ───────────────────────────────────────────────── */}
      <ProgressStepper stage={stage} />

      {/* ── Main ───────────────────────────────────────────────────────────── */}
      <main style={{ maxWidth: 1040, width: '100%', margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: 28, flex: 1 }}>

        {/* ── Hero Banner (always visible) ───────────────────────────────── */}
        <div style={{ textAlign: 'center', maxWidth: 680, margin: '0 auto' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--indigo-dim)', color: 'var(--primary)', padding: '4px 14px', borderRadius: 20, fontSize: 12, fontWeight: 700, marginBottom: 12 }}>
            <Sparkles size={13} /> Autonomous AI Commerce Platform
          </div>
          <h1 style={{ fontSize: 32, fontWeight: 900, color: 'var(--text-primary)', letterSpacing: '-0.8px', marginBottom: 10 }}>
            What are you shopping for today?
          </h1>
          <p style={{ fontSize: 15, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            State your item requirement and budget naturally. Your Buyer AI will match items and negotiate directly with the Merchant AI under locked economic policies.
          </p>
        </div>

        {/* ── Search Box ─────────────────────────────────────────────────── */}
        <form
          onSubmit={(e) => { e.preventDefault(); handleFindAndMatch(); }}
          style={{ background: '#fff', borderRadius: 14, border: '2px solid rgba(67,97,238,0.25)', padding: '6px 8px 6px 16px', display: 'flex', alignItems: 'center', gap: 12, boxShadow: '0 8px 24px rgba(67,97,238,0.08)' }}
        >
          <div style={{ color: 'var(--primary)', display: 'flex', alignItems: 'center', flexShrink: 0 }}>
            <Search size={20} />
          </div>
          <input
            type="text"
            style={{ flex: 1, minWidth: 0, border: 'none', outline: 'none', boxShadow: 'none', fontSize: 16, color: 'var(--text-primary)', background: 'transparent', padding: '10px 4px', fontWeight: 500 }}
            placeholder='e.g., "I want a gaming keyboard under ₹3,600"'
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="submit"
            className="btn btn-primary"
            style={{ padding: '12px 24px', fontSize: 14, fontWeight: 700, flexShrink: 0, borderRadius: 10, display: 'flex', alignItems: 'center', gap: 8 }}
            disabled={stage === STAGE.MATCHING || !query.trim()}
          >
            {stage === STAGE.MATCHING ? (
              <><LoadingSpinner size={16} /><span>Finding your best match…</span></>
            ) : (
              <><span>Find &amp; Match</span><ArrowRight size={16} /></>
            )}
          </button>
        </form>

        {/* ── Suggested Query Chips ──────────────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontWeight: 600 }}>Try Demo Queries:</span>
          {SUGGESTED_QUERIES.map((sq, i) => (
            <button
              key={i}
              type="button"
              onClick={() => { setQuery(sq); handleFindAndMatch(sq); }}
              disabled={stage === STAGE.MATCHING}
              style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 20, padding: '6px 14px', fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer', transition: 'all 0.15s ease', boxShadow: 'var(--shadow-xs)' }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--primary)'; e.currentTarget.style.color = 'var(--primary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
            >
              {sq}
            </button>
          ))}
        </div>

        {/* ── Global Error Banner ────────────────────────────────────────── */}
        {error && (
          <div style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 'var(--r-md)', padding: '14px 18px', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <AlertCircle size={18} color="var(--danger)" style={{ flexShrink: 0, marginTop: 1 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--danger)' }}>{error}</div>
            </div>
            <button onClick={() => { setError(null); if (stage === STAGE.ERROR) setStage(STAGE.REQUEST); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', padding: 4 }}>✕</button>
          </div>
        )}

        {/* ── MATCHED: Intent Summary + Product ─────────────────────────── */}
        {[STAGE.MATCHED, STAGE.NEGOTIATING, STAGE.AGREED, STAGE.PAYING, STAGE.COMPLETE].includes(stage) && intentData && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

            {/* Intent Card */}
            <div className="card" style={{ padding: '18px 22px', background: 'linear-gradient(135deg, #f8faff 0%, #ffffff 100%)', border: '1px solid rgba(67,97,238,0.2)', boxShadow: '0 2px 12px rgba(67,97,238,0.06)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 34, height: 34, borderRadius: '50%', background: 'var(--primary-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--primary)' }}>
                    <Bot size={18} />
                  </div>
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 800, color: 'var(--primary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>AI Understood Intent</div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--text-primary)', marginTop: 1 }}>
                      Looking for: <span style={{ color: 'var(--primary)', background: 'rgba(67,97,238,0.08)', padding: '2px 10px', borderRadius: 6, textTransform: 'capitalize' }}>{dispQuery}</span>
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <span className="badge badge-indigo" style={{ padding: '4px 10px', fontSize: 12 }}>
                    {intentData.matches?.length || 0} Match{intentData.matches?.length !== 1 ? 'es' : ''}
                  </span>
                  <span className="badge badge-cyan" style={{ padding: '4px 10px', fontSize: 12 }}>Buyer AI Active</span>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, padding: '12px 14px', background: '#fff', borderRadius: 'var(--r-md)', border: '1px solid var(--border-subtle)' }}>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>Category</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--primary)', display: 'inline-block' }} />
                    {intentData.intent?.category || 'General'}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>Budget Ceiling</div>
                  <div style={{ fontSize: 13, fontWeight: 800, color: budget ? 'var(--success)' : 'var(--text-secondary)' }}>
                    {budget ? `Up to ₹${Number(budget).toLocaleString('en-IN')}` : 'Flexible'}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>Quantity</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {intentData.intent?.quantity || 1} unit{(intentData.intent?.quantity || 1) > 1 ? 's' : ''}
                  </div>
                </div>
                {(intentData.intent?.requirements || []).length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>Requirements</div>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {intentData.intent.requirements.map((r, i) => (
                        <span key={i} style={{ background: 'var(--bg-root)', border: '1px solid var(--border)', borderRadius: 4, padding: '1px 6px', fontSize: 11, fontWeight: 600 }}>{r}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* New Search Button */}
              {stage !== STAGE.COMPLETE && (
                <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ fontSize: 12 }}
                    onClick={handleReset}
                  >
                    <Search size={12} /> New Search
                  </button>
                </div>
              )}
            </div>

            {/* Product Match */}
            {/* Scroll anchor for MATCHED stage */}
            <div ref={matchedRef} />
            {stage === STAGE.MATCHED && (
              <>
                {(intentData.matches || []).length === 0 ? (
                  <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)' }}>
                    <Package size={32} style={{ opacity: 0.25, marginBottom: 12 }} />
                    <div style={{ fontWeight: 700, marginBottom: 6 }}>No matching products found</div>
                    <div style={{ fontSize: 13 }}>No matching products found. Try changing your requirements or budget.</div>
                    <button className="btn btn-secondary" style={{ marginTop: 16 }} onClick={handleReset}>
                      <RotateCcw size={14} /> Try Another Search
                    </button>
                  </div>
                ) : (
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Package size={15} color="var(--primary)" />
                      <span>Available Matching Catalog Products ({intentData.matches.length})</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 20 }}>
                      {intentData.matches.map((p) => (
                        <ProductCard
                          key={p.id}
                          product={p}
                          budget={budget}
                          preferredPrice={intentData?.intent?.preferred_price || (budget ? parseFloat((budget * 0.85).toFixed(2)) : null)}
                          onNegotiate={handleNegotiate}
                          negotiating={false}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── NEGOTIATING: Loading State ─────────────────────────────────── */}
        {stage === STAGE.NEGOTIATING && (
          <div className="card" style={{ padding: '48px 24px', textAlign: 'center', border: '2px solid rgba(67,97,238,0.2)', boxShadow: '0 6px 28px rgba(67,97,238,0.08)' }}>
            <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginBottom: 24 }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 48, height: 48, borderRadius: '50%', background: 'var(--cyan-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Bot size={24} color="var(--cyan)" />
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--cyan)' }}>Buyer AI</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingTop: 10 }}>
                {[0, 1, 2].map((i) => (
                  <div key={i} style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--primary)', opacity: 0.4, animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite` }} />
                ))}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 48, height: 48, borderRadius: '50%', background: 'var(--primary-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Store size={24} color="var(--primary)" />
                </div>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--primary)' }}>Merchant AI</span>
              </div>
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 6 }}>
              Buyer AI is negotiating with Merchant AI…
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Bounded by Economic Constitution · Max 10% discount · Min 18% margin
            </div>
            {selectedProduct && (
              <div style={{ marginTop: 16, fontSize: 13, color: 'var(--text-tertiary)' }}>
                Negotiating: <strong>{selectedProduct.name}</strong> (Catalog: ₹{Number(selectedProduct.price).toLocaleString('en-IN', { minimumFractionDigits: 2 })})
              </div>
            )}
          </div>
        )}

        {/* ── AGREED: Deal + Payment Button ──────────────────────────────── */}
        {stage === STAGE.AGREED && agreedPrice && selectedProduct && (
          <div ref={dealRef} className="card" style={{ padding: 0, overflow: 'hidden', boxShadow: '0 6px 28px rgba(0,0,0,0.07)', border: '1px solid var(--border)' }}>

            {/* Negotiation Chat Log */}
            {negEvents.length > 0 && (
              <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 16, background: '#fafbfc', borderBottom: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Sparkles size={12} /> AI-to-AI Negotiation Transcript
                </div>
                {negEvents.map((ev, i) => (
                  <ChatBubble key={i} ev={ev} merchantName={merchant?.business_name} />
                ))}
              </div>
            )}

            {/* Deal Banner */}
            <div style={{ padding: '28px', background: '#fff' }}>
              <div style={{ background: 'linear-gradient(135deg, rgba(16,185,129,0.06) 0%, rgba(67,97,238,0.04) 100%)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: 'var(--r-lg)', padding: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 20, marginBottom: 20 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--success)', fontSize: 14, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    <CheckCircle2 size={18} /> Deal Accepted
                  </div>
                  <h2 style={{ fontSize: 22, fontWeight: 900, color: 'var(--text-primary)', marginTop: 4, letterSpacing: '-0.4px' }}>
                    {selectedProduct.name}
                  </h2>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 6 }}>
                    <span style={{ fontSize: 32, fontWeight: 900, color: 'var(--text-primary)', letterSpacing: '-0.5px' }}>
                      ₹{Number(agreedPrice).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                    <span style={{ fontSize: 16, color: 'var(--text-tertiary)', textDecoration: 'line-through' }}>
                      ₹{Number(selectedProduct.price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 800, background: 'var(--success-dim)', color: 'var(--success)', padding: '3px 10px', borderRadius: 20 }}>
                      Save ₹{(Number(selectedProduct.price) - Number(agreedPrice)).toFixed(2)} OFF
                    </span>
                  </div>
                  {/* Buyer economics summary */}
                  {(confirmedBudget || confirmedPreferredPrice) && (
                    <div style={{ display: 'flex', gap: 16, marginTop: 10, flexWrap: 'wrap' }}>
                      {confirmedBudget && (
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                          Your Maximum Budget: <strong style={{ color: 'var(--text-primary)' }}>₹{Number(confirmedBudget).toLocaleString('en-IN')}</strong>
                        </div>
                      )}
                      {confirmedPreferredPrice && (
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                          Buyer Target: <strong style={{ color: 'var(--primary)' }}>₹{Number(confirmedPreferredPrice).toLocaleString('en-IN')}</strong>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 260 }}>
                  <button
                    className="btn btn-success btn-lg"
                    style={{ padding: '16px 28px', fontSize: 16, fontWeight: 800, justifyContent: 'center', borderRadius: 12, boxShadow: '0 4px 16px rgba(16,185,129,0.35)' }}
                    onClick={handlePayment}
                    disabled={stage === STAGE.PAYING}
                  >
                    <CreditCard size={20} />
                    <span>{stage === STAGE.PAYING ? 'Preparing Razorpay…' : 'Proceed to Secure Payment'}</span>
                  </button>
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                    <ShieldCheck size={14} color="var(--success)" /> Genuine Razorpay Test Mode Checkout
                  </div>
                </div>
              </div>

              {/* Checklist */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, padding: '14px 18px', background: 'var(--bg-subtle)', borderRadius: 'var(--r-md)', border: '1px solid var(--border-subtle)' }}>
                {[
                  { label: 'Buyer AI Accepted', desc: 'Fits your budget ceiling' },
                  { label: 'Merchant AI Approved', desc: 'Within Economic Constitution' },
                  { label: 'Policy Satisfied', desc: 'Margin & Discount Compliant' },
                  { label: 'Payment Ready', desc: 'Server verified order ready' },
                ].map((chk, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ color: 'var(--success)', marginTop: 2 }}><CheckCheck size={16} strokeWidth={2.5} /></div>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>{chk.label}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{chk.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── COMPLETE: Order Confirmation ──────────────────────────────── */}
        {stage === STAGE.COMPLETE && paySuccess && selectedProduct && (
          <div style={{ background: 'linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(67,97,238,0.04) 100%)', border: '2px solid var(--success)', borderRadius: 'var(--r-lg)', padding: '32px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--success)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', boxShadow: '0 4px 16px rgba(16,185,129,0.35)' }}>
                  <CheckCircle2 size={30} />
                </div>
                <div>
                  <h2 style={{ fontSize: 26, fontWeight: 900, color: 'var(--text-primary)', letterSpacing: '-0.5px' }}>🎉 Order Confirmed</h2>
                  <div style={{ fontSize: 14, color: 'var(--success)', fontWeight: 700, marginTop: 2 }}>
                    Payment confirmed ✓ · Inventory settled ✓
                  </div>
                </div>
              </div>
              <div style={{ background: '#fff', border: '1px solid rgba(16,185,129,0.3)', borderRadius: 'var(--r-md)', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Sparkles size={16} color="var(--primary)" />
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--primary)' }}>Your AI negotiated this price for you.</span>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, background: '#fff', borderRadius: 'var(--r-md)', padding: '20px', border: '1px solid var(--border)', marginBottom: 24 }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 600 }}>Purchased Item</div>
                <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)', marginTop: 2 }}>{selectedProduct.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>Category: {selectedProduct.category}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 600 }}>Agreed Amount Paid</div>
                <div style={{ fontSize: 20, fontWeight: 900, color: 'var(--success)', marginTop: 2 }}>
                  ₹{Number(agreedPrice).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textDecoration: 'line-through' }}>
                  ₹{Number(selectedProduct.price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 600 }}>Razorpay Order ID</div>
                <div style={{ fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', marginTop: 2, wordBreak: 'break-all' }}>
                  {paySuccess?.razorpay_order_id || 'order_verified'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 600 }}>Razorpay Payment ID</div>
                <div style={{ fontSize: 12, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', marginTop: 2, wordBreak: 'break-all' }}>
                  {paySuccess?.razorpay_payment_id || 'pay_verified'}
                </div>
                <div style={{ fontSize: 11, color: 'var(--success)', fontWeight: 600 }}>HMAC Signature Verified ✓</div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" style={{ padding: '12px 20px', fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }} onClick={handleReset}>
                <RotateCcw size={15} /><span>Shop Another Item</span>
              </button>
              <button className="btn btn-primary" style={{ padding: '12px 24px', fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }} onClick={onSwitchToMerchant}>
                <Store size={15} /><span>View in Merchant Control Center</span><ArrowRight size={15} />
              </button>
            </div>
          </div>
        )}

      </main>

      {/* ── Deal Preferences Modal ────────────────────────────────────── */}
      {showDealModal && pendingProduct && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(4px)' }}>
          <div style={{ background: '#fff', borderRadius: 16, width: '100%', maxWidth: 480, boxShadow: '0 24px 64px rgba(0,0,0,0.2)', overflow: 'hidden', animation: 'fadeInScale 0.2s ease' }}>
            {/* Modal Header */}
            <div style={{ padding: '24px 28px 0', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                  <div style={{ width: 38, height: 38, borderRadius: '50%', background: 'var(--primary-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--primary)' }}>
                    <DollarSign size={20} />
                  </div>
                  <h2 style={{ fontSize: 20, fontWeight: 900, color: 'var(--text-primary)', letterSpacing: '-0.3px', margin: 0 }}>Set Your Deal</h2>
                </div>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0, lineHeight: 1.5 }}>Tell your Buyer AI what you're comfortable paying.</p>
              </div>
              <button onClick={() => setShowDealModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: 'var(--text-tertiary)' }}>
                <X size={20} />
              </button>
            </div>

            {/* Product Summary */}
            <div style={{ margin: '16px 28px', padding: '12px 16px', background: 'var(--bg-subtle)', borderRadius: 'var(--r-md)', border: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{pendingProduct.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{pendingProduct.category}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Catalog Price</div>
                <div style={{ fontSize: 16, fontWeight: 900, color: 'var(--text-primary)' }}>₹{Number(pendingProduct.price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
              </div>
            </div>

            {/* Form Fields */}
            <div style={{ padding: '0 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Maximum Budget */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 6 }}>What's your maximum budget?</label>
                <div style={{ display: 'flex', alignItems: 'center', border: '2px solid var(--border)', borderRadius: 10, padding: '0 12px', transition: 'border-color 0.15s', background: '#fff' }}
                  onFocus={(e) => e.currentTarget.style.borderColor = 'var(--primary)'}
                  onBlur={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
                >
                  <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-tertiary)', marginRight: 4 }}>₹</span>
                  <input
                    type="number"
                    value={modalBudgetMax}
                    onChange={(e) => { setModalBudgetMax(e.target.value); setModalValidationError(null); }}
                    placeholder="e.g., 3600"
                    style={{ flex: 1, border: 'none', outline: 'none', fontSize: 16, fontWeight: 600, padding: '12px 4px', background: 'transparent', color: 'var(--text-primary)' }}
                    autoFocus
                  />
                </div>
              </div>

              {/* Preferred Price */}
              <div>
                <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 6 }}>What price would you like to get?</label>
                <div style={{ display: 'flex', alignItems: 'center', border: '2px solid var(--border)', borderRadius: 10, padding: '0 12px', transition: 'border-color 0.15s', background: '#fff' }}
                  onFocus={(e) => e.currentTarget.style.borderColor = 'var(--primary)'}
                  onBlur={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
                >
                  <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-tertiary)', marginRight: 4 }}>₹</span>
                  <input
                    type="number"
                    value={modalPreferredPrice}
                    onChange={(e) => { setModalPreferredPrice(e.target.value); setModalValidationError(null); }}
                    placeholder="e.g., 3400 (optional)"
                    style={{ flex: 1, border: 'none', outline: 'none', fontSize: 16, fontWeight: 600, padding: '12px 4px', background: 'transparent', color: 'var(--text-primary)' }}
                  />
                </div>
              </div>

              {/* Helper text */}
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.5, padding: '4px 0' }}>
                <ShieldCheck size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
                Your Buyer AI will negotiate toward your preferred price while never exceeding your maximum budget.
              </div>

              {/* Validation error */}
              {modalValidationError && (
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(239,68,68,0.06)', padding: '8px 12px', borderRadius: 8 }}>
                  <AlertCircle size={14} />
                  {modalValidationError}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div style={{ padding: '20px 28px 24px', display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 8 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowDealModal(false)}
                style={{ padding: '10px 20px', fontSize: 13, fontWeight: 600 }}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleStartNegotiation}
                style={{ padding: '10px 24px', fontSize: 14, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8, borderRadius: 10, boxShadow: '0 4px 12px rgba(67,97,238,0.25)' }}
              >
                <Bot size={16} />
                <span>Continue to AI Negotiation →</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal animation */}
      <style>{`
        @keyframes fadeInScale {
          from { opacity: 0; transform: scale(0.95); }
          to { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}
