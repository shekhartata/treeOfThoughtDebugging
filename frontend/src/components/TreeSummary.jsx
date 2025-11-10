import React from 'react';
import '../styles/TreeSummary.css';

function TreeSummary({ summary }) {
  if (!summary) return null;

  return (
    <div className="tree-summary">
      <div className="summary-card">
        <div className="summary-value">{summary.total_nodes || 0}</div>
        <div className="summary-label">Total Nodes</div>
      </div>
      <div className="summary-card">
        <div className="summary-value">{summary.active_branches || 0}</div>
        <div className="summary-label">Active Branches</div>
      </div>
      <div className="summary-card">
        <div className="summary-value">{summary.pruned_branches || 0}</div>
        <div className="summary-label">Pruned Branches</div>
      </div>
      <div className="summary-card">
        <div className="summary-value">{summary.accepted_branches || 0}</div>
        <div className="summary-label">Accepted Branches</div>
      </div>
    </div>
  );
}

export default TreeSummary;

