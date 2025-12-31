import React, { useState, useEffect } from 'react';
import { detectLocalOllama } from '../services/api';
import '../styles/ModelSelector.css';

function ModelSelector({ onModelChange, selectedProvider, selectedModel }) {
  const [localModels, setLocalModels] = useState([]);
  const [localAvailable, setLocalAvailable] = useState(false);
  const [detecting, setDetecting] = useState(true);
  const [customBaseUrl, setCustomBaseUrl] = useState('http://localhost:11434');
  const [showCustomUrl, setShowCustomUrl] = useState(false);
  const [detectionError, setDetectionError] = useState(null);

  // Auto-detect Ollama on mount
  useEffect(() => {
    detectOllama();
  }, []);

  const detectOllama = async (baseUrl = 'http://localhost:11434') => {
    setDetecting(true);
    setDetectionError(null);
    try {
      const result = await detectLocalOllama(baseUrl);
      console.log('Ollama detection result:', result); // Debug log
      
      if (result.available && result.models && result.models.length > 0) {
        setLocalAvailable(true);
        setLocalModels(result.models);
        setCustomBaseUrl(result.base_url || baseUrl);
        setDetectionError(null);
      } else {
        setLocalAvailable(false);
        setLocalModels([]);
        // Show error message if available
        if (result.error) {
          setDetectionError(result.error);
          console.error('Ollama detection error:', result.error); // Debug log
        }
      }
    } catch (error) {
      console.error('Ollama detection exception:', error); // Debug log
      setLocalAvailable(false);
      setLocalModels([]);
      setDetectionError(error.message || 'Failed to detect Ollama instance');
    } finally {
      setDetecting(false);
    }
  };

  const handleProviderChange = (e) => {
    const provider = e.target.value;
    let defaultModel = '';
    
    // Set default model based on provider
    if (provider === 'groq') {
      defaultModel = 'openai/gpt-oss-120b';
    } else if (provider === 'openai') {
      defaultModel = 'gpt-5';
    } else if (provider === 'ollama' && localModels.length > 0) {
      defaultModel = localModels[0];
    }
    
    onModelChange({
      provider,
      model: defaultModel,
      baseUrl: provider === 'ollama' ? customBaseUrl : null
    });
  };

  const handleModelChange = (e) => {
    const model = e.target.value;
    onModelChange({
      provider: selectedProvider,
      model,
      baseUrl: selectedProvider === 'ollama' ? customBaseUrl : null
    });
  };

  const handleCustomUrlChange = (e) => {
    const newUrl = e.target.value;
    setCustomBaseUrl(newUrl);
    if (selectedProvider === 'ollama') {
      detectOllama(newUrl);
    }
  };

  const handleRetryDetection = () => {
    detectOllama(customBaseUrl);
  };

  return (
    <div className="model-selector">
      <div className="form-group">
        <label htmlFor="provider-select">LLM Provider:</label>
        <select
          id="provider-select"
          value={selectedProvider || ''}
          onChange={handleProviderChange}
          className="select-input"
        >
          <option value="">Select provider...</option>
          <option value="groq">Groq (Cloud - Fast)</option>
          <option value="openai">OpenAI (Cloud - GPT-5)</option>
          <option value="ollama" disabled={!localAvailable && !detecting}>
            Ollama (Local)
            {localAvailable && ' ⚡️ Detected'}
          </option>
        </select>
      </div>

      {selectedProvider === 'ollama' && (
        <div className="ollama-config">
          {detecting ? (
            <div className="detection-status">
              <span className="spinner"></span> Detecting local Ollama instance...
            </div>
          ) : localAvailable ? (
            <>
              <div className="local-gpu-badge">
                ⚡️ Local LLM(s) Detected
              </div>
              <div className="form-group">
                <label htmlFor="ollama-model-select">Local Model:</label>
                <select
                  id="ollama-model-select"
                  value={selectedModel || ''}
                  onChange={handleModelChange}
                  className="select-input"
                >
                  {localModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={showCustomUrl}
                    onChange={(e) => setShowCustomUrl(e.target.checked)}
                  />
                  Use custom URL/Port
                </label>
                {showCustomUrl && (
                  <input
                    type="text"
                    value={customBaseUrl}
                    onChange={handleCustomUrlChange}
                    placeholder="http://localhost:11434"
                    className="text-input"
                  />
                )}
              </div>
              <div className="performance-warning">
                ⚠️ Local inference is slower (~30-40 t/s) than cloud (~300 t/s)
              </div>
            </>
          ) : (
            <div className="no-local-detected">
              <p>No local Ollama instance detected.</p>
              {detectionError && (
                <div className="error-message">
                  <strong>Error:</strong> {detectionError}
                </div>
              )}
              <button
                type="button"
                onClick={handleRetryDetection}
                className="retry-button"
              >
                Retry Detection
              </button>
              {showCustomUrl && (
                <div className="form-group">
                  <label htmlFor="custom-url">Custom Ollama URL:</label>
                  <input
                    id="custom-url"
                    type="text"
                    value={customBaseUrl}
                    onChange={handleCustomUrlChange}
                    placeholder="http://localhost:11434"
                    className="text-input"
                  />
                  <button
                    type="button"
                    onClick={() => detectOllama(customBaseUrl)}
                    className="retry-button"
                  >
                    Test Connection
                  </button>
                </div>
              )}
              <label>
                <input
                  type="checkbox"
                  checked={showCustomUrl}
                  onChange={(e) => setShowCustomUrl(e.target.checked)}
                />
                Use custom URL/Port
              </label>
            </div>
          )}
        </div>
      )}

      {selectedProvider === 'groq' && (
        <div className="form-group">
          <label htmlFor="groq-model-select">Groq Model:</label>
          <select
            id="groq-model-select"
            value={selectedModel || 'openai/gpt-oss-120b'}
            onChange={handleModelChange}
            className="select-input"
          >
            <option value="openai/gpt-oss-120b">openai/gpt-oss-120b (Default)</option>
            <option value="llama-3.1-70b-versatile">llama-3.1-70b-versatile</option>
            <option value="mixtral-8x7b-32768">mixtral-8x7b-32768</option>
          </select>
        </div>
      )}

      {selectedProvider === 'openai' && (
        <div className="form-group">
          <label htmlFor="openai-model-select">OpenAI Model:</label>
          <select
            id="openai-model-select"
            value={selectedModel || 'gpt-5'}
            onChange={handleModelChange}
            className="select-input"
          >
            <option value="gpt-5">gpt-5 (Default)</option>
            <option value="gpt-4">gpt-4</option>
          </select>
        </div>
      )}
    </div>
  );
}

export default ModelSelector;

