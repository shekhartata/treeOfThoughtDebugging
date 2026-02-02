import React, { useState } from 'react';
import { listUnfinishedSessions, loadSession } from '../services/api';
import '../styles/SessionRecoveryDialog.css';

function SessionRecoveryDialog({ onResume, onDismiss, onStartNew }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [resuming, setResuming] = useState(false);

  React.useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    try {
      setLoading(true);
      const data = await listUnfinishedSessions();
      setSessions(data.sessions || []);
    } catch (error) {
      console.error('Error loading unfinished sessions:', error);
      setSessions([]);
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async (sessionId) => {
    try {
      setResuming(true);
      const result = await loadSession(sessionId);
      if (onResume) {
        onResume(result);
      }
    } catch (error) {
      alert('Error loading session: ' + (error.response?.data?.error || error.message));
    } finally {
      setResuming(false);
    }
  };

  if (loading) {
    return (
      <div className="session-recovery-overlay">
        <div className="session-recovery-dialog">
          <h2>Loading Sessions...</h2>
        </div>
      </div>
    );
  }

  if (sessions.length === 0) {
    return null; // No unfinished sessions, don't show dialog
  }

  return (
    <div className="session-recovery-overlay">
      <div className="session-recovery-dialog">
        <h2>📂 Unfinished Debugging Sessions</h2>
        <p>You have {sessions.length} unfinished session(s). Would you like to resume one?</p>
        
        <div className="sessions-list">
          {sessions.map((session) => (
            <div key={session.session_id} className="session-item">
              <div className="session-details">
                <div className="session-problem">
                  <strong>{session.problem_summary || 'Untitled Session'}</strong>
                </div>
                <div className="session-meta">
                  <span>Created: {new Date(session.created_at).toLocaleString()}</span>
                  {session.last_saved_at && (
                    <span>Last saved: {new Date(session.last_saved_at).toLocaleString()}</span>
                  )}
                  <span>Steps: {session.step_counter}</span>
                  <span>Nodes: {session.total_nodes}</span>
                </div>
              </div>
              <button
                className="button button-primary"
                onClick={() => handleResume(session.session_id)}
                disabled={resuming}
              >
                {resuming ? 'Loading...' : 'Resume'}
              </button>
            </div>
          ))}
        </div>

        <div className="dialog-actions">
          <button
            className="button button-secondary"
            onClick={onStartNew}
          >
            Start New Session
          </button>
          {onDismiss && (
            <button
              className="button button-secondary"
              onClick={onDismiss}
            >
              Dismiss
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default SessionRecoveryDialog;
