import React, { useState, useEffect, useCallback } from 'react';
import { searchUsers, shareWithUser, getShareToken, getSharedWith } from '../services/api';
import '../styles/ShareModal.css';

const SEARCH_DEBOUNCE_MS = 300;

export default function ShareModal({ isOpen, onClose, sessionId, onCopied }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [sharedWith, setSharedWith] = useState([]);
  const [searching, setSearching] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const loadSharedWith = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await getSharedWith(sessionId);
      setSharedWith(data.shared_with || []);
    } catch (e) {
      console.warn('Failed to load shared-with:', e);
    }
  }, [sessionId]);

  useEffect(() => {
    if (isOpen && sessionId) loadSharedWith();
  }, [isOpen, sessionId, loadSharedWith]);

  useEffect(() => {
    if (!isOpen) return;
    const q = searchQuery.trim();
    if (q.length < 2) {
      setSearchResults([]);
      return;
    }
    const t = setTimeout(async () => {
      setSearching(true);
      setError('');
      try {
        const data = await searchUsers(q);
        setSearchResults(data.users || []);
      } catch (e) {
        setError(e.response?.data?.error || e.message || 'Search failed');
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchQuery, isOpen]);

  const addSelected = (u) => {
    if (selectedUsers.some((x) => x.id === u.id)) return;
    if (sharedWith.some((x) => x.id === u.id)) return;
    setSelectedUsers((prev) => [...prev, u]);
  };

  const removeSelected = (id) => {
    setSelectedUsers((prev) => prev.filter((x) => x.id !== id));
  };

  const handleCopyLink = async () => {
    if (!sessionId) return;
    setSharing(true);
    setError('');
    try {
      for (const u of selectedUsers) {
        await shareWithUser(sessionId, u.id);
      }
      const data = await getShareToken(sessionId);
      const url = data.share_url || `${window.location.origin}${window.location.pathname || '/'}?token=${data.share_token}`;
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
      loadSharedWith();
      setSelectedUsers([]);
      setSearchQuery('');
      setSearchResults([]);
      if (onCopied) onCopied(url);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Failed to share');
    } finally {
      setSharing(false);
    }
  };

  const canCopy = selectedUsers.length > 0;

  if (!isOpen) return null;

  return (
    <div className="share-modal-overlay" onClick={onClose}>
      <div className="share-modal" onClick={(e) => e.stopPropagation()}>
        <div className="share-modal-header">
          <h3>Share board with team members</h3>
          <button type="button" className="share-modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <p className="share-modal-hint">Search by name or email. Only registered users can be added. They must sign in to open the link.</p>

        <div className="share-modal-search">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by name or email..."
            autoFocus
          />
          {searching && <span className="share-modal-spinner">Searching…</span>}
        </div>

        {searchResults.length > 0 && (
          <div className="share-modal-results">
            {searchResults.map((u) => {
              const alreadyShared = sharedWith.some((x) => x.id === u.id);
              const selected = selectedUsers.some((x) => x.id === u.id);
              return (
                <button
                  type="button"
                  key={u.id}
                  className={`share-modal-user ${selected ? 'selected' : ''} ${alreadyShared ? 'disabled' : ''}`}
                  onClick={() => !alreadyShared && addSelected(u)}
                  disabled={alreadyShared}
                >
                  <span className="share-modal-user-name">{u.name || u.email}</span>
                  <span className="share-modal-user-email">{u.email}</span>
                  {alreadyShared && <span className="share-modal-badge">Already shared</span>}
                  {selected && !alreadyShared && <span className="share-modal-badge">Selected</span>}
                </button>
              );
            })}
          </div>
        )}

        {selectedUsers.length > 0 && (
          <div className="share-modal-selected">
            <strong>Selected:</strong>
            {selectedUsers.map((u) => (
              <span key={u.id} className="share-modal-chip">
                {u.name || u.email}
                <button type="button" onClick={() => removeSelected(u.id)} aria-label="Remove">×</button>
              </span>
            ))}
          </div>
        )}

        {sharedWith.length > 0 && (
          <div className="share-modal-shared">
            <strong>Already shared with:</strong>
            {sharedWith.map((u) => (
              <span key={u.id} className="share-modal-chip static">{u.name || u.email}</span>
            ))}
          </div>
        )}

        {error && <div className="share-modal-error">{error}</div>}

        <div className="share-modal-actions">
          <button type="button" className="button button-secondary" onClick={onClose}>Cancel</button>
          <button
            type="button"
            className="button button-primary"
            onClick={handleCopyLink}
            disabled={!canCopy || sharing}
          >
            {copied ? '✓ Link copied!' : sharing ? 'Sharing…' : canCopy ? `Share with ${selectedUsers.length} user(s) & copy link` : 'Search and select users to share with'}
          </button>
        </div>
      </div>
    </div>
  );
}
