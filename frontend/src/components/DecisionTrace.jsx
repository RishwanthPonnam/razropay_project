import React, { useState } from 'react';
import { Cpu, ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';

export default function DecisionTrace({ trace = [], confidence, policyCompliant }) {
  const [open, setOpen] = useState(true);
  if (!trace?.length) return null;

  return (
    <div className="trace-container" style={{ marginTop: 16 }}>
      <div className="trace-header" onClick={() => setOpen(!open)}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Cpu size={14} color="var(--indigo)" />
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
            AI Decision Trace
          </span>
          <span style={{
            fontSize: 10, fontWeight: 700, padding: '2px 8px',
            borderRadius: 'var(--r-pill)',
            background: 'var(--indigo-dim)', color: 'var(--indigo)',
            border: '1px solid rgba(67,97,238,0.12)',
          }}>
            {trace.length} steps
          </span>
          {confidence !== undefined && (
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '2px 8px',
              borderRadius: 'var(--r-pill)',
              background: 'var(--success-dim)', color: 'var(--success)',
              border: '1px solid rgba(5,150,105,0.12)',
            }}>
              {(confidence * 100).toFixed(0)}% confidence
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {policyCompliant !== undefined && (
            <span style={{ fontSize: 11, color: policyCompliant ? 'var(--success)' : 'var(--warning)', display: 'flex', alignItems: 'center', gap: 4, fontWeight: 600 }}>
              <ShieldCheck size={13} />
              {policyCompliant ? 'Policy Compliant' : 'Policy Warning'}
            </span>
          )}
          {open ? <ChevronDown size={15} color="var(--text-tertiary)" /> : <ChevronRight size={15} color="var(--text-tertiary)" />}
        </div>
      </div>

      {open && (
        <div className="trace-body">
          {trace.map((step, idx) => {
            const text = typeof step === 'string' ? step : JSON.stringify(step);
            return (
              <div key={idx} className="trace-step">
                <span className="trace-num">{idx + 1}</span>
                <span className="trace-text">{text}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
