import React, { useState, useEffect } from 'react';
import {
  Bot, User, Store, CheckCircle2, XCircle, RefreshCw, Play, Plus,
  CreditCard, Clock, Search, ChevronRight, ShieldCheck, Package, AlertTriangle,
} from 'lucide-react';
import { aiApi } from '../api/ai';
import { launchRazorpayCheckout } from '../api/payments';
import StatusBadge from '../components/StatusBadge';
import DecisionTrace from '../components/DecisionTrace';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';
import EmptyState from '../components/EmptyState';

/* ── Message Bubble ───────────────────────────────────────────── */
function MessageBubble({ ev }) {
  const isSystem = ev.actor === 'SYSTEM' || ev.event_type === 'TIMEOUT' || ev.event_type === 'STARTED';
  const isBuyer = ev.actor === 'BUYER' || ev.actor === 'AI_BUYER';
  const isMerchant = ev.actor === 'MERCHANT' || ev.actor === 'AI_MERCHANT';

  if (isSystem) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0' }}>
        <div className="neg-bubble neg-bubble-system">{ev.message || ev.event_type}</div>
      </div>
    );
  }

  const chipClass = !ev.decision ? '' : ev.decision === 'ACCEPT' ? 'chip-accept' : ev.decision === 'COUNTER' ? 'chip-counter' : 'chip-reject';
  const chipLabel = ev.decision === 'ACCEPT' ? '✓ Accept' : ev.decision === 'COUNTER' ? '⟳ Counter' : ev.decision === 'REJECT' ? '✗ Reject' : '';

  const formatMsg = (msg) => {
    if (!msg) return '';
    // Format any legacy walk-away messages empathetically
    const match = msg.match(/Merchant offer (?:₹|INR)?\s*([0-9,]+(?:\.[0-9]{1,2})?) exceeds walk-away price/i);
    if (match) {
      const price = match[1];
      return `Sorry! ₹${price} is our best and final price. We've already applied the maximum discount we can offer. If this doesn't fit your budget, we completely understand.`;
    }
    return msg;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isBuyer ? 'flex-start' : 'flex-end', padding: '6px 0' }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 5 }}>
        {isBuyer ? <User size={11} color="var(--cyan)" /> : <Store size={11} color="var(--indigo)" />}
        {isBuyer ? 'AI Buyer' : 'AI Merchant'} · Round {ev.round_number}
      </div>
      <div className={`neg-bubble ${isBuyer ? 'neg-bubble-buyer' : 'neg-bubble-merchant'}`}>
        {ev.message && <p style={{ fontSize: 13, lineHeight: 1.55, margin: 0 }}>{formatMsg(ev.message)}</p>}
        {ev.proposed_price && (
          <div className={`neg-offer-price ${isBuyer ? 'buyer' : 'merchant'}`}>₹{ev.proposed_price}</div>
        )}
        {chipLabel && <span className={`neg-decision-chip ${chipClass}`}>{chipLabel}</span>}
      </div>
    </div>
  );
}

