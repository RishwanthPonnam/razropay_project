import React, { useState, useEffect, useCallback } from 'react';
import {
  CreditCard, RefreshCw, CheckCircle2, AlertTriangle,
  Search, Info, XCircle,
} from 'lucide-react';
import { paymentsApi, launchRazorpayCheckout } from '../api/payments';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';
import EmptyState from '../components/EmptyState';

/* ── Detail Row ───────────────────────────────────────────────── */
function Row({ label, value, mono, color }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
      <span style={{ fontSize: 12, color: 'var(--text-tertiary)', flexShrink: 0, marginRight: 16 }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 600, fontFamily: mono ? 'var(--font-mono)' : undefined, color: color || 'var(--text-primary)', textAlign: 'right', wordBreak: 'break-all' }}>
        {value || '—'}
      </span>
    </div>
  );
}

/* ── Transaction Detail ───────────────────────────────────────── */
function TransactionDetail({ txn, merchantId, onRefresh }) {
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [verifyError, setVerifyError] = useState(null);
  const [checkoutLoading, setCheckoutLoading] = useState(false);

  const handleOpenCheckout = async () => {
    setCheckoutLoading(true);
    setVerifyError(null);
    try {
      await launchRazorpayCheckout({
        txn,
        onSuccess: (verifiedTxn) => {
          setVerifyResult(verifiedTxn);
          onRefresh && onRefresh();
        },
        onError: (err) => {
          setVerifyError(err.message || 'Razorpay checkout failed.');
        },
        onDismiss: () => {},
      });
    } catch (err) {
      setVerifyError(err.message || 'Failed to open Razorpay checkout.');
    } finally {
      setCheckoutLoading(false);
    }
  };

  const handleVerify = async () => {
    setVerifying(true); setVerifyError(null);
    try {
      const res = await paymentsApi.verifySignature(
        txn.id,
        txn.razorpay_payment_id || `pay_${Date.now()}`,
        'simulated_signature'
      );
      setVerifyResult(res);
      onRefresh && onRefresh();
    } catch (err) {
      setVerifyError(err.message || 'Verification signature rejected by server.');
    } finally { setVerifying(false); }
  };

  if (!txn) return null;
  const amount = txn.agreed_amount ?? ((txn.amount_minor_units || 0) / 100);
  const isCaptured = txn.status === 'PAYMENT_CAPTURED';
  const isFailed   = txn.status === 'PAYMENT_FAILED';
  const isPending  = txn.status === 'ORDER_CREATED' || txn.status === 'PAYMENT_PENDING';

  // Lifecycle steps
  const steps = [
    { label: 'Order Created', done: true },
    { label: 'Payment Pending', done: txn.status !== 'CREATED' },
    { label: 'Payment Captured', done: isCaptured, error: isFailed },
    { label: 'Settlement Complete', done: isCaptured },
  ];

  return (
    <div style={{ padding: '24px 28px', height: '100%', overflowY: 'auto' }} className="scroll-y">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-primary)' }}>
            {txn.product_name || 'Transaction'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 2 }}>
            Buyer: <strong>{txn.buyer_name || 'AI Buyer'}</strong>
          </div>
        </div>
        <StatusBadge status={txn.status} />
      </div>
      <div style={{ fontSize: 32, fontWeight: 900, letterSpacing: '-1px', color: isCaptured ? 'var(--success)' : 'var(--text-primary)', marginBottom: 20 }}>
        ₹{Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>

      {/* Payment Lifecycle Stepper */}
      <div className="card card-sm" style={{ marginBottom: 16, padding: '14px 16px' }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
          Payment & Settlement Lifecycle
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4 }}>
          {steps.map((st, i) => (
            <React.Fragment key={st.label}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flex: 1, textAlign: 'center' }}>
                <div style={{
                  width: 20, height: 20, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 10, fontWeight: 700,
                  background: st.error ? 'var(--danger-dim)' : st.done ? 'var(--success-dim)' : 'var(--bg-secondary)',
                  color: st.error ? 'var(--danger)' : st.done ? 'var(--success)' : 'var(--text-tertiary)',
                  border: `1px solid ${st.error ? 'var(--danger)' : st.done ? 'var(--success)' : 'var(--border)'}`,
                }}>
                  {st.error ? '✗' : st.done ? '✓' : i + 1}
                </div>
                <span style={{ fontSize: 10, fontWeight: 600, color: st.error ? 'var(--danger)' : st.done ? 'var(--text-primary)' : 'var(--text-tertiary)' }}>
                  {st.label}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div style={{ height: 2, flex: 1, background: steps[i + 1].done ? 'var(--success)' : 'var(--border)', margin: '0 4px', marginBottom: 16 }} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* IDs card */}
      <div className="card card-sm" style={{ marginBottom: 16 }}>
        <Row label="Transaction ID"    value={`#${txn.id}`}                              mono />
        <Row label="Razorpay Order ID" value={txn.razorpay_order_id || '—'}              mono />
        <Row label="Razorpay Pymt ID"  value={txn.razorpay_payment_id || '—'}            mono />
        <Row label="Negotiation Ref"   value={txn.negotiation_id ? `#${txn.negotiation_id}` : '—'} />
        <Row label="Buyer"             value={txn.buyer_name || 'AI Buyer'} />
        <Row label="Currency"          value={txn.currency || 'INR'} />
        <Row label="Created"           value={txn.created_at ? new Date(txn.created_at).toLocaleString('en-IN') : '—'} />
        <Row label="Updated"           value={txn.updated_at ? new Date(txn.updated_at).toLocaleString('en-IN') : '—'} />
        <Row label="Payment Verified"  value={txn.payment_verified ? '✓ Yes' : 'Pending'} color={txn.payment_verified ? 'var(--success)' : undefined} />
        <Row label="Settlement State"  value={isCaptured ? '✓ Inventory Decremented (-1)' : 'Pending Capture'} color={isCaptured ? 'var(--success)' : 'var(--text-tertiary)'} />
        {txn.failure_reason && (
          <Row label="Failure Reason"  value={txn.failure_reason} color="var(--danger)" />
        )}
      </div>

      {/* Test mode */}
      <div className="alert alert-info" style={{ fontSize: 13, marginBottom: 16 }}>
        <Info size={14} style={{ flexShrink: 0 }} />
        Razorpay Test Mode transaction. No real money was charged.
      </div>

      {/* Actions */}
      {isPending && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <ErrorBanner message={verifyError} onDismiss={() => setVerifyError(null)} />
          {verifyResult && (
            <div className="alert alert-success" style={{ fontSize: 13 }}>
              <CheckCircle2 size={14} />
              Verification: <strong>{verifyResult.status || 'OK'}</strong>
              {verifyResult.status === 'PAYMENT_CAPTURED' && ' · Inventory decremented.'}
            </div>
          )}
          <button
            className="btn btn-success btn-lg"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={handleOpenCheckout}
            disabled={checkoutLoading || !txn.razorpay_order_id}
          >
            <CreditCard size={15} /> {checkoutLoading ? 'Opening Razorpay Checkout…' : 'Open Razorpay Test Checkout'}
          </button>
          <button
            className="btn btn-secondary btn-md"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={handleVerify}
            disabled={verifying}
          >
            <CheckCircle2 size={14} /> {verifying ? 'Verifying…' : 'Verify Payment Status'}
          </button>
        </div>
      )}
      {isCaptured && (
        <div className="alert alert-success" style={{ fontSize: 13 }}>
          <CheckCircle2 size={14} />
          Payment confirmed and captured · Inventory settlement complete
        </div>
      )}
      {isFailed && (
        <div className="alert alert-error" style={{ fontSize: 13 }}>
          <AlertTriangle size={14} />
          Payment failed or expired: {txn.failure_reason || 'No amount was captured.'}
        </div>
      )}
    </div>
  );
}

