import React from 'react';
import {
  LayoutDashboard, Zap, Bot, Package, CreditCard,
  History, ScrollText, Shield, Circle,
} from 'lucide-react';

const NAV = [
  {
    group: 'Command Center',
    items: [{ id: 'overview', label: 'Overview', icon: LayoutDashboard }],
  },
  {
    group: 'Revenue Intelligence',
    items: [{ id: 'revenue-engine', label: 'AI Revenue Engine', icon: Zap }],
  },
  {
    group: 'Autonomous Commerce',
    items: [{ id: 'negotiations', label: 'AI Negotiations', icon: Bot }],
  },
  {
    group: 'Operations',
    items: [
      { id: 'products',     label: 'Products',      icon: Package },
      { id: 'transactions', label: 'Transactions',   icon: CreditCard },
    ],
  },
  {
    group: 'Governance',
    items: [
      { id: 'constitution', label: 'Economic Constitution', icon: ScrollText },
      { id: 'audit',        label: 'Activity / Audit',      icon: History },
    ],
  },
];

export default function Sidebar({ activeTab, setActiveTab, pendingCount = 0 }) {
  return (
    <aside style={{
      width: 'var(--sidebar-w)',
      flexShrink: 0,
      background: '#fff',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      overflow: 'hidden',
    }}>
      {/* Brand */}
      <div style={{
        padding: '20px 18px 18px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 34, height: 34,
            borderRadius: 9,
            background: 'var(--indigo)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 1px 3px rgba(67,97,238,0.3)',
          }}>
            <Shield size={16} color="#fff" />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, letterSpacing: '-0.3px', color: 'var(--text-primary)' }}>
              MERCHANT OS
            </div>
            <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.06em', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
              AI Commerce
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: '14px 10px', display: 'flex', flexDirection: 'column', gap: 2 }}
           className="scroll-y">
        {NAV.map((group) => (
          <div key={group.group} style={{ marginBottom: 6 }}>
            <div style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
              textTransform: 'uppercase', color: 'var(--text-tertiary)',
              padding: '10px 10px 5px',
            }}>
              {group.group}
            </div>
            {group.items.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              const count = item.id === 'transactions' ? pendingCount : 0;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                    padding: '8px 11px',
                    borderRadius: 8,
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: 'var(--font)',
                    fontSize: 13,
                    fontWeight: isActive ? 600 : 500,
                    color: isActive ? 'var(--indigo)' : 'var(--text-secondary)',
                    background: isActive ? 'var(--indigo-dim)' : 'transparent',
                    transition: 'all 0.12s ease',
                    textAlign: 'left',
                    marginBottom: 1,
                  }}
                  onMouseEnter={(e) => { if (!isActive) { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--text-primary)'; } }}
                  onMouseLeave={(e) => { if (!isActive) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)'; } }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                    <Icon size={16} color={isActive ? 'var(--indigo)' : 'var(--text-tertiary)'} strokeWidth={isActive ? 2.2 : 1.8} />
                    {item.label}
                  </div>
                  {count > 0 && (
                    <span style={{
                      background: 'var(--indigo)', color: '#fff',
                      borderRadius: 99, fontSize: 10, fontWeight: 700,
                      padding: '1px 6px', minWidth: 18, textAlign: 'center',
                    }}>{count}</span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Status Footer */}
      <div style={{
        padding: '14px 18px',
        borderTop: '1px solid var(--border)',
        flexShrink: 0,
        background: 'var(--bg-card-alt)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
          <Circle size={7} color="var(--success)" fill="var(--success)" className="pulse" />
          <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)' }}>AI Core Online</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <Circle size={7} color="var(--indigo)" fill="var(--indigo)" />
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Razorpay Test Mode</span>
        </div>
      </div>
    </aside>
  );
}
