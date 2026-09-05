import React from 'react';

/**
 * Maps backend status strings to CSS class + display label.
 * Centralised here to guarantee consistency across all pages.
 */
const STATUS_MAP = {
  // Negotiations
  ACTIVE:          { cls: 's-active',      label: 'In Progress' },
  BUYER_TURN:      { cls: 's-active',      label: 'In Progress' },
  MERCHANT_TURN:   { cls: 's-active',      label: 'In Progress' },
  NEGOTIATING:     { cls: 's-active',      label: 'In Progress' },
  AGREED:          { cls: 's-agreed',      label: 'Agreement Reached' },
  ACCEPTED:        { cls: 's-agreed',      label: 'Agreement Reached' },
  REJECTED:        { cls: 's-rejected',    label: 'Negotiation Rejected' },
  TERMINATED:      { cls: 's-rejected',    label: 'Negotiation Rejected' },
  EXPIRED:         { cls: 's-expired',     label: 'Negotiation Expired' },

  // Transactions / Payment
  CREATED:         { cls: 's-pending',     label: 'Created' },
  ORDER_CREATED:   { cls: 's-payment',     label: 'Order Created' },
  PAYMENT_PENDING: { cls: 's-payment',     label: 'Payment Pending' },
  PAYMENT_CAPTURED:{ cls: 's-captured',    label: 'Captured' },
  PAYMENT_FAILED:  { cls: 's-failed',      label: 'Payment Failed' },
  CAPTURED:        { cls: 's-captured',    label: 'Captured' },
  FAILED:          { cls: 's-failed',      label: 'Failed' },

  // Generic
  PENDING:         { cls: 's-pending',     label: 'Pending' },
  SUCCESS:         { cls: 's-agreed',      label: 'Success' },
  true:            { cls: 's-active',      label: 'Active' },
  false:           { cls: 's-rejected',    label: 'Inactive' },
};

export function mapStatus(status) {
  if (!status && status !== false) return null;
  const key = String(status).toUpperCase();
  return STATUS_MAP[key] || { cls: 's-pending', label: String(status) };
}

export default function StatusBadge({ status }) {
  if (status == null) return null;
  const { cls, label } = mapStatus(status) || { cls: 's-pending', label: String(status) };
  return (
    <span className={`badge ${cls}`}>
      <span className="badge-dot" />
      {label}
    </span>
  );
}
