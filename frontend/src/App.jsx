import React, { useState, useEffect } from 'react';
import './App.css';
import { useAuth } from './contexts/AuthContext';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import InitializeForm from './components/InitializeForm';
import CurrentState from './components/CurrentState';
import TreeView from './components/TreeView';
import SessionRecoveryDialog from './components/SessionRecoveryDialog';
import ShareModal from './components/ShareModal';
import { getCurrentNode, checkSession, getHistory, joinBoard, setBoardToken, clearBoardToken, clearCurrentSessionStorage } from './services/api';

function App() {
  const { user, loading: authLoading, logout } = useAuth();
  const [isInitialized, setIsInitialized] = useState(false);
  const [currentState, setCurrentState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [showRecoveryDialog, setShowRecoveryDialog] = useState(false);
  const [joiningByToken, setJoiningByToken] = useState(
    () => typeof window !== 'undefined' && !!new URLSearchParams(window.location.search).get('token')
  );
  const [shareUrl, setShareUrl] = useState(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);

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

  // When user logs in and URL has ?token=, run join (share link requires login)
  useEffect(() => {
    if (!user) {
      setJoiningByToken(false); // clear loading when user signs out so we don't stay stuck
      return;
    }
    const urlParams = new URLSearchParams(window.location.search);
    const shareToken = urlParams.get('token');
    if (!shareToken) return;
    // When opening a share link, always join; clear any existing session so we don't show wrong board
    if (sessionId) {
      clearBoardToken(sessionId);
      clearCurrentSessionStorage();
      setSessionId(null);
      setIsInitialized(false);
      setCurrentState(null);
    }
    let cancelled = false;
    setJoiningByToken(true);
    setError(null);
    const timeoutMs = 12000;
    const timeoutId = setTimeout(() => {
      if (!cancelled) {
        setJoiningByToken(false);
        setError('Opening shared board timed out. Please try again or check the link.');
      }
    }, timeoutMs);
    joinBoard(shareToken)
      .then((joinData) => {
        if (cancelled) return;
        const sid = joinData?.session_id != null ? String(joinData.session_id) : null;
        const tokenToStore = joinData?.share_token || shareToken;
        if (sid) {
          localStorage.setItem('current_session_id', sid);
          setBoardToken(sid, tokenToStore);
          setSessionId(sid);
          setIsInitialized(true);
          setError(null);
          window.history.replaceState({}, '', window.location.pathname || '/');
          loadCurrentState(sid).catch((err) => {
            console.error('Failed to load board after join:', err);
            setError(err.response?.data?.error || err.message || 'Failed to load board.');
          });
        } else {
          setError('Invalid share link response. Please ask the owner for a new link.');
        }
      })
      .catch((e) => {
        if (!cancelled) {
          console.error('Failed to join board:', e);
          const msg = e.response?.data?.error || e.message || 'Failed to open shared board';
          setError(msg + (e.response?.status === 403 ? ' Make sure you’re signed in with the account the owner shared the link with.' : ''));
        }
      })
      .finally(() => {
        if (!cancelled) setJoiningByToken(false);
        clearTimeout(timeoutId);
      });
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [user]);

  // Auto-detect existing session on mount (only when no token in URL; token flow needs login first)
  useEffect(() => {
    const detectSession = async () => {
      const urlParams = new URLSearchParams(window.location.search);
      const shareToken = urlParams.get('token');
      if (shareToken) {
        // Share link: require login; join will run in the effect above when user is set
        setJoiningByToken(false);
        return;
      }
      setJoiningByToken(false);

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

  // After sign-in, restore a board only if current user has access; otherwise show dashboard
  useEffect(() => {
    if (!user || sessionId || joiningByToken) return;
    const stored = localStorage.getItem('current_session_id');
    if (!stored) {
      setShowDashboard(true);
      setShowRecoveryDialog(false);
      return;
    }
    checkSession({ params: { session_id: stored } })
      .then((result) => {
        if (result.has_session) {
          setSessionId(stored);
          setIsInitialized(true);
        } else {
          clearBoardToken(stored);
          clearCurrentSessionStorage();
          setShowDashboard(true);
          setShowRecoveryDialog(false);
        }
      })
      .catch(() => {
        clearBoardToken(stored);
        clearCurrentSessionStorage();
        setShowDashboard(true);
        setShowRecoveryDialog(false);
      });
  }, [user]);

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
        current_branch_ids: [],
        is_owner: data.is_owner !== false
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

  const handleLogout = () => {
    const sid = currentState?.session_id || sessionId;
    if (sid) clearBoardToken(sid);
    clearCurrentSessionStorage();
    logout();
    setSessionId(null);
    setCurrentState(null);
    setIsInitialized(false);
  };

  const handleReturnToLogin = () => {
    const sid = currentState?.session_id || sessionId;
    if (sid) clearBoardToken(sid);
    clearCurrentSessionStorage();
    setSessionId(null);
    setCurrentState(null);
    setIsInitialized(false);
    logout();
  };

  const handleShare = () => {
    const sid = currentState?.session_id || sessionId;
    if (!sid) return;
    setShowShareModal(true);
  };

  const handleShareCopied = (url) => {
    setShareUrl(url);
    setTimeout(() => setShareUrl(null), 3000);
  };

  const handleStartBoard = () => {
    setShowDashboard(false);
    setShowRecoveryDialog(false);
  };

  const handleSelectSession = (sid) => {
    setSessionId(sid);
    localStorage.setItem('current_session_id', sid);
    setIsInitialized(true);
    setShowDashboard(false);
    setShowRecoveryDialog(false);
    loadCurrentState(sid);
  };

  const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
  const hasShareToken = urlParams && urlParams.get('token');

  if (!user) {
    return (
      <Login
        message={hasShareToken ? 'Sign in to open this shared board. Only people the owner shared with can access it.' : undefined}
      />
    );
  }

  if (joiningByToken) {
    return (
      <div className="app-container app-loading">
        <div className="container app-loading-card">
          <p className="app-loading-text">Loading shared board…</p>
        </div>
      </div>
    );
  }

  if (showDashboard) {
    return (
      <Dashboard
        user={user}
        onStartBoard={handleStartBoard}
        onSelectSession={handleSelectSession}
        onLogout={handleLogout}
      />
    );
  }

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
            <div className="header-title">
              <h1>🌳 MongoDB Tree-of-Thought Debugging Tool</h1>
              <p>Interactive reasoning engine for diagnosing MongoDB issues</p>
            </div>
            <div className="header-user">
              <span>{user?.email}</span>
              <button type="button" className="header-logout" onClick={handleLogout}>Sign out</button>
            </div>
          </div>
          <div className="content">
            {error && (
              <div className="error-message">
                {error}
              </div>
            )}
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
          <div className="header-title">
            <h1>🌳 MongoDB Tree-of-Thought Debugging Tool</h1>
            <p>Interactive reasoning engine for diagnosing MongoDB issues</p>
          </div>
          <div className="header-user">
            {user ? (
              <button type="button" className="header-logout header-logout-primary" onClick={handleLogout}>
                Sign out
              </button>
            ) : (
              <button type="button" className="header-logout header-logout-primary" onClick={handleReturnToLogin}>
                Sign in to switch account
              </button>
            )}
            {user && sessionId && currentState && (currentState.is_owner !== false) && (
              <>
                <button type="button" className="header-share" onClick={handleShare}>
                  {shareUrl ? '✓ Link copied!' : 'Share'}
                </button>
                <ShareModal
                  isOpen={showShareModal}
                  onClose={() => setShowShareModal(false)}
                  sessionId={currentState?.session_id || sessionId}
                  onCopied={handleShareCopied}
                />
              </>
            )}
            <span className="header-user-email">{user?.email || (sessionId && !user ? 'Collaborator' : '')}</span>
            {user && sessionId && currentState && (
              <span className="header-user-role" title={currentState.is_owner !== false ? 'You own this board' : 'You were shared this board'}>
                {currentState.is_owner !== false ? 'Owner' : 'Collaborator'}
              </span>
            )}
          </div>
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

