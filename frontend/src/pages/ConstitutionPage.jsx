import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck, Save, AlertTriangle, CheckCircle2, Lock,
  ArrowRight, ShieldAlert, Check, RefreshCw, Cpu, Zap, CreditCard, ChevronRight
} from 'lucide-react';
import { merchantsApi } from '../api/merchants';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';

export default function ConstitutionPage({ merchantId }) {
  const [policy, setPolicy] = useState(null);
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [dirty, setDirty] = useState(false);

  const fetchPolicy = useCallback(async () => {
    if (!merchantId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await merchantsApi.getPolicy(merchantId);
      setPolicy(res);
      setForm({ ...res });
      setDirty(false);
    } catch (err) {
      setError(err.message || 'Failed to load merchant policy.');
    } finally {
      setLoading(false);
    }
  }, [merchantId]);

  useEffect(() => {
    fetchPolicy();
  }, [fetchPolicy]);

  const handleChange = (field) => (val) => {
    setForm(f => ({ ...f, [field]: val }));
    setDirty(true);
    setSuccess(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await merchantsApi.updatePolicy(merchantId, {
        minimum_margin_percent: Number(form.minimum_margin_percent),
        maximum_discount_percent: Number(form.maximum_discount_percent),
        maximum_negotiation_rounds: Number(form.maximum_negotiation_rounds),
        auto_approval_limit: Number(form.auto_approval_limit),
      });
      setDirty(false);
      setSuccess('Economic Constitution updated. Autonomous agents are immediately bound by these new parameters.');
      fetchPolicy();
    } catch (err) {
      setError(err.message || 'Failed to update economic constitution.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner text="Loading Economic Constitution…" />;

  const minMargin = form?.minimum_margin_percent ?? 18;
  const maxDiscount = form?.maximum_discount_percent ?? 10;
  const maxRounds = form?.maximum_negotiation_rounds ?? 3;
  const autoLimit = form?.auto_approval_limit ?? 25000;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28, maxWidth: 1040 }} className="fade-up">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{
              fontSize: 11,
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--indigo)',
              background: 'var(--indigo-dim)',
              padding: '2px 8px',
              borderRadius: 'var(--r-pill)',
              border: '1px solid rgba(67,97,238,0.15)'
            }}>
              AI Governance Center
            </span>
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.5px', margin: 0 }}>
            Merchant Economic Constitution
          </h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4, margin: 0, fontStyle: 'italic' }}>
            &ldquo;Rules autonomous agents cannot violate.&rdquo;
          </p>
        </div>

        {dirty && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button
              className="btn btn-secondary"
              onClick={() => { setForm({ ...policy }); setDirty(false); }}
            >
              Reset
            </button>
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={saving}
              style={{ boxShadow: 'var(--shadow-sm)' }}
            >
              <Save size={14} /> {saving ? 'Applying Bounds…' : 'Save Constitution'}
            </button>
          </div>
        )}
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {success && (
        <div className="alert alert-success" style={{ fontSize: 13, background: 'var(--success-dim)', border: '1px solid rgba(5,150,105,0.2)', color: 'var(--success)' }}>
          <CheckCircle2 size={16} />
          <span>{success}</span>
        </div>
      )}

      {/* Four Primary Cards */}
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-tertiary)', marginBottom: 12 }}>
          Core Economic Invariants
        </div>
        <div className="grid-4">
          {/* Minimum Margin */}
          <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', borderTop: '3px solid var(--indigo)' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Minimum Margin
                </span>
                <ShieldCheck size={16} color="var(--indigo)" />
              </div>
              <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-1px', marginBottom: 4 }}>
                {minMargin}%
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.4, margin: 0 }}>
                Strict gross profit floor. Any buyer offer yielding less is automatically rejected.
              </p>
            </div>
            <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--indigo)' }}>✓ Non-negotiable limit</span>
            </div>
          </div>

          {/* Maximum Discount */}
          <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', borderTop: '3px solid #0EA5E9' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Maximum Discount
                </span>
                <Zap size={16} color="#0EA5E9" />
              </div>
              <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-1px', marginBottom: 4 }}>
                {maxDiscount}%
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.4, margin: 0 }}>
                Hard concession ceiling. The AI agent cannot concede more regardless of volume.
              </p>
            </div>
            <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#0EA5E9' }}>✓ Absolute cap</span>
            </div>
          </div>

          {/* Maximum Negotiation Rounds */}
          <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', borderTop: '3px solid var(--amber)' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Max Rounds
                </span>
                <Cpu size={16} color="var(--amber)" />
              </div>
              <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-1px', marginBottom: 4 }}>
                {maxRounds}
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.4, margin: 0 }}>
                Deadlock prevention bound. Sessions terminate after round {maxRounds} if no consensus.
              </p>
            </div>
            <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--amber)' }}>✓ Anti-stalemate</span>
            </div>
          </div>

          {/* Auto Approval Limit */}
          <div className="card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', borderTop: '3px solid var(--success)' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  Auto Approval
                </span>
                <CreditCard size={16} color="var(--success)" />
              </div>
              <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.5px', marginBottom: 4 }}>
                ₹{Number(autoLimit).toLocaleString()}
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.4, margin: 0 }}>
                Instant settlement threshold. Orders below proceed straight to Razorpay Test checkout.
              </p>
            </div>
            <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--success)' }}>✓ Autonomous clearance</span>
            </div>
          </div>
        </div>
      </div>

      {/* Visual Governance Flow */}
      <div className="card" style={{ padding: '26px 28px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.2px' }}>
              Autonomous Governance Enforcement Pipeline
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
              How policies are mathematically enforced from natural language intent to Razorpay payment
            </div>
          </div>
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            color: 'var(--indigo)',
            background: 'var(--indigo-dim)',
            padding: '3px 10px',
            borderRadius: 'var(--r-pill)',
            border: '1px solid rgba(67,97,238,0.15)'
          }}>
            Zero-Trust AI
          </span>
        </div>

        {/* 4-Step Pipeline Flow */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: 16,
          position: 'relative',
        }}>
          {/* Step 1: AI PROPOSES */}
          <div style={{
            background: '#F8FAFC',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r-lg)',
            padding: '18px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            position: 'relative'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 24, height: 24, borderRadius: '50%', background: 'var(--indigo-dim)',
                color: 'var(--indigo)', fontSize: 11, fontWeight: 800, display: 'flex',
                alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(67,97,238,0.2)'
              }}>
                1
              </span>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--indigo)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Generation
              </span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>
              AI PROPOSES
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
              Buyer AI or Merchant AI generates an offer based on customer intent and market parameters.
            </div>
          </div>

          {/* Step 2: CONSTITUTION VALIDATES */}
          <div style={{
            background: 'var(--indigo-dim)',
            border: '1px solid rgba(67,97,238,0.25)',
            borderRadius: 'var(--r-lg)',
            padding: '18px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            position: 'relative'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 24, height: 24, borderRadius: '50%', background: 'var(--indigo)',
                color: '#fff', fontSize: 11, fontWeight: 800, display: 'flex',
                alignItems: 'center', justifyContent: 'center'
              }}>
                2
              </span>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--indigo)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Governance
              </span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--indigo)' }}>
              CONSTITUTION VALIDATES
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.45 }}>
              Strict margin (&ge;{minMargin}%), discount (&le;{maxDiscount}%), and round limit checks reject illegal offers before they leave the node.
            </div>
          </div>

          {/* Step 3: BACKEND AUTHORIZES */}
          <div style={{
            background: '#F8FAFC',
            border: '1px solid var(--border)',
            borderRadius: 'var(--r-lg)',
            padding: '18px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            position: 'relative'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 24, height: 24, borderRadius: '50%', background: 'var(--amber-dim)',
                color: 'var(--amber)', fontSize: 11, fontWeight: 800, display: 'flex',
                alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(217,119,6,0.2)'
              }}>
                3
              </span>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--amber)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Settlement Guard
              </span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>
              BACKEND AUTHORIZES
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.45 }}>
              Server locks stock, generates cryptographically bound agreement hash, and validates approval limits.
            </div>
          </div>

          {/* Step 4: RAZORPAY EXECUTES */}
          <div style={{
            background: 'var(--success-dim)',
            border: '1px solid rgba(5,150,105,0.25)',
            borderRadius: 'var(--r-lg)',
            padding: '18px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
            position: 'relative'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                width: 24, height: 24, borderRadius: '50%', background: 'var(--success)',
                color: '#fff', fontSize: 11, fontWeight: 800, display: 'flex',
                alignItems: 'center', justifyContent: 'center'
              }}>
                4
              </span>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--success)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Payment
              </span>
            </div>
            <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--success)' }}>
              RAZORPAY EXECUTES
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.45 }}>
              Exact agreed amount is dispatched to Razorpay Test Mode order API for instant secure payment checkout.
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Bounds Configuration */}
      <div className="card" style={{ padding: '24px 28px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>
              Configure Constitution Thresholds
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
              Adjust operating bounds. Changes apply in real-time to all future negotiation sessions.
            </div>
          </div>
          <Lock size={16} color="var(--text-tertiary)" />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Row 1: Margins & Discounts */}
          <div className="grid-2">
            <div className="field">
              <label className="field-label">Minimum Gross Margin (%) *</label>
              <div style={{ position: 'relative' }}>
                <input
                  type="number"
                  className="input"
                  value={form?.minimum_margin_percent ?? ''}
                  onChange={(e) => handleChange('minimum_margin_percent')(e.target.value)}
                  min={0}
                  max={100}
                  style={{ fontWeight: 700, fontSize: 15 }}
                />
                <span style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', fontWeight: 600, color: 'var(--text-tertiary)', fontSize: 13 }}>
                  %
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                Offers yielding less than this percentage over cost are immediately rejected.
              </div>
            </div>

            <div className="field">
              <label className="field-label">Maximum Discount Permitted (%) *</label>
              <div style={{ position: 'relative' }}>
                <input
                  type="number"
                  className="input"
                  value={form?.maximum_discount_percent ?? ''}
                  onChange={(e) => handleChange('maximum_discount_percent')(e.target.value)}
                  min={0}
                  max={100}
                  style={{ fontWeight: 700, fontSize: 15 }}
                />
                <span style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', fontWeight: 600, color: 'var(--text-tertiary)', fontSize: 13 }}>
                  %
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                Maximum concession from list price the Merchant AI may provide.
              </div>
            </div>
          </div>

          {/* Row 2: Rounds & Auto Approval */}
          <div className="grid-2">
            <div className="field">
              <label className="field-label">Maximum Negotiation Rounds *</label>
              <div style={{ position: 'relative' }}>
                <input
                  type="number"
                  className="input"
                  value={form?.maximum_negotiation_rounds ?? ''}
                  onChange={(e) => handleChange('maximum_negotiation_rounds')(e.target.value)}
                  min={1}
                  max={20}
                  style={{ fontWeight: 700, fontSize: 15 }}
                />
                <span style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', fontWeight: 600, color: 'var(--text-tertiary)', fontSize: 13 }}>
                  rounds
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                Limits back-and-forth turns to avoid circular stalls and token exhaustion.
              </div>
            </div>

            <div className="field">
              <label className="field-label">Auto-Approval Transaction Limit (₹) *</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', fontWeight: 700, color: 'var(--text-tertiary)', fontSize: 14 }}>
                  ₹
                </span>
                <input
                  type="number"
                  className="input"
                  value={form?.auto_approval_limit ?? ''}
                  onChange={(e) => handleChange('auto_approval_limit')(e.target.value)}
                  min={0}
                  style={{ paddingLeft: 28, fontWeight: 700, fontSize: 15 }}
                />
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                Deals under this amount bypass manual merchant sign-off for instant payment.
              </div>
            </div>
          </div>

          {dirty && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 12, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
              <button
                className="btn btn-secondary"
                onClick={() => { setForm({ ...policy }); setDirty(false); }}
              >
                Revert Changes
              </button>
              <button
                className="btn btn-primary"
                onClick={handleSave}
                disabled={saving}
              >
                <Save size={14} /> {saving ? 'Saving…' : 'Apply Constitution to AI Agents'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
