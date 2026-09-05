import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  History, RefreshCw, Search, Bot, CreditCard, Shield, User,
  CheckCircle2, ArrowRight, Activity, Filter, Download
} from 'lucide-react';
import { aiApi } from '../api/ai';
import { paymentsApi } from '../api/payments';
import StatusBadge from '../components/StatusBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';
import EmptyState from '../components/EmptyState';

const ACTOR_STYLES = {
  'Buyer AI': {
    color: '#0284C7',
    bg: '#E0F2FE',
    border: 'rgba(2,132,199,0.2)',
    icon: User,
  },
  'Merchant AI': {
    color: '#4F46E5',
    bg: '#EEF2FF',
    border: 'rgba(79,70,229,0.2)',
    icon: Bot,
  },
  'Economic System': {
    color: '#D97706',
    bg: '#FEF3C7',
    border: 'rgba(217,119,6,0.2)',
    icon: Shield,
  },
  'Payment System': {
    color: '#059669',
    bg: '#D1FAE5',
    border: 'rgba(5,150,105,0.2)',
    icon: CreditCard,
  },
};

export default function AuditPage({ merchantId }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQ, setSearchQ] = useState('');
  const [actorFilter, setActorFilter] = useState('ALL');

  const fetchAuditData = useCallback(async () => {
    if (!merchantId) return;
    setLoading(true);
    setError(null);
    try {
      const [negsRes, txnsRes] = await Promise.allSettled([
        aiApi.listNegotiations(merchantId),
        paymentsApi.listTransactions(merchantId),
      ]);

      const negList = negsRes.status === 'fulfilled'
        ? (Array.isArray(negsRes.value) ? negsRes.value : negsRes.value?.results || [])
        : [];
      const txnList = txnsRes.status === 'fulfilled'
        ? (Array.isArray(txnsRes.value) ? txnsRes.value : txnsRes.value?.results || [])
        : [];

      const parsedEvents = [];

      // 1. Parse negotiations and their inner events
      negList.forEach(neg => {
        const productName = neg.product_name || `Item #${neg.product_id || ''}`;
        const negId = neg.id;

        // Session creation event (Economic System)
        parsedEvents.push({
          id: `econ-init-${negId}`,
          timestamp: neg.created_at,
          actor: 'Economic System',
          event: `Negotiation Policy Bound · Session #${negId}`,
          action: 'POLICY_INIT',
          amount: null,
          status: 'ACTIVE',
          product: productName,
        });

        // Inner round events
        const innerEvents = Array.isArray(neg.events) ? neg.events : [];
        if (innerEvents.length > 0) {
          innerEvents.forEach((ev, idx) => {
            const isBuyer = ev.actor === 'BUYER' || ev.actor === 'BUYER_AI' || (ev.message && ev.message.toLowerCase().includes('buyer'));
            const isSystem = ev.actor === 'SYSTEM';
            const actorName = isBuyer ? 'Buyer AI' : isSystem ? 'Economic System' : 'Merchant AI';
            const offerPrice = ev.proposed_price || ev.offer_price || ev.price || null;

            parsedEvents.push({
              id: `ev-${negId}-${idx}`,
              timestamp: ev.created_at || neg.updated_at || neg.created_at,
              actor: actorName,
              event: ev.event_type || (isBuyer ? `Buyer Offer (Round ${ev.round_number || idx + 1})` : `Merchant Response (Round ${ev.round_number || idx + 1})`),
              action: ev.action || (isBuyer ? 'PROPOSE_PRICE' : ev.decision || 'COUNTER'),
              amount: offerPrice ? Number(offerPrice) : null,
              status: ev.status || neg.status,
              product: productName,
            });
          });
        } else {
          // If no granular events list, create synthetic representation from negotiation summary
          if (neg.status === 'AGREED' && neg.agreed_price) {
            parsedEvents.push({
              id: `neg-agree-${negId}`,
              timestamp: neg.updated_at || neg.created_at,
              actor: 'Merchant AI',
              event: `Commercial Agreement Reached · ${productName}`,
              action: 'AGREE',
              amount: Number(neg.agreed_price),
              status: 'AGREED',
              product: productName,
            });
          } else if (neg.status === 'REJECTED') {
            parsedEvents.push({
              id: `neg-reject-${negId}`,
              timestamp: neg.updated_at || neg.created_at,
              actor: 'Economic System',
              event: `Negotiation Terminated · Margin Boundary Protected`,
              action: 'REJECT',
              amount: null,
              status: 'REJECTED',
              product: productName,
            });
          }
        }
      });

      // 2. Parse transactions (Payment System)
      txnList.forEach(txn => {
        const amt = txn.agreed_amount || (txn.amount_minor_units ? txn.amount_minor_units / 100 : null);
        const orderId = txn.razorpay_order_id || `TXN-${txn.id}`;

        parsedEvents.push({
          id: `txn-order-${txn.id}`,
          timestamp: txn.created_at,
          actor: 'Payment System',
          event: `Razorpay Order Created · ${orderId}`,
          action: 'ORDER_CREATED',
          amount: amt ? Number(amt) : null,
          status: txn.status || 'PAYMENT_PENDING',
          product: txn.product_name || 'Agreed Order',
        });

        if (txn.status === 'PAYMENT_CAPTURED' || txn.status === 'CAPTURED') {
          parsedEvents.push({
            id: `txn-captured-${txn.id}`,
            timestamp: txn.updated_at || txn.created_at,
            actor: 'Payment System',
            event: `Payment Captured & Verified · ${txn.razorpay_payment_id || orderId}`,
            action: 'CAPTURE_VERIFIED',
            amount: amt ? Number(amt) : null,
            status: 'PAYMENT_CAPTURED',
            product: txn.product_name || 'Agreed Order',
          });
        }
      });

      // Sort newest first
      parsedEvents.sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));
      setEvents(parsedEvents);
    } catch (err) {
      setError(err.message || 'Failed to assemble activity log.');
    } finally {
      setLoading(false);
    }
  }, [merchantId]);

  useEffect(() => {
    fetchAuditData();
  }, [fetchAuditData]);

  // Filters
  const filteredEvents = useMemo(() => {
    return events.filter(e => {
      if (actorFilter !== 'ALL' && e.actor !== actorFilter) return false;
      if (searchQ) {
        const q = searchQ.toLowerCase();
        const mEvent = (e.event || '').toLowerCase().includes(q);
        const mAction = (e.action || '').toLowerCase().includes(q);
        const mProduct = (e.product || '').toLowerCase().includes(q);
        const mActor = (e.actor || '').toLowerCase().includes(q);
        if (!mEvent && !mAction && !mProduct && !mActor) return false;
      }
      return true;
    });
  }, [events, actorFilter, searchQ]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }} className="fade-up">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.4px', margin: 0 }}>
            Activity & Audit Log
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4, margin: 0 }}>
            Immutable chronological audit trace of all AI buyer, merchant, constitution, and Razorpay payment events
          </p>
        </div>
        <button className="btn btn-secondary" onClick={fetchAuditData} style={{ padding: '8px 14px' }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="card" style={{ padding: '14px 18px', display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: '1 1 240px' }}>
          <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
          <input
            className="input"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            placeholder="Search audit timeline by event, action, or product…"
            style={{ paddingLeft: 34, height: 38 }}
          />
        </div>

        {/* Actor Filter Tabs */}
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg-root)', padding: 3, borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
          {[
            { key: 'ALL', label: 'All' },
            { key: 'Buyer AI', label: 'Buyer AI' },
            { key: 'Merchant AI', label: 'Merchant AI' },
            { key: 'Economic System', label: 'Economic System' },
            { key: 'Payment System', label: 'Payment System' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActorFilter(tab.key)}
              style={{
                background: actorFilter === tab.key ? '#fff' : 'transparent',
                color: actorFilter === tab.key ? 'var(--text-primary)' : 'var(--text-tertiary)',
                fontWeight: actorFilter === tab.key ? 700 : 500,
                fontSize: 12,
                padding: '6px 12px',
                borderRadius: 'var(--r-sm)',
                border: 'none',
                cursor: 'pointer',
                boxShadow: actorFilter === tab.key ? 'var(--shadow-xs)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {loading && <LoadingSpinner text="Compiling verified event audit log…" />}

      {/* Audit Timeline Table */}
      {!loading && filteredEvents.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '16%' }}>Timestamp</th>
                <th style={{ width: '18%' }}>Actor</th>
                <th style={{ width: '30%' }}>Event</th>
                <th style={{ width: '14%' }}>Action</th>
                <th style={{ width: '12%', textAlign: 'right' }}>Amount</th>
                <th style={{ width: '10%' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.map((item) => {
                const actorStyle = ACTOR_STYLES[item.actor] || ACTOR_STYLES['Economic System'];
                const ActorIcon = actorStyle.icon;

                const formattedTime = item.timestamp
                  ? new Date(item.timestamp).toLocaleString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })
                  : '—';

                return (
                  <tr key={item.id}>
                    {/* Timestamp */}
                    <td>
                      <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                        {formattedTime}
                      </span>
                    </td>

                    {/* Actor */}
                    <td>
                      <span style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: actorStyle.color,
                        background: actorStyle.bg,
                        border: `1px solid ${actorStyle.border}`,
                        padding: '3px 9px',
                        borderRadius: 'var(--r-pill)',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 5,
                      }}>
                        <ActorIcon size={12} />
                        {item.actor}
                      </span>
                    </td>

                    {/* Event */}
                    <td>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                        {item.event}
                      </div>
                      {item.product && (
                        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
                          {item.product}
                        </div>
                      )}
                    </td>

                    {/* Action */}
                    <td>
                      <span style={{
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 600,
                        color: 'var(--text-secondary)',
                        background: 'var(--bg-root)',
                        border: '1px solid var(--border)',
                        padding: '2px 8px',
                        borderRadius: 'var(--r-sm)',
                        display: 'inline-block',
                      }}>
                        {item.action}
                      </span>
                    </td>

                    {/* Amount */}
                    <td style={{ textAlign: 'right' }}>
                      {item.amount != null ? (
                        <span style={{ fontSize: 13, fontWeight: 800, color: 'var(--text-primary)' }}>
                          ₹{Number(item.amount).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                        </span>
                      ) : (
                        <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>—</span>
                      )}
                    </td>

                    {/* Status */}
                    <td>
                      <StatusBadge status={item.status} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : !loading && (
        <EmptyState
          icon={History}
          title="No audit events found"
          description={events.length === 0
            ? "Audit records are generated as autonomous agents evaluate intents, execute negotiations, and process payments."
            : "No events match the selected filters. Try switching the actor filter to 'All'."}
        />
      )}
    </div>
  );
}
