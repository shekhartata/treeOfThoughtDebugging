import React, { useState } from 'react';
import '../styles/AddHypothesisModal.css';

const CATEGORIES = [
  'indexing',
  'query_shape',
  'schema',
  'wt_cache',
  'storage',
  'replication',
  'networking',
];

export default function AddHypothesisModal({ isOpen, onClose, onSubmit, sessionId }) {
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('schema');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const desc = (description || '').trim();
    if (!desc) {
      setError('Hypothesis description is required');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      await onSubmit(desc, category);
      setDescription('');
      setCategory('schema');
      onClose();
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Failed to add hypothesis');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="add-hypothesis-overlay" onClick={onClose}>
      <div className="add-hypothesis-modal" onClick={(e) => e.stopPropagation()}>
        <div className="add-hypothesis-header">
          <h3>Add hypothesis (manual branch)</h3>
          <button type="button" className="add-hypothesis-close" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit} className="add-hypothesis-form">
          {error && <div className="add-hypothesis-error">{error}</div>}
          <div className="add-hypothesis-field">
            <label htmlFor="add-hyp-desc">Description *</label>
            <textarea
              id="add-hyp-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe your hypothesis..."
              rows={4}
              required
            />
          </div>
          <div className="add-hypothesis-field">
            <label htmlFor="add-hyp-category">Category</label>
            <select
              id="add-hyp-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="add-hypothesis-actions">
            <button type="button" className="button button-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="button button-primary" disabled={submitting}>
              {submitting ? 'Adding…' : 'Add hypothesis'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
