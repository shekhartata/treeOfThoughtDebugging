import React, { useState, useEffect } from 'react';
import './App.css';
import InitializeForm from './components/InitializeForm';
import CurrentState from './components/CurrentState';
import TreeView from './components/TreeView';
import { getCurrentNode } from './services/api';

function App() {
  const [isInitialized, setIsInitialized] = useState(false);
  const [currentState, setCurrentState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isInitialized) {
      loadCurrentState();
    }
  }, [isInitialized]);

  const loadCurrentState = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getCurrentNode();
      setCurrentState(data);
    } catch (err) {
      setError(err.message || 'Failed to load current state');
    } finally {
      setLoading(false);
    }
  };

  const handleInitialized = (data) => {
    setIsInitialized(true);
    setCurrentState(data);
  };

  const handleStateUpdate = (data) => {
    setCurrentState(data);
  };

  if (!isInitialized) {
    return (
      <div className="app-container">
        <div className="container">
          <div className="header">
            <h1>🌳 MongoDB Tree-of-Thought Debugging Tool</h1>
            <p>Interactive reasoning engine for diagnosing MongoDB issues</p>
          </div>
          <div className="content">
            <InitializeForm onInitialized={handleInitialized} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <div className="container">
        <div className="header">
          <h1>🌳 MongoDB Tree-of-Thought Debugging Tool</h1>
          <p>Interactive reasoning engine for diagnosing MongoDB issues</p>
        </div>
        <div className="content">
          {error && (
            <div className="error-message">
              {error}
            </div>
          )}
          <CurrentState 
            currentState={currentState} 
            onStateUpdate={handleStateUpdate}
            onRefresh={loadCurrentState}
            loading={loading}
          />
        </div>
      </div>
    </div>
  );
}

export default App;

