import React, { useState, useEffect } from 'react';
import { saveSession, getSessionStatus } from '../services/api';
import '../styles/SessionManager.css';

function SessionManager({ sessionId, onSaveSuccess }) {
  const [saving, setSaving] = useState(false);
  const [sessionStatus, setSessionStatus] = useState(null);
  const [lastSaved, setLastSaved] = useState(null);

  useEffect(() => {
    if (sessionId) {
      loadSessionStatus();
      // Check status every 30 seconds
      const interval = setInterval(loadSessionStatus, 30000);
      return () => clearInterval(interval);
    }
  }, [sessionId]);

  const loadSessionStatus = async () => {
    if (!sessionId) return;
    try {
      const status = await getSessionStatus(sessionId);
      setSessionStatus(status);
      setLastSaved(status.last_saved_at);
    } catch (error) {
      console.error('Error loading session status:', error);
    }
  };

  const handleSave = async () => {
    if (!sessionId) {
      alert('No active session to save');
      return;
    }

    try {
      setSaving(true);
      const result = await saveSession(sessionId);
      alert('Session saved successfully!');
      setLastSaved(new Date().toISOString());
      if (onSaveSuccess) {
        // Pass sessionId, not the entire result object
        onSaveSuccess(sessionId);
      }
      // Reload status
      await loadSessionStatus();
    } catch (error) {
      alert('Error saving session: ' + (error.response?.data?.error || error.message));
    } finally {
      setSaving(false);
    }
  };

  if (!sessionId) {
    return null;
  }

  const hasUnsavedChanges = sessionStatus?.has_unsaved_changes;

  return (
    <div className="session-manager">
      <div className="session-info">
        <div className="session-id">
          <strong>Session ID:</strong> <code>{sessionId.substring(0, 8)}...</code>
        </div>
        {lastSaved && (
          <div className="last-saved">
            Last saved: {new Date(lastSaved).toLocaleString()}
          </div>
        )}
        {hasUnsavedChanges && (
          <div className="unsaved-indicator">
            ⚠️ Unsaved changes
          </div>
        )}
      </div>
      <button
        className="button button-primary"
        onClick={handleSave}
        disabled={saving}
        style={{
          background: hasUnsavedChanges ? '#ff9800' : '#4CAF50',
          color: 'white',
          border: 'none',
          padding: '10px 20px',
          fontSize: '14px',
          borderRadius: '4px',
          cursor: saving ? 'not-allowed' : 'pointer',
          opacity: saving ? 0.6 : 1
        }}
      >
        {saving ? 'Saving...' : '💾 Save Session'}
      </button>
    </div>
  );
}

export default SessionManager;
