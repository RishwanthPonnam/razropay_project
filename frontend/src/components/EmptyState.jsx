import React from 'react';
import { Inbox } from 'lucide-react';

export default function EmptyState({ icon: Icon = Inbox, title = 'No data available', description, action }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <Icon size={20} />
      </div>
      <p className="empty-state-title">{title}</p>
      {description && <p className="empty-state-desc">{description}</p>}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  );
}
