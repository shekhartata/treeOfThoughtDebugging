import React from 'react';
import { focusBranch, pruneBranch, unpruneBranch } from '../services/api';
import '../styles/HypothesisCard.css';

function HypothesisCard({ hypothesis, hypothesisNumber, onStateUpdate, onRefresh, sessionId }) {
  const confidence = hypothesis.confidence || 0;
  const confidenceClass = confidence >= 0.7 ? 'confidence-high' : 
                          confidence >= 0.4 ? 'confidence-medium' : 'confidence-low';
  const status = hypothesis.status || 'active';

  const handleFocus = async () => {
    try {
      const data = await focusBranch(hypothesis.id, sessionId);
      if (onStateUpdate) onStateUpdate(data);
      if (onRefresh) onRefresh();
    } catch (error) {
      alert('Error focusing branch: ' + (error.response?.data?.error || error.message));
    }
  };

  const handlePrune = async () => {
    if (!confirm(`Are you sure you want to prune this hypothesis?`)) return;
    try {
      const data = await pruneBranch(hypothesis.id, sessionId);
      if (onStateUpdate) onStateUpdate(data);
      if (onRefresh) onRefresh();
    } catch (error) {
      alert('Error pruning branch: ' + (error.response?.data?.error || error.message));
    }
  };

  const handleUnprune = async () => {
    try {
      const data = await unpruneBranch(hypothesis.id, sessionId);
      if (onStateUpdate) onStateUpdate(data);
      if (onRefresh) onRefresh();
    } catch (error) {
      alert('Error restoring branch: ' + (error.response?.data?.error || error.message));
    }
  };

  return (
    <div className={`hypothesis-card ${status}`}>
      <div className="hypothesis-header">
        <div className="hypothesis-title">
          <span className="hypothesis-number" style={{ 
            fontWeight: 'bold', 
            color: '#667eea', 
            marginRight: '8px',
            fontSize: '14px'
          }}>
            Hypothesis {hypothesisNumber}:
          </span>
          {hypothesis.description}
        </div>
        <div>
          <span className={`confidence-badge ${confidenceClass}`}>
            {(confidence * 100).toFixed(0)}%
          </span>
          <span 
            className="status-badge" 
            style={{
              background: status === 'active' ? '#4caf50' : 
                         status === 'accepted' ? '#2196f3' : '#f44336',
              color: 'white',
              marginLeft: '5px',
              padding: '2px 8px',
              borderRadius: '4px',
              fontSize: '12px'
            }}
          >
            {status}
          </span>
        </div>
      </div>
      <div style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>
        Category: {hypothesis.category}
      </div>
      {hypothesis.evidence && hypothesis.evidence.length > 0 && (
        <ul className="evidence-list">
          {hypothesis.evidence.slice(0, 3).map((e, idx) => (
            <li key={idx}>{e}</li>
          ))}
        </ul>
      )}
      <div style={{ marginTop: '10px', display: 'flex', gap: '5px' }}>
        {status === 'active' && (
          <>
            <button className="button button-secondary" onClick={handleFocus} style={{ fontSize: '11px', padding: '4px 8px' }}>
              Focus Branch
            </button>
            <button className="button button-danger" onClick={handlePrune} style={{ fontSize: '11px', padding: '4px 8px' }}>
              Prune
            </button>
          </>
        )}
        {status === 'pruned' && (
          <button className="button button-success" onClick={handleUnprune} style={{ fontSize: '11px', padding: '4px 8px' }}>
            Restore
          </button>
        )}
      </div>
    </div>
  );
}

export default HypothesisCard;

