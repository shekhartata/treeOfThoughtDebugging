import React, { useState, useEffect } from 'react';
import { getMySessions } from '../services/api';
import '../styles/Dashboard.css';

export default function Dashboard({ user, onStartBoard, onSelectSession, onLogout }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getMySessions()
      .then((data) => {
        if (!cancelled && data.sessions) setSessions(data.sessions);
      })
      .catch((err) => {
        if (!cancelled) setError(err.response?.data?.error || err.message || 'Failed to load boards');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString(undefined, { dateStyle: 'short' }) + ' ' + d.toLocaleTimeString(undefined, { timeStyle: 'short' });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="app-container dashboard-container">
      <div className="container dashboard-card">
        <div className="header">
          <div className="header-title">
            <h1>🌳 MongoDB Tree-of-Thought Debugging Tool</h1>
            <p>Interactive reasoning engine for diagnosing MongoDB issues</p>
          </div>
          <div className="header-user">
            <span>{user?.email}</span>
            <button type="button" className="header-logout" onClick={onLogout}>Sign out</button>
          </div>
        </div>
        <div className="dashboard-content">
          <div className="dashboard-actions">
            <button type="button" className="dashboard-start-btn" onClick={onStartBoard}>
              Start a board
            </button>
          </div>
          <section className="dashboard-section">
            <h2>Active boards</h2>
            {error && (
              <div className="dashboard-error" role="alert">{error}</div>
            )}
            {loading ? (
              <p className="dashboard-loading">Loading boards…</p>
            ) : sessions.length === 0 ? (
              <p className="dashboard-empty">No active boards. Start a board to begin.</p>
            ) : (
              <ul className="dashboard-session-list">
                {sessions.map((s) => (
                  <li key={s.session_id}>
                    <button
                      type="button"
                      className="dashboard-session-item"
                      onClick={() => onSelectSession(s.session_id)}
                    >
                      <span className="dashboard-session-summary">
                        {s.problem_summary || 'Untitled board'}
                      </span>
                      <span className="dashboard-session-meta">
                        Updated {formatDate(s.updated_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
