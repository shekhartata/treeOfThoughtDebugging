import React, { useState, useEffect } from 'react';
import './App.css';
import InitializeForm from './components/InitializeForm';
import CurrentState from './components/CurrentState';
import TreeView from './components/TreeView';
import SessionRecoveryDialog from './components/SessionRecoveryDialog';
import { getCurrentNode, checkSession, getHistory } from './services/api';

function App() {
  const [isInitialized, setIsInitialized] = useState(false);
  const [currentState, setCurrentState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [showRecoveryDialog, setShowRecoveryDialog] = useState(false);

  const loadCurrentState = async (sid = null) => {
    try {
      setLoading(true);
      setError(null);
      // Use sessionId from state if sid not provided
      // If sid is an object (from onSaveSuccess), extract session_id from it
      let sessionIdToUse = sid;
      if (sessionIdToUse && typeof sessionIdToUse === 'object') {
        sessionIdToUse = sessionIdToUse.session_id || sessionIdToUse;
      }
      sessionIdToUse = sessionIdToUse || sessionId || localStorage.getItem('current_session_id');
      
      if (!sessionIdToUse) {
        setError('No session ID available');
        setLoading(false);
        return;
      }
      
      const params = { params: { session_id: sessionIdToUse } };
      const [currentNodeData, historyData] = await Promise.all([
        getCurrentNode(params).catch(err => {
          // If session is finished or not found, reset to init state
          if (err.response?.status === 404 || err.response?.data?.session_status === 'finished') {
            localStorage.removeItem('current_session_id');
            setIsInitialized(false);
            setSessionId(null);
            setCurrentState(null);
            throw err;
          }
          throw err;
        }),
        getHistory(sessionIdToUse).catch(err => {
          // If session is finished, return empty nodes
          if (err.response?.data?.session_status === 'finished') {
            return { nodes: [] };
          }
          console.warn('Failed to load history:', err);
          return { nodes: [] };
        })
      ]);
      
      // Merge history nodes into current state
      const mergedData = {
        ...currentNodeData,
        history_nodes: historyData.nodes || [],
        nodes: historyData.nodes || []
      };
      
      setCurrentState(mergedData);
      if (mergedData.session_id) {
        setSessionId(mergedData.session_id);
        // Store in localStorage for persistence
        localStorage.setItem('current_session_id', mergedData.session_id);
      }
    } catch (err) {
      const errorMsg = err.response?.data?.error || err.message || 'Failed to load current state';
      
      // If session is finished or not found, reset to initialization state
      if (err.response?.status === 404 || err.response?.data?.session_status === 'finished') {
        localStorage.removeItem('current_session_id');
        setIsInitialized(false);
        setSessionId(null);
        setCurrentState(null);
        setError(null); // Clear error to show init form
        return;
      }
      
      setError(errorMsg);
      console.error('Error loading current state:', err);
      // Don't set currentState to null on error - keep previous state if available
      // This prevents UI from getting stuck on "Loading..."
    } finally {
      setLoading(false);
    }
  };

  // Auto-detect existing session on mount
  useEffect(() => {
    const detectSession = async () => {
      // Check if we should skip session detection (after reset)
      const skipDetection = localStorage.getItem('skip_session_detection');
      if (skipDetection === 'true') {
        localStorage.removeItem('skip_session_detection');
        // Clear any remaining session data
        localStorage.removeItem('current_session_id');
        setSessionId(null);
        setIsInitialized(false);
        setCurrentState(null);
        setShowRecoveryDialog(false);
        return; // Don't try to detect sessions, just show init form
      }
      
      try {
        // Check for session in localStorage first
        const storedSessionId = localStorage.getItem('current_session_id');
        if (storedSessionId) {
          try {
            const result = await checkSession({ params: { session_id: storedSessionId } });
            if (result.has_session) {
              setSessionId(storedSessionId);
              setIsInitialized(true);
              return;
            }
          } catch (e) {
            // Session not found, clear localStorage
            localStorage.removeItem('current_session_id');
          }
        }
        
        // Check for any unfinished sessions
        const result = await checkSession();
        if (result.has_session && result.session_id) {
          setSessionId(result.session_id);
          setIsInitialized(true);
        } else {
          // Show recovery dialog if there are unfinished sessions
          setShowRecoveryDialog(true);
        }
      } catch (err) {
        // Session doesn't exist or error - that's fine, show init form
        console.log('No existing session found');
        setShowRecoveryDialog(true);
      }
    };
    detectSession();
  }, []); // Run only once on mount

  useEffect(() => {
    // Only auto-load if we don't already have currentState
    // This prevents overwriting the state set from initialization response
    if (isInitialized && sessionId && !currentState) {
      loadCurrentState(sessionId);
    }
  }, [isInitialized, sessionId]);

  const handleInitialized = async (data) => {
    // Extract session_id from response first
    const sid = data.session_id || data.node?.session_id;
    if (sid) {
      setSessionId(sid);
      localStorage.setItem('current_session_id', sid);
      // Set initialized first so UI switches to CurrentState
      setIsInitialized(true);
      
      // Set current state from initialization response immediately
      // This prevents UI from being stuck on "Loading..." and avoids loading from MongoDB
      // before auto-save completes
      const initialState = {
        session_id: sid,
        current_node_id: data.node?.id,
        root_node_id: data.node?.id,
        step_number: data.node?.step_number || 1,
        all_hypotheses: (data.node?.hypotheses || []).map(h => ({
          id: h.id,
          description: h.description,
          category: h.category,
          confidence: h.confidence,
          status: h.status || 'active',
          evidence: []
        })),
        requested_data: data.node?.requested_data || [],
        next_requests: data.node?.requested_data || [],
        tree_summary: data.tree_summary || {
          total_nodes: 1,
          current_step: 1,
          active_hypotheses: data.node?.hypotheses?.length || 0
        },
        branches: [],
        is_focused: false,
        current_branch_ids: []
      };
      
      setCurrentState(initialState);
      
      // Fetch history in background (for new sessions, this will just be the initial node)
      getHistory(sid).then(historyData => {
        setCurrentState(prev => ({
          ...prev,
          history_nodes: historyData.nodes || [],
          nodes: historyData.nodes || []
        }));
      }).catch(err => {
        console.warn('Failed to load history after initialization:', err);
      });
      
      // Don't try to load from MongoDB immediately - use the initialization response data
      // The auto-save happens in background. Only load from MongoDB on page reload.
    } else {
      // If no session_id, still set initialized and current state
      setIsInitialized(true);
      setCurrentState(data);
    }
    setShowRecoveryDialog(false);
  };

  const handleResumeSession = async (sessionData) => {
    try {
      const sid = sessionData.session_id || sessionData.session?.session_id;
      if (!sid) {
        alert('Invalid session data received');
        return;
      }
      
      setSessionId(sid);
      localStorage.setItem('current_session_id', sid);
      setIsInitialized(true);
      setShowRecoveryDialog(false);
      
      // Load the full current state
      await loadCurrentState(sid);
    } catch (error) {
      console.error('Error resuming session:', error);
      alert('Error resuming session: ' + (error.response?.data?.error || error.message));
    }
  };

  const handleStartNew = () => {
    setShowRecoveryDialog(false);
    localStorage.removeItem('current_session_id');
  };

  const handleStateUpdate = (data) => {
    setCurrentState(data);
  };

  if (!isInitialized) {
    return (
      <div className="app-container">
        {showRecoveryDialog && (
          <SessionRecoveryDialog
            onResume={handleResumeSession}
            onDismiss={() => setShowRecoveryDialog(false)}
            onStartNew={handleStartNew}
          />
        )}
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

