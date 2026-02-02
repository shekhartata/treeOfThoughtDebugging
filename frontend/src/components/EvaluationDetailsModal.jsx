import React, { useState, useEffect } from 'react';
import { getNodeEvaluationDetails } from '../services/api';
import '../styles/EvaluationDetailsModal.css';

function EvaluationDetailsModal({ nodeId, sessionId, isOpen, onClose }) {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && nodeId) {
      loadDetails();
    }
  }, [isOpen, nodeId, sessionId]);

  const loadDetails = async () => {
    if (!sessionId) {
      setError('Session ID is required');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getNodeEvaluationDetails(nodeId, sessionId);
      setDetails(data);
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Failed to load evaluation details');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const formatConfidence = (val) => {
    if (val === null || val === undefined) return 'N/A';
    return `${(val * 100).toFixed(1)}%`;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content evaluation-details-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Evaluation & Pruning Details</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {loading && <div className="loading">Loading details...</div>}
          
          {error && (
            <div className="error-message">
              <strong>Error:</strong> {error}
            </div>
          )}

          {!loading && !error && details && (
            <>
              {details.evaluation_details && (
                <div className="details-section evaluation-section">
                  <h3>📊 Evaluation Details</h3>
                  
                  <div className="detail-row">
                    <span className="detail-label">Artifact Evaluated:</span>
                    <span className="detail-value">{details.evaluation_details.artifact_name || 'N/A'}</span>
                  </div>

                  <div className="detail-row">
                    <span className="detail-label">Evaluated At:</span>
                    <span className="detail-value">{formatDate(details.evaluation_details.evaluated_at)}</span>
                  </div>

                  <div className="confidence-change">
                    <div className="confidence-before">
                      <span className="label">Confidence Before:</span>
                      <span className="value">{formatConfidence(details.evaluation_details.confidence_before)}</span>
                    </div>
                    <div className="confidence-arrow">→</div>
                    <div className="confidence-after">
                      <span className="label">Confidence After:</span>
                      <span className="value">{formatConfidence(details.evaluation_details.confidence_after)}</span>
                    </div>
                    {details.evaluation_details.confidence_change !== undefined && (
                      <div className={`confidence-change-value ${details.evaluation_details.confidence_change >= 0 ? 'positive' : 'negative'}`}>
                        {details.evaluation_details.confidence_change >= 0 ? '+' : ''}
                        {formatConfidence(details.evaluation_details.confidence_change)}
                      </div>
                    )}
                  </div>

                  <div className="detail-row">
                    <span className="detail-label">Evaluation Status:</span>
                    <span className={`status-badge ${details.evaluation_details.status || 'neutral'}`}>
                      {details.evaluation_details.status || 'neutral'}
                    </span>
                  </div>

                  {details.evaluation_details.evidence_found && (
                    <div className="detail-block">
                      <span className="detail-label">Evidence Found:</span>
                      <div className="detail-text">{details.evaluation_details.evidence_found}</div>
                    </div>
                  )}

                  {details.evaluation_details.evidence_summary && (
                    <div className="detail-block">
                      <span className="detail-label">Evidence Summary:</span>
                      <div className="detail-text">{details.evaluation_details.evidence_summary}</div>
                    </div>
                  )}

                  {details.evaluation_details.llm_reasoning && (
                    <div className="detail-block">
                      <span className="detail-label">LLM Reasoning:</span>
                      <div className="detail-text llm-reasoning">{details.evaluation_details.llm_reasoning}</div>
                    </div>
                  )}
                </div>
              )}

              {details.pruning_details && (
                <div className="details-section pruning-section">
                  <h3>✂️ Pruning Details</h3>
                  
                  <div className="detail-row">
                    <span className="detail-label">Pruned At:</span>
                    <span className="detail-value">{formatDate(details.pruning_details.pruned_at)}</span>
                  </div>

                  <div className="detail-row">
                    <span className="detail-label">Confidence at Pruning:</span>
                    <span className="detail-value">{formatConfidence(details.pruning_details.confidence_at_pruning)}</span>
                  </div>

                  <div className="detail-row">
                    <span className="detail-label">Threshold Used:</span>
                    <span className="detail-value">
                      {details.pruning_details.threshold_used !== null && details.pruning_details.threshold_used !== undefined
                        ? formatConfidence(details.pruning_details.threshold_used)
                        : 'N/A'}
                    </span>
                  </div>

                  <div className="detail-row">
                    <span className="detail-label">Was Top Hypothesis:</span>
                    <span className="detail-value">{details.pruning_details.was_top_hypothesis ? 'Yes' : 'No'}</span>
                  </div>

                  {details.pruning_details.reason && (
                    <div className="detail-block">
                      <span className="detail-label">Pruning Reason:</span>
                      <div className="detail-text pruning-reason">{details.pruning_details.reason}</div>
                    </div>
                  )}
                </div>
              )}

              {!details.evaluation_details && !details.pruning_details && (
                <div className="no-details">
                  No evaluation or pruning details available for this node.
                </div>
              )}
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="button button-primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

export default EvaluationDetailsModal;

