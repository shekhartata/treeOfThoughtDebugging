import React, { useState } from 'react';
import { initializeEngine } from '../services/api';
import ModelSelector from './ModelSelector';
import '../styles/InitializeForm.css';

function InitializeForm({ onInitialized }) {
  const [problemSummary, setProblemSummary] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [useHardcodedFallback, setUseHardcodedFallback] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState(null);
  const [selectedModel, setSelectedModel] = useState(null);
  const [selectedBaseUrl, setSelectedBaseUrl] = useState(null);

  const handleModelChange = ({ provider, model, baseUrl }) => {
    setSelectedProvider(provider);
    setSelectedModel(model);
    setSelectedBaseUrl(baseUrl);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!problemSummary.trim()) {
      setError('Please provide a problem summary');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await initializeEngine(
        problemSummary,
        useHardcodedFallback,
        selectedProvider,
        selectedModel,
        selectedBaseUrl
      );
      onInitialized(data);
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Failed to initialize');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="section">
      <h2>1. Problem Summary</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="problem-summary">Describe the MongoDB issue:</label>
          <textarea
            id="problem-summary"
            value={problemSummary}
            onChange={(e) => setProblemSummary(e.target.value)}
            placeholder="e.g., Writes slow on primary after deploy. Users reporting timeouts."
            rows="5"
          />
        </div>
        
        <ModelSelector
          onModelChange={handleModelChange}
          selectedProvider={selectedProvider}
          selectedModel={selectedModel}
        />
        
        <div className="form-group">
          <label>
            <input
              type="checkbox"
              checked={useHardcodedFallback}
              onChange={(e) => setUseHardcodedFallback(e.target.checked)}
            />
            Use hardcoded fallback (for testing without LLM)
          </label>
        </div>
        {error && <div className="error-message">{error}</div>}
        <button type="submit" className="button" disabled={loading}>
          {loading ? 'Initializing...' : 'Initialize Debugging Session'}
        </button>
      </form>
    </div>
  );
}

export default InitializeForm;

