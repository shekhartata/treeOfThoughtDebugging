import React, { useState } from 'react';
import api from '../services/api';
import '../styles/FinalAnalysis.css';

function FinalAnalysis({ isComplete, onStateUpdate }) {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleGetAnalysis = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get('/final-analysis');
      const data = response.data;
      if (data.analysis) {
        setAnalysis(data.analysis);
        if (onStateUpdate) onStateUpdate(data);
      } else {
        setError(data.error || 'Failed to get final analysis');
      }
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Failed to get final analysis');
    } finally {
      setLoading(false);
    }
  };

  // Always show the component - no isComplete check

  return (
    <div className="final-analysis-section">
      <h3>🎯 Final Analysis</h3>
      {!analysis && (
        <button 
          className="button" 
          onClick={handleGetAnalysis} 
          disabled={loading}
        >
          {loading ? 'Generating Analysis...' : 'Get Final Analysis'}
        </button>
      )}
      
      {error && (
        <div className="error-message">{error}</div>
      )}
      
      {analysis && (
        <div className="final-analysis-content">
          <div className="analysis-section">
            <h4>Most Likely Root Cause:</h4>
            <p>{analysis.most_likely_root_cause || 'N/A'}</p>
          </div>
          
          {analysis.confidence && (
            <div className="analysis-section">
              <h4>Confidence:</h4>
              <p>{(analysis.confidence * 100).toFixed(0)}%</p>
            </div>
          )}
          
          {analysis.recommended_actions && analysis.recommended_actions.length > 0 && (
            <div className="analysis-section">
              <h4>Recommended Actions:</h4>
              <ul>
                {analysis.recommended_actions.map((action, idx) => (
                  <li key={idx}>{action}</li>
                ))}
              </ul>
            </div>
          )}
          
          {analysis.raw_llm_analysis && (
            <div className="analysis-section">
              <h4>LLM Analysis:</h4>
              <p style={{ whiteSpace: 'pre-wrap' }}>{analysis.raw_llm_analysis}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default FinalAnalysis;

