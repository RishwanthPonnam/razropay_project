import React from 'react';
import {
  Bot, CreditCard, Package, ShieldCheck,
  ArrowRight, Clock, Circle, Zap, TrendingUp, User, Store,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';

/* ── Autonomous Commerce Flow Stepper ─────────────────────────── */
function FlowStepper() {
  const nodes = ['Intent', 'Match', 'Optimize', 'Negotiate', 'Agree', 'Pay', 'Settle'];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', justifyContent: 'center', padding: '16px 0 4px' }}>
      {nodes.map((node, i) => (
        <React.Fragment key={node}>
          <div className="flow-node" style={{ fontSize: 11, padding: '5px 12px' }}>{node}</div>
          {i < nodes.length - 1 && <span style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>→</span>}
        </React.Fragment>
      ))}
    </div>
  );
}

/* ── Activity Item ────────────────────────────────────────────── */
function ActivityItem({ icon: Icon, color, bgColor, title, desc, timestamp, status }) {
  return (
    <div className="timeline-item">
      <div className="timeline-dot" style={{ background: bgColor || '#F9FAFB', borderColor: color ? `${color}30` : undefined }}>
        <Icon size={13} color={color || 'var(--text-tertiary)'} />
      </div>
      <div className="timeline-body">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <span className="timeline-title">{title}</span>
          {status && <StatusBadge status={status} />}
        </div>
        {desc && <p className="timeline-desc">{desc}</p>}
        {timestamp && (
          <time className="timeline-meta">
            {new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {new Date(timestamp).toLocaleDateString()}
          </time>
        )}
      </div>
    </div>
  );
}

/* ── Policy Summary ───────────────────────────────────────────── */
function PolicyCard({ policy }) {
  const rows = policy
    ? [
        { label: 'Min Margin',    value: `${policy.minimum_margin_percent}%`,                   color: 'var(--success)' },
        { label: 'Max Discount',  value: `${policy.maximum_discount_percent}%`,                  color: 'var(--warning)' },
        { label: 'Max Rounds',    value: `${policy.maximum_negotiation_rounds}`,                  color: 'var(--text-primary)' },
        { label: 'Auto Approval', value: `₹${Number(policy.auto_approval_limit).toLocaleString()}`, color: 'var(--indigo)' },
      ]
    : [];

  return (
    <div className="card card-sm">
      <div className="card-header" style={{ marginBottom: 14 }}>
        <span className="card-title"><ShieldCheck size={15} color="var(--indigo)" />Economic Constitution</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {rows.map((row) => (
          <div key={row.label} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '10px 0', borderBottom: '1px solid var(--border-subtle)',
          }}>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{row.label}</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: row.color }}>{row.value}</span>
          </div>
        ))}
        {!policy && <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>No policy configured</span>}
      </div>

      <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
        <div className="section-label" style={{ marginBottom: 12, textAlign: 'center' }}>Autonomous Commerce Flow</div>
        <FlowStepper />
      </div>
    </div>
  );
}

