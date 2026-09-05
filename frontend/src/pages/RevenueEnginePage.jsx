import React, { useState } from 'react';
import { Zap, Search, CheckCircle2, Package, Tag, TrendingUp, Bot } from 'lucide-react';
import { aiApi } from '../api/ai';
import StatusBadge from '../components/StatusBadge';
import DecisionTrace from '../components/DecisionTrace';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';
import EmptyState from '../components/EmptyState';

const SAMPLE_PROMPTS = [
  'I need a mechanical gaming keyboard under ₹4,500',
  'Looking for a 27-inch gaming monitor under ₹25,000',
  'Gaming mouse with high DPI under ₹2,000',
  'Smart TV for bedroom under ₹50,000',
];

/* ── Intent Tag ───────────────────────────────────────────────── */
function IntentTag({ label, value, color }) {
  if (!value && value !== 0) return null;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '9px 0', borderBottom: '1px solid var(--border-subtle)' }}>
      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: color || 'var(--text-primary)' }}>
        {Array.isArray(value) ? (value.length ? value.join(', ') : '—') : String(value)}
      </span>
    </div>
  );
}

/* ── Product Match Card ───────────────────────────────────────── */
function ProductCard({ product, onNegotiate }) {
  const inStock = product.inventory_quantity > 0;
  const isLow = inStock && product.inventory_quantity <= 5;
  return (
    <div className="card card-hover" style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{product.name}</span>
        <span style={{
          fontSize: 10, fontWeight: 700, padding: '3px 8px', borderRadius: 'var(--r-pill)',
          background: 'var(--success-dim)', color: 'var(--success)', border: '1px solid rgba(5,150,105,0.12)',
        }}>Match</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 12 }}>{product.category}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.4px', color: 'var(--text-primary)' }}>
          ₹{product.price}
        </span>
        <span style={{ fontSize: 12, fontWeight: 600, color: isLow ? 'var(--warning)' : (!inStock ? 'var(--danger)' : 'var(--success)') }}>
          {!inStock ? 'Out of stock' : isLow ? `${product.inventory_quantity} left` : `${product.inventory_quantity} in stock`}
        </span>
      </div>
      {onNegotiate && (
        <button className="btn btn-secondary btn-sm" style={{ marginTop: 12, width: '100%', justifyContent: 'center' }} onClick={() => onNegotiate(product)}>
          <Bot size={12} /> Negotiate with AI
        </button>
      )}
    </div>
  );
}