/* ── Start Modal ──────────────────────────────────────────────── */
function StartNegotiationModal({ products, initialProductId, onStart, onClose }) {
  const [selectedProduct, setSelectedProduct] = useState(initialProductId ? String(initialProductId) : '');
  const [buyerProfile, setBuyerProfile] = useState({
    name: 'Alex Kumar', budget: '', price_sensitivity: 'HIGH', loyalty: 'NEW',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleStart = async () => {
    if (!selectedProduct || !buyerProfile.budget) { setError('Select product and enter budget.'); return; }
    setLoading(true); setError(null);
    try {
      const prodObj = products.find(p => String(p.id) === String(selectedProduct));
      await onStart({
        productId: selectedProduct,
        buyerProfile: {
          ...buyerProfile,
          productName: prodObj?.name,
        },
      });
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to start negotiation.');
    } finally { setLoading(false); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <Bot size={17} color="var(--indigo)" style={{ marginRight: 8 }} />
            New Autonomous Negotiation
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="field">
            <label className="field-label">Product</label>
            <select className="select" value={selectedProduct} onChange={(e) => setSelectedProduct(e.target.value)}>
              <option value="">Choose a product…</option>
              {products.filter(p => p.inventory_quantity > 0).map((p) => (
                <option key={p.id} value={p.id}>{p.name} — ₹{p.price}</option>
              ))}
            </select>
          </div>

          <div className="grid-2">
            <div className="field">
              <label className="field-label">Buyer Name</label>
              <input className="input" value={buyerProfile.name} onChange={(e) => setBuyerProfile(b => ({ ...b, name: e.target.value }))} />
            </div>
            <div className="field">
              <label className="field-label">Max Budget (₹)</label>
              <input className="input" type="number" value={buyerProfile.budget} onChange={(e) => setBuyerProfile(b => ({ ...b, budget: e.target.value }))} placeholder="e.g. 4500" />
            </div>
          </div>

          <div className="grid-2">
            <div className="field">
              <label className="field-label">Price Sensitivity</label>
              <select className="select" value={buyerProfile.price_sensitivity} onChange={(e) => setBuyerProfile(b => ({ ...b, price_sensitivity: e.target.value }))}>
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label">Loyalty</label>
              <select className="select" value={buyerProfile.loyalty} onChange={(e) => setBuyerProfile(b => ({ ...b, loyalty: e.target.value }))}>
                <option value="NEW">New</option>
                <option value="REGULAR">Regular</option>
                <option value="VIP">VIP</option>
              </select>
            </div>
          </div>

          <div className="alert alert-info" style={{ fontSize: 13 }}>
            <Bot size={14} style={{ flexShrink: 0 }} />
            The AI Buyer agent will autonomously negotiate using LLM reasoning within bounded policy.
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 4 }}>
            <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" onClick={handleStart} disabled={loading}>
              {loading ? <RefreshCw size={14} className="spinner" /> : <Play size={14} />}
              {loading ? 'Starting…' : 'Begin Negotiation'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Intelligence Panel (right side) ──────────────────────────── */
function IntelligencePanel({ neg }) {
  const isAgreed = neg.status === 'AGREED';
  const isRejected = neg.status === 'REJECTED' || neg.status === 'TERMINATED';
  const isExpired = neg.status === 'EXPIRED';
  const isActive = !isAgreed && !isRejected && !isExpired;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '18px 20px', height: '100%', overflowY: 'auto' }} className="scroll-y">
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 2 }}>
        Negotiation Intelligence
      </div>

      {/* State */}
      <div className="card card-sm" style={{ padding: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)' }}>Negotiation State</span>
          <StatusBadge status={neg.status} />
        </div>
        <InfoRow label="Session" value={`#${neg.id}`} />
        <InfoRow label="Round" value={`${neg.negotiation_round ?? 0} / ${neg.max_rounds || 3}`} />
        <InfoRow label="Product" value={neg.product_name || '—'} />
        {neg.catalog_price && <InfoRow label="Catalog Price" value={`₹${neg.catalog_price}`} />}
      </div>

      {/* Merchant Policy */}
      <div className="card card-sm" style={{ padding: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <ShieldCheck size={13} color="var(--indigo)" /> Merchant Policy
        </div>
        {neg.merchant_policy ? (
          <>
            <InfoRow label="Min Margin" value={`${neg.merchant_policy.minimum_margin_percent || '—'}%`} />
            <InfoRow label="Max Discount" value={`${neg.merchant_policy.maximum_discount_percent || '—'}%`} />
          </>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Policy loaded at runtime</div>
        )}
      </div>

      {/* Agreement Card */}
      {isAgreed && neg.agreed_price && (
        <div className="card card-sm" style={{ borderColor: 'rgba(5,150,105,0.25)', background: 'var(--success-dim)', padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, color: 'var(--success)', fontWeight: 700, fontSize: 13 }}>
            <CheckCircle2 size={15} /> Agreement Reached
          </div>
          <div style={{ fontSize: 28, fontWeight: 900, letterSpacing: '-1px', color: 'var(--text-primary)', marginBottom: 10 }}>
            ₹{neg.agreed_price}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--success)', display: 'flex', alignItems: 'center', gap: 5 }}><CheckCircle2 size={11} /> Buyer AI accepted</span>
            <span style={{ fontSize: 12, color: 'var(--success)', display: 'flex', alignItems: 'center', gap: 5 }}><CheckCircle2 size={11} /> Policy compliant</span>
            <span style={{ fontSize: 12, color: 'var(--info)', display: 'flex', alignItems: 'center', gap: 5, marginTop: 4 }}><CreditCard size={11} /> Payment ready</span>
          </div>
        </div>
      )}

      {/* Rejection Card */}
      {isRejected && (
        <div className="card card-sm" style={{ borderColor: 'rgba(220,38,38,0.15)', padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, color: 'var(--danger)', fontWeight: 700, fontSize: 13 }}>
            <XCircle size={15} /> Negotiation Rejected
          </div>
          {neg.termination_reason && (
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', borderLeft: '3px solid var(--danger)', paddingLeft: 10, lineHeight: 1.6, marginBottom: 8 }}>
              {neg.termination_reason}
            </div>
          )}
          <InfoRow label="Settlement" value="No agreement" color="var(--text-tertiary)" />
        </div>
      )}

      {/* Expired Card */}
      {isExpired && (
        <div className="card card-sm" style={{ padding: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-tertiary)', marginBottom: 4 }}>Negotiation Expired</div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Session timed out without agreement.</div>
        </div>
      )}

      {/* Decision Trace */}
      {neg.decision_trace?.length > 0 && <DecisionTrace trace={neg.decision_trace} />}
    </div>
  );
}

function InfoRow({ label, value, color }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
      <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: color || 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}

/* ── Chat Panel (center) ──────────────────────────────────────── */
function ChatPanel({ neg, merchant, onInitiatePayment }) {
  const [payLoading, setPayLoading] = useState(false);
  const [payError, setPayError] = useState(null);
  const [paySuccess, setPaySuccess] = useState(null);

  const openCheckoutForTxn = async (txn) => {
    setPayLoading(true);
    setPayError(null);
    try {
      await launchRazorpayCheckout({
        txn,
        onSuccess: (verifiedTxn) => {
          setPaySuccess(verifiedTxn);
          onInitiatePayment && onInitiatePayment(verifiedTxn);
        },
        onError: (err) => {
          setPayError(err.message || 'Razorpay checkout failed.');
        },
        onDismiss: () => {
          // Keep the existing transaction info visible
          setPaySuccess(txn);
        },
      });
    } catch (err) {
      setPayError(err.message || 'Failed to open Razorpay checkout.');
    } finally {
      setPayLoading(false);
    }
  };

  const handlePay = async () => {
    setPayLoading(true);
    setPayError(null);
    try {
      const res = await aiApi.initiatePayment(neg.id);
      setPaySuccess(res);
      onInitiatePayment && onInitiatePayment(res);
      if (res.status !== 'PAYMENT_CAPTURED' && res.razorpay_order_id && res.razorpay_key_id) {
        await openCheckoutForTxn(res);
      }
    } catch (err) {
      setPayError(err.message || 'Payment initiation failed.');
    } finally {
      setPayLoading(false);
    }
  };

  const isAgreed = neg.status === 'AGREED';
  const isRejected = neg.status === 'REJECTED' || neg.status === 'TERMINATED';
  const events = neg.events || neg.negotiation_history || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header banner */}
      <div style={{ padding: '16px 22px', borderBottom: '1px solid var(--border)', background: '#fff', flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.2px' }}>
              {neg.product_name || 'Product'}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 3 }}>
              Session #{neg.id} · Round {neg.negotiation_round ?? 0} of {neg.max_rounds || 3} · {events.length} event{events.length !== 1 ? 's' : ''}
            </div>
          </div>
          <StatusBadge status={neg.status} />
        </div>

        {/* Agent headers */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16, gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', background: 'var(--cyan-dim)', borderRadius: 'var(--r-md)', border: '1px solid rgba(8,145,178,0.1)', flex: 1 }}>
            <User size={16} color="var(--cyan)" />
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>Buyer AI</div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Value Seeker</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 10px', color: 'var(--text-tertiary)', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            ↔
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', background: 'var(--indigo-dim)', borderRadius: 'var(--r-md)', border: '1px solid rgba(67,97,238,0.1)', flex: 1, justifyContent: 'flex-end', textAlign: 'right' }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)' }}>Merchant AI{merchant?.business_name ? ` · ${merchant.business_name}` : ''}</div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Policy Bounded</div>
            </div>
            <Store size={16} color="var(--indigo)" />
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="scroll-y" style={{ flex: 1, padding: '16px 22px', display: 'flex', flexDirection: 'column', gap: 4, background: 'var(--bg-root)' }}>
        {events.length > 0
          ? events.map((ev, i) => <MessageBubble key={i} ev={ev} />)
          : (
            <EmptyState icon={Clock} title="No rounds yet" description="The AI negotiation has not started or has no events logged." />
          )}
      </div>

      {/* Footer */}
      <div style={{ padding: '14px 22px', borderTop: '1px solid var(--border)', background: '#fff', flexShrink: 0 }}>
        {payError && <ErrorBanner message={payError} onDismiss={() => setPayError(null)} />}
        {paySuccess && (
          <div className={`alert ${paySuccess.status === 'PAYMENT_CAPTURED' ? 'alert-success' : 'alert-info'}`} style={{ marginBottom: 10, fontSize: 13, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <CheckCircle2 size={15} color={paySuccess.status === 'PAYMENT_CAPTURED' ? 'var(--success)' : 'var(--primary)'} />
              <span>{paySuccess.status === 'PAYMENT_CAPTURED' ? 'Payment Captured & Verified:' : 'Razorpay Test Mode Order Created:'}</span>
              <strong style={{ fontFamily: 'var(--font-mono)' }}>{paySuccess.status === 'PAYMENT_CAPTURED' ? paySuccess.razorpay_payment_id : paySuccess.razorpay_order_id}</strong>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', paddingLeft: 21 }}>
              Amount: ₹{paySuccess.agreed_amount || neg.agreed_price} · Status: <strong>{paySuccess.status}</strong> · {paySuccess.status === 'PAYMENT_CAPTURED' ? '✓ Inventory settlement complete (-1)' : 'Awaiting payment capture.'}
            </div>
          </div>
        )}
        {isAgreed && (!paySuccess || paySuccess.status !== 'PAYMENT_CAPTURED') && (
          <button
            className="btn btn-success btn-lg"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={paySuccess ? () => openCheckoutForTxn(paySuccess) : handlePay}
            disabled={payLoading}
          >
            <CreditCard size={15} /> {payLoading ? 'Launching Razorpay Checkout…' : paySuccess ? 'Open Razorpay Test Checkout' : `Proceed to Razorpay Test Payment · ₹${neg.agreed_price}`}
          </button>
        )}
        {isRejected && (
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)', textAlign: 'center', padding: '4px 0' }}>
            Session ended · {neg.termination_reason?.toLowerCase().includes('walk-away') || neg.termination_reason?.toLowerCase().includes('margin') ? 'Offer exceeded buyer budget' : (neg.termination_reason || 'No agreement reached')}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Main Page ────────────────────────────────────────────────── */
export default function NegotiationsPage({ merchantId, merchant, products = [], negotiations, onRefresh, preselectedProductId }) {
  const [localNegs, setLocalNegs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedNegId, setSelectedNegId] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [filter, setFilter] = useState('ALL');
  const [searchQ, setSearchQ] = useState('');

  const fetchNegs = async () => {
    setLoading(true); setError(null);
    try {
      const res = await aiApi.listNegotiations(merchantId);
      const list = Array.isArray(res) ? res : (res?.results || []);
      setLocalNegs(list);
      if (list.length > 0 && !selectedNegId) setSelectedNegId(list[0].id);
    } catch (err) {
      setError(err.message || 'Failed to load negotiations.');
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchNegs(); }, [merchantId]);
  useEffect(() => { if (preselectedProductId) setShowModal(true); }, [preselectedProductId]);

  const handleStart = async ({ productId, buyerProfile }) => {
    const res = await aiApi.startNegotiation(merchantId, productId, buyerProfile);
    await fetchNegs();
    setSelectedNegId(res?.session?.id || res?.session?.negotiation_id || res?.id || null);
  };

  const STATUS_FILTERS = ['ALL', 'AGREED', 'ACTIVE', 'REJECTED', 'EXPIRED'];
  let filtered = localNegs;
  if (filter !== 'ALL') filtered = filtered.filter(n => n.status === filter);
  if (searchQ) filtered = filtered.filter(n => (n.product_name || '').toLowerCase().includes(searchQ.toLowerCase()) || String(n.id).includes(searchQ));

  const selectedNeg = filtered.find(n => n.id === selectedNegId) || localNegs.find(n => n.id === selectedNegId);

  return (
    <div style={{ display: 'flex', gap: 0, height: 'calc(100vh - var(--topbar-h))', overflow: 'hidden' }} className="fade-up">

      {/* List sidebar */}
      <div style={{
        width: 290, flexShrink: 0, borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        background: '#fff',
      }}>
        <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 7 }}>
              <Bot size={15} color="var(--indigo)" /> Negotiations
              <span style={{ fontSize: 10, fontWeight: 700, background: 'var(--indigo-dim)', color: 'var(--indigo)', padding: '2px 7px', borderRadius: 999 }}>
                {localNegs.length}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="btn btn-ghost btn-sm" onClick={fetchNegs} title="Refresh"><RefreshCw size={13} /></button>
              <button className="btn btn-primary btn-sm" onClick={() => setShowModal(true)}><Plus size={13} /> New</button>
            </div>
          </div>
          <div style={{ position: 'relative' }}>
            <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
            <input className="input" value={searchQ} onChange={(e) => setSearchQ(e.target.value)} placeholder="Search…" style={{ paddingLeft: 30, fontSize: 13 }} />
          </div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 10 }}>
            {STATUS_FILTERS.map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`} style={{ fontSize: 10, padding: '3px 8px' }}>
                {f}
              </button>
            ))}
          </div>
        </div>

        <ErrorBanner message={error} onDismiss={() => setError(null)} />
        {loading && <LoadingSpinner text="Loading…" />}

        <div className="scroll-y" style={{ flex: 1 }}>
          {!loading && filtered.length === 0 && (
            <div style={{ padding: 20 }}>
              <EmptyState icon={Bot} title="No negotiations" description="Start one with the + New button." />
            </div>
          )}
          {filtered.map((neg) => {
            const isActive = neg.id === selectedNegId;
            return (
              <div
                key={neg.id}
                onClick={() => setSelectedNegId(neg.id)}
                style={{
                  padding: '13px 16px',
                  borderBottom: '1px solid var(--border-subtle)',
                  cursor: 'pointer',
                  background: isActive ? 'var(--indigo-dim)' : '#fff',
                  borderLeft: isActive ? '3px solid var(--indigo)' : '3px solid transparent',
                  transition: 'all 0.1s',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', flex: 1, marginRight: 8 }}>
                    {neg.product_name || `Session #${neg.id}`}
                  </span>
                  <StatusBadge status={neg.status} />
                </div>
                {neg.agreed_price && (
                  <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--success)', letterSpacing: '-0.3px' }}>₹{neg.agreed_price}</div>
                )}
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                  {neg.created_at ? new Date(neg.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                  {` · Round ${neg.negotiation_round ?? 0}/${neg.max_rounds || 3}`}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Center: Chat */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        {selectedNeg
          ? <ChatPanel neg={selectedNeg} merchant={merchant} onInitiatePayment={fetchNegs} />
          : (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-root)' }}>
              <EmptyState icon={Bot} title="Select a negotiation" description="Click any session on the left to view the full AI-to-AI transcript." />
            </div>
          )}
      </div>

      {/* Right: Intelligence */}
      {selectedNeg && (
        <div style={{
          width: 280, flexShrink: 0, borderLeft: '1px solid var(--border)',
          background: '#fff', overflow: 'hidden',
        }}>
          <IntelligencePanel neg={selectedNeg} />
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <StartNegotiationModal
          products={products}
          initialProductId={preselectedProductId}
          onStart={handleStart}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