/* ── Main ─────────────────────────────────────────────────────── */
export default function TransactionsPage({ merchantId }) {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [filter, setFilter] = useState('ALL');
  const [searchQ, setSearchQ] = useState('');

  const fetchTransactions = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await paymentsApi.listTransactions(merchantId);
      const list = Array.isArray(res) ? res : (res?.results || []);
      setTransactions(list);
      if (list.length > 0 && !selectedId) setSelectedId(list[0].id);
    } catch (err) {
      setError(err.message || 'Failed to load transactions.');
    } finally { setLoading(false); }
  }, [merchantId]);

  useEffect(() => { fetchTransactions(); }, [fetchTransactions]);

  const STATUS_FILTERS = ['ALL', 'PAYMENT_CAPTURED', 'ORDER_CREATED', 'PAYMENT_FAILED'];
  let filtered = transactions;
  if (filter !== 'ALL') filtered = filtered.filter(t => t.status === filter);
  if (searchQ) filtered = filtered.filter(t =>
    (t.product_name || '').toLowerCase().includes(searchQ.toLowerCase()) ||
    (t.razorpay_order_id || '').toLowerCase().includes(searchQ.toLowerCase()) ||
    String(t.id).includes(searchQ)
  );

  const selectedTxn = filtered.find(t => t.id === selectedId) || transactions.find(t => t.id === selectedId);

  return (
    <div style={{ display: 'flex', gap: 0, height: 'calc(100vh - var(--topbar-h))', overflow: 'hidden' }} className="fade-up">
      {/* List */}
      <div style={{
        width: 340, flexShrink: 0, borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        background: '#fff',
      }}>
        <div style={{ padding: '16px 16px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 7 }}>
              <CreditCard size={15} color="var(--info)" /> Transactions
              <span style={{ fontSize: 10, fontWeight: 700, background: 'var(--info-dim)', color: 'var(--info)', padding: '2px 7px', borderRadius: 999 }}>
                {transactions.length}
              </span>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={fetchTransactions}><RefreshCw size={13} /></button>
          </div>
          <div style={{ position: 'relative' }}>
            <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
            <input className="input" value={searchQ} onChange={(e) => setSearchQ(e.target.value)} placeholder="Search…" style={{ paddingLeft: 30, fontSize: 13 }} />
          </div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 10 }}>
            {STATUS_FILTERS.map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`} style={{ fontSize: 10, padding: '3px 7px' }}>
                {f.replace('PAYMENT_', '').replace('ORDER_', 'ORD ')}
              </button>
            ))}
          </div>
        </div>

        {loading && <LoadingSpinner text="Loading…" />}
        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        <div className="scroll-y" style={{ flex: 1 }}>
          {!loading && filtered.length === 0 && (
            <div style={{ padding: 20 }}>
              <EmptyState icon={CreditCard} title="No transactions" description="Transactions appear once a Razorpay order is created." />
            </div>
          )}
          {filtered.map((txn) => {
            const isActive = txn.id === selectedId;
            const amount = txn.agreed_amount ?? ((txn.amount_minor_units || 0) / 100);
            const isCaptured = txn.status === 'PAYMENT_CAPTURED';
            return (
              <div
                key={txn.id}
                onClick={() => setSelectedId(txn.id)}
                style={{
                  padding: '13px 16px',
                  borderBottom: '1px solid var(--border-subtle)',
                  cursor: 'pointer',
                  background: isActive ? 'var(--info-dim)' : '#fff',
                  borderLeft: isActive ? '3px solid var(--info)' : '3px solid transparent',
                  transition: 'all 0.1s',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', flex: 1, marginRight: 8 }}>
                    {txn.product_name || `Transaction #${txn.id}`}
                  </span>
                  <StatusBadge status={txn.status} />
                </div>
                <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.3px', color: isCaptured ? 'var(--success)' : 'var(--text-primary)', marginBottom: 2 }}>
                  ₹{Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </div>
                {txn.razorpay_order_id && (
                  <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
                    {txn.razorpay_order_id}
                  </div>
                )}
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                  {txn.created_at ? new Date(txn.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Detail */}
      <div style={{ flex: 1, overflow: 'hidden', background: 'var(--bg-root)' }}>
        {selectedTxn
          ? <TransactionDetail txn={selectedTxn} merchantId={merchantId} onRefresh={fetchTransactions} />
          : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <EmptyState icon={CreditCard} title="Select a transaction" description="Click any transaction to view full details." />
            </div>
          )}
      </div>
    </div>
  );
}