export default function RevenueEnginePage({ merchantId, onStartNegotiationWithProduct }) {
  const [query, setQuery] = useState(SAMPLE_PROMPTS[0]);
  const [loadingIntent, setLoadingIntent] = useState(false);
  const [loadingDecision, setLoadingDecision] = useState(false);
  const [error, setError] = useState(null);
  const [intentData, setIntentData] = useState(null);
  const [productMatches, setProductMatches] = useState([]);
  const [decisionData, setDecisionData] = useState(null);

  const handleAnalyze = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setLoadingIntent(true); setError(null); setDecisionData(null);
    try {
      const res = await aiApi.extractIntent(query.trim());
      setIntentData(res?.intent || null);
      setProductMatches(res?.matches || []);
    } catch (err) {
      setError(err.message || 'Failed to extract buyer intent.');
    } finally { setLoadingIntent(false); }
  };

  const handleDecision = async () => {
    if (!query.trim()) return;
    setLoadingDecision(true); setError(null);
    try {
      const res = await aiApi.getDecision(query.trim(), merchantId);
      setDecisionData(res?.selected_decision || null);
    } catch (err) {
      setError(err.message || 'Decision engine failed.');
    } finally { setLoadingDecision(false); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }} className="fade-up">
      {/* Header */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--indigo)', marginBottom: 6 }}>
          AI Revenue Engine
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.5px', marginBottom: 6 }}>
          Turn buyer intent into the most profitable compliant action.
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
          Natural language parsing → product matching → bounded revenue optimization → autonomous decision.
        </p>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {/* Input */}
      <div className="card" style={{ padding: 24 }}>
        <div style={{ marginBottom: 12, fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
          What is the buyer looking for?
        </div>
        <form onSubmit={handleAnalyze} style={{ display: 'flex', gap: 12 }}>
          <input
            className="input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. I need a mechanical gaming keyboard under ₹4,500"
            style={{ flex: 1, fontSize: 15, padding: '11px 16px' }}
          />
          <button type="submit" className="btn btn-primary btn-lg" disabled={loadingIntent || !query.trim()}>
            <Search size={15} /> Run Revenue Analysis
          </button>
        </form>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 14 }}>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)', paddingTop: 3 }}>Try:</span>
          {SAMPLE_PROMPTS.map((p, i) => (
            <button key={i} onClick={() => setQuery(p)} style={{
              background: '#fff', border: '1px solid var(--border)',
              color: 'var(--text-tertiary)', borderRadius: 'var(--r-pill)',
              fontSize: 12, padding: '4px 12px', cursor: 'pointer',
              transition: 'all 0.12s', boxShadow: 'var(--shadow-xs)',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.borderColor = '#D1D5DB'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; e.currentTarget.style.borderColor = 'var(--border)'; }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {loadingIntent && <LoadingSpinner text="Extracting intent and matching catalog products…" />}

      {/* Results 3-column */}
      {intentData && (
        <div style={{ display: 'grid', gridTemplateColumns: '240px 1fr 280px', gap: 20, alignItems: 'start' }}>
          {/* Buyer Intent */}
          <div className="card card-sm">
            <div className="card-header" style={{ marginBottom: 12 }}>
              <span className="card-title"><Tag size={14} color="var(--cyan)" />Buyer Intent</span>
            </div>
            <IntentTag label="Category"    value={intentData.category}     color="var(--indigo)" />
            <IntentTag label="Budget"      value={intentData.budget_max ? `₹${Number(intentData.budget_max).toLocaleString()}` : 'Flexible'} color="var(--success)" />
            <IntentTag label="Quantity"    value={intentData.quantity || 1} />
            <IntentTag label="Constraints" value={intentData.hard_constraints} />
            <IntentTag label="Use Case"    value={intentData.use_cases} />
            <IntentTag label="Preferences" value={intentData.preferences} />
          </div>

          {/* Product Matches */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Package size={14} color="var(--success)" />
              Product Matches ({productMatches.length})
            </div>
            {productMatches.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
                {productMatches.map((p) => (
                  <ProductCard key={p.id} product={p} onNegotiate={onStartNegotiationWithProduct} />
                ))}
              </div>
            ) : (
              <EmptyState icon={Package} title="No products matched" description="Adjust the buyer query or add relevant products to the catalog." />
            )}

            {/* Decision Engine */}
            <div className="card" style={{ marginTop: 20, padding: '16px 20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 3 }}>
                    Run Autonomous Decision Engine
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    Evaluates margin bounds, strategy alternatives, and selects the optimal action.
                  </div>
                </div>
                <button className="btn btn-primary" onClick={handleDecision} disabled={loadingDecision} style={{ flexShrink: 0 }}>
                  <TrendingUp size={14} /> {loadingDecision ? 'Evaluating…' : 'Get Decision'}
                </button>
              </div>
            </div>

            {loadingDecision && <LoadingSpinner text="Evaluating policy bounds and decision trace…" />}
          </div>

          {/* AI Recommendation */}
          {decisionData ? (
            <div className="card card-sm" style={{ borderColor: 'rgba(67,97,238,0.25)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--indigo)', marginBottom: 12 }}>
                AI Recommendation
              </div>
              <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--indigo)', letterSpacing: '-0.3px', marginBottom: 6 }}>
                {decisionData.selected_action || 'OFFER_DISCOUNT'}
              </div>
              {decisionData.selected_opportunity?.proposed_price && (
                <div style={{ fontSize: 28, fontWeight: 900, letterSpacing: '-1px', color: 'var(--text-primary)', marginBottom: 16 }}>
                  ₹{decisionData.selected_opportunity.proposed_price}
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, color: 'var(--success)', fontWeight: 600 }}>
                  <CheckCircle2 size={14} /> Margin compliant
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, color: 'var(--success)', fontWeight: 600 }}>
                  <CheckCircle2 size={14} /> Discount within limit
                </div>
                {decisionData.selected_opportunity?.resulting_margin_percent && (
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', paddingLeft: 21 }}>
                    Margin: {decisionData.selected_opportunity.resulting_margin_percent}%
                  </div>
                )}
              </div>
              {decisionData.reason && (
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', borderLeft: '3px solid var(--indigo)', paddingLeft: 12, lineHeight: 1.6, marginBottom: 12 }}>
                  {decisionData.reason}
                </div>
              )}
              <DecisionTrace trace={decisionData.decision_trace} confidence={decisionData.confidence} policyCompliant={true} />
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontSize: 13, flexDirection: 'column', gap: 10, padding: 32 }}>
              <TrendingUp size={28} opacity={0.25} />
              <span>Decision will appear here</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
