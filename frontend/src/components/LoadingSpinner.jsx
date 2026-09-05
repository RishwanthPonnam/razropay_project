import React from 'react';
import { Loader2 } from 'lucide-react';

export default function LoadingSpinner({ text = 'Processing…', size = 16 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '20px 0', color: 'var(--text-tertiary)', fontSize: 13 }}>
      <Loader2 size={size} className="spinner" color="var(--indigo)" />
      {text}
    </div>
  );
}