/* ── Main Page ────────────────────────────────────────────────── */
export default function OverviewPage({ merchant, policy, products = [], negotiations = [], transactions = [], onNavigate }) {
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  const activeNegs   = negotiations.filter(n => n.status === 'ACTIVE' || n.status === 'BUYER_TURN' || n.status === 'MERCHANT_TURN');
  const agreedNegs   = negotiations.filter(n => n.status === 'AGREED');
  const pendingTxns  = transactions.filter(t => t.status === 'ORDER_CREATED' || t.status === 'PAYMENT_PENDING');
  const capturedTxns = transactions.filter(t => t.status === 'PAYMENT_CAPTURED');
  const lowStock     = products.filter(p => p.inventory_quantity > 0 && p.inventory_quantity <= 5);
  const outOfStock   = products.filter(p => p.inventory_quantity === 0);

  // Activity feed from real backend events only
  const events = [];
  negotiations.forEach((neg) => {
    events.push({
      id: `neg-${neg.id}`, timestamp: neg.created_at,
      title: 'Negotiation initialized',
      desc: `${neg.product_name || 'Product'} · Buyer: ${neg.buyer_profile?.name || 'AI Buyer'}`,
      status: neg.status, icon: Bot, color: 'var(--indigo)', bgColor: 'var(--indigo-dim)',
    });
    if (neg.agreed_price) {
      events.push({
        id: `agree-${neg.id}`, timestamp: neg.updated_at || neg.created_at,
        title: 'Agreement reached',
        desc: `Settled at ₹${neg.agreed_price} · payment_ready = true`,
        status: 'AGREED', icon: ShieldCheck, color: 'var(--success)', bgColor: 'var(--success-dim)',
      });
    }
  });
  transactions.forEach((txn) => {
    const rupees = txn.agreed_amount || ((txn.amount_minor_units || 0) / 100).toFixed(2);
    events.push({
      id: `txn-${txn.id}`, timestamp: txn.created_at,
      title: 'Razorpay order created',
      desc: `₹${rupees} · ${txn.razorpay_order_id || ''}`,
      status: txn.status, icon: CreditCard, color: 'var(--info)', bgColor: 'var(--info-dim)',
    });
    if (txn.payment_verified || txn.status === 'PAYMENT_CAPTURED') {
      events.push({
        id: `cap-${txn.id}`, timestamp: txn.updated_at || txn.created_at,
        title: 'Payment captured & verified',
        desc: `₹${rupees} · Inventory decremented`,
        status: 'PAYMENT_CAPTURED', icon: TrendingUp, color: 'var(--success)', bgColor: 'var(--success-dim)',
      });
    }
  });
  events.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }} className="fade-up">
      {/* Greeting */}
      <div>
        <div style={{ fontSize: 13, color: 'var(--text-tertiary)', marginBottom: 4, fontWeight: 500 }}>{greeting}</div>
        <h1 style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.6px', color: 'var(--text-primary)', marginBottom: 6 }}>
          Merchant Command Center
        </h1>
        <p style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          Your autonomous commerce system is operating within policy.{merchant && ` — ${merchant.business_name}`}
        </p>
      </div>

      {/* KPIs */}
      <div className="grid-4">
        <div className="kpi-card card-hover" onClick={() => onNavigate('negotiations')} style={{ cursor: 'pointer' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <Bot size={14} color="var(--indigo)" />
            <div className="kpi-label">Active Negotiations</div>
          </div>
          <div className="kpi-value">{activeNegs.length}</div>
          <div className="kpi-sub">{agreedNegs.length} agreed · pending payment</div>
        </div>
        <div className="kpi-card card-hover" onClick={() => onNavigate('transactions')} style={{ cursor: 'pointer' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <CreditCard size={14} color="var(--info)" />
            <div className="kpi-label">Payment Pipeline</div>
          </div>
          <div className="kpi-value">{pendingTxns.length}</div>
          <div className="kpi-sub">{capturedTxns.length} captured successfully</div>
        </div>
        <div className="kpi-card card-hover" onClick={() => onNavigate('products')} style={{ cursor: 'pointer' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <Package size={14} color="var(--success)" />
            <div className="kpi-label">Catalog Size</div>
          </div>
          <div className="kpi-value">{products.length}</div>
          <div className="kpi-sub">{lowStock.length} low · {outOfStock.length} out of stock</div>
        </div>
        <div className="kpi-card card-hover" onClick={() => onNavigate('constitution')} style={{ cursor: 'pointer' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
            <ShieldCheck size={14} color={outOfStock.length > 0 ? 'var(--danger)' : 'var(--success)'} />
            <div className="kpi-label">Inventory Risk</div>
          </div>
          <div className="kpi-value" style={{ color: outOfStock.length > 0 ? 'var(--danger)' : 'var(--success)' }}>
            {outOfStock.length}
          </div>
          <div className="kpi-sub">{outOfStock.length > 0 ? 'items out of stock' : 'All inventory healthy'}</div>
        </div>
      </div>

      {/* Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 22 }}>
        {/* AI Decision Feed */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', maxHeight: 520 }}>
          <div className="card-header">
            <span className="card-title"><Clock size={15} className="card-title-icon" />AI Decision Feed</span>
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Real-time autonomous commerce decisions</span>
          </div>
          <div className="timeline scroll-y" style={{ flex: 1, paddingRight: 4 }}>
            {events.length > 0
              ? events.slice(0, 15).map((ev) => <ActivityItem key={ev.id} {...ev} />)
              : (
                <EmptyState
                  icon={Clock}
                  title="No AI activity yet"
                  description="Run an intent analysis or start an autonomous negotiation to generate live events."
                />
              )}
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <PolicyCard policy={policy} />

          <div className="card card-sm">
            <div className="card-header" style={{ marginBottom: 12 }}>
              <span className="card-title"><Zap size={15} color="var(--indigo)" />Quick Actions</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button className="btn btn-primary" style={{ justifyContent: 'flex-start', gap: 8 }} onClick={() => onNavigate('revenue-engine')}>
                <Zap size={14} /> Run Revenue Analysis
              </button>
              <button className="btn btn-secondary" style={{ justifyContent: 'flex-start', gap: 8 }} onClick={() => onNavigate('negotiations')}>
                <Bot size={14} /> Start AI Negotiation
              </button>
              <button className="btn btn-secondary" style={{ justifyContent: 'flex-start', gap: 8 }} onClick={() => onNavigate('transactions')}>
                <CreditCard size={14} /> View Transactions
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
