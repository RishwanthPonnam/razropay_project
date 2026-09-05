import React from 'react';
import { AlertCircle, X } from 'lucide-react';

export default function ErrorBanner({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="alert alert-error" style={{ marginBottom: 16 }}>
      <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
      <span style={{ flex: 1 }}>{message}</span>
      {onDismiss && (
        <button onClick={onDismiss} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', padding: 0, display: 'flex', alignItems: 'center' }}>
          <X size={14} />
        </button>
      )}
    </div>
  );
}
