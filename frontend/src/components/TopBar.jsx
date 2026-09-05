import React from 'react';
import { Circle } from 'lucide-react';

export default function TopBar({ merchants = [], selectedMerchantId, onSelectMerchant, pageTitle, pageSubtitle, backendConnected, onSwitchToBuyer }) {
  return (
    <header style={{
      height: 'var(--topbar-h)',
      background: '#fff',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 32px',
      flexShrink: 0,
      position: 'sticky',
      top: 0,
      zIndex: 200,
    }}>
      {/* Left: Page context */}
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
          {pageTitle}
        </div>
        {pageSubtitle && (
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 1 }}>
            {pageSubtitle}
          </div>
        )}
      </div>

      {/* Right: Merchant selector + status pills + Buyer Portal switch */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* Switch to Buyer Portal button */}
        <button
          className="btn btn-primary"
          onClick={onSwitchToBuyer}
          style={{
            fontSize: 12,
            fontWeight: 700,
            padding: '6px 13px',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            borderRadius: 'var(--r-md)',
            boxShadow: '0 2px 8px rgba(67,97,238,0.2)'
          }}
        >
          <span>🛍️ Open Buyer AI Portal</span>
        </button>

        {/* Merchant Selector */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: '#fff', border: '1px solid var(--border)',
          borderRadius: 'var(--r-md)', padding: '6px 12px',
          boxShadow: 'var(--shadow-xs)',
        }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Merchant
          </span>
          <div style={{ width: 1, height: 16, background: 'var(--border)' }} />
          <select
            value={selectedMerchantId ?? ''}
            onChange={(e) => onSelectMerchant(Number(e.target.value))}
            style={{
              background: 'transparent', border: 'none', color: 'var(--text-primary)',
              fontSize: 13, fontWeight: 600, fontFamily: 'var(--font)',
              cursor: 'pointer', outline: 'none', letterSpacing: '-0.2px',
              paddingRight: 4,
            }}
          >
            {merchants.map((m) => (
              <option key={m.id} value={m.id}>{m.business_name}</option>
            ))}
          </select>
        </div>

        {/* Razorpay Test Mode pill */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          background: 'var(--indigo-dim)', border: '1px solid rgba(67,97,238,0.12)',
          borderRadius: 'var(--r-pill)', padding: '4px 11px',
          fontSize: 11, fontWeight: 600, color: 'var(--indigo)',
        }}>
          <Circle size={5} color="var(--indigo)" fill="var(--indigo)" />
          Test Mode
        </div>

        {/* AI Core status */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          background: backendConnected ? 'var(--success-dim)' : 'var(--danger-dim)',
          border: backendConnected ? '1px solid rgba(5,150,105,0.12)' : '1px solid rgba(220,38,38,0.12)',
          borderRadius: 'var(--r-pill)', padding: '4px 11px',
          fontSize: 11, fontWeight: 600,
          color: backendConnected ? 'var(--success)' : 'var(--danger)',
        }}>
          <Circle size={5} color={backendConnected ? 'var(--success)' : 'var(--danger)'} fill={backendConnected ? 'var(--success)' : 'var(--danger)'} className={backendConnected ? 'pulse' : ''} />
          {backendConnected ? 'AI Online' : 'Offline'}
        </div>
      </div>
    </header>
  );
}
