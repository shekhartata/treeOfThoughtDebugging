import React, { useState, useEffect } from 'react';
import { uploadArtifact, unfocusBranches } from '../services/api';
import '../styles/ArtifactUpload.css';

function ArtifactUpload({ branches, isFocused, currentBranchIds, onStateUpdate, onRefresh }) {
  const [artifactName, setArtifactName] = useState('');
  const [artifactContent, setArtifactContent] = useState('');
  const [selectAll, setSelectAll] = useState(true);
  const [selectedBranches, setSelectedBranches] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Filter and sort active branches by hypothesis number
  const getHypothesisNumber = (hypId) => {
    const match = hypId?.match(/hyp_(\d+)/);
    return match ? parseInt(match[1], 10) : 999;
  };
  
  const activeBranches = (branches?.filter(b => b.status === 'active') || []).sort((a, b) => {
    return getHypothesisNumber(a.hypothesis_id) - getHypothesisNumber(b.hypothesis_id);
  });

  useEffect(() => {
    if (activeBranches.length > 0) {
      setSelectedBranches(new Set(activeBranches.map(b => b.hypothesis_id)));
    }
  }, [branches]);

  const handleUnfocus = async () => {
    try {
      const data = await unfocusBranches();
      if (onStateUpdate) onStateUpdate(data);
      if (onRefresh) onRefresh();
    } catch (error) {
      alert('Error unfocusing: ' + (error.response?.data?.error || error.message));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!artifactName.trim() || !artifactContent.trim()) {
      setError('Please provide both artifact name and content');
      return;
    }

    // If in focused mode (from backtrack), use the focused branches
    // Otherwise, use checkbox selection
    let branchIds;
    if (isFocused && currentBranchIds && currentBranchIds.length > 0) {
      branchIds = currentBranchIds;
    } else {
      branchIds = selectAll ? null : Array.from(selectedBranches);
      if (!selectAll && branchIds.length === 0) {
        setError('Please select at least one branch to evaluate');
        return;
      }
    }

    try {
      setLoading(true);
      setError(null);
      const data = await uploadArtifact(artifactName, artifactContent, branchIds);
      if (onStateUpdate) onStateUpdate(data);
      if (onRefresh) onRefresh();
      
      // Clear form
      setArtifactName('');
      setArtifactContent('');
      
      alert(`Artifact processed successfully! Created ${data.nodes_created || 0} nodes.`);
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Failed to process artifact');
    } finally {
      setLoading(false);
    }
  };

  const toggleBranch = (branchId) => {
    const newSelected = new Set(selectedBranches);
    if (newSelected.has(branchId)) {
      newSelected.delete(branchId);
    } else {
      newSelected.add(branchId);
    }
    setSelectedBranches(newSelected);
    setSelectAll(false);
  };

  const toggleSelectAll = (checked) => {
    setSelectAll(checked);
    if (checked) {
      setSelectedBranches(new Set(activeBranches.map(b => b.hypothesis_id)));
    }
  };

  return (
    <div className="artifact-upload">
      <h3>📎 Upload Artifact</h3>
      
      {isFocused && (
        <div className="focused-mode-indicator">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <strong>🎯 Focused Mode Active</strong>
              <p style={{ margin: '5px 0 0 0', fontSize: '13px', color: '#666' }}>
                Future artifacts will only evaluate the focused branch.
              </p>
            </div>
            <button className="button button-warning" onClick={handleUnfocus} style={{ fontSize: '13px', padding: '8px 16px' }}>
              Unfocus (Evaluate All)
            </button>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="artifact-name">Artifact Name:</label>
          <input
            type="text"
            id="artifact-name"
            value={artifactName}
            onChange={(e) => setArtifactName(e.target.value)}
            placeholder="e.g., db.currentOp() output"
          />
        </div>
        <div className="form-group">
          <label htmlFor="artifact-content">Artifact Content:</label>
          <textarea
            id="artifact-content"
            value={artifactContent}
            onChange={(e) => setArtifactContent(e.target.value)}
            placeholder="Paste MongoDB command output, logs, or metrics here..."
            rows="6"
          />
        </div>
        
        {activeBranches.length > 1 && !isFocused && (
          <div className="form-group">
            <label>
              <input
                type="checkbox"
                checked={selectAll}
                onChange={(e) => toggleSelectAll(e.target.checked)}
              />
              Evaluate all active branches (uncheck to select specific branches)
            </label>
            {!selectAll && (
              <div className="branch-checkboxes">
                {activeBranches.map((branch) => {
                  const hypNumber = getHypothesisNumber(branch.hypothesis_id);
                  const displayNumber = hypNumber !== 999 ? hypNumber : '?';
                  
                  return (
                    <label key={branch.hypothesis_id} style={{ display: 'block', margin: '5px 0' }}>
                      <input
                        type="checkbox"
                        checked={selectedBranches.has(branch.hypothesis_id)}
                        onChange={() => toggleBranch(branch.hypothesis_id)}
                      />
                      <span style={{ fontWeight: 'bold', color: '#667eea', marginRight: '5px' }}>
                        Hypothesis {displayNumber}:
                      </span>
                      {branch.hypothesis?.description || branch.hypothesis_id} 
                      ({(branch.hypothesis?.confidence * 100 || 0).toFixed(0)}%)
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {error && <div className="error-message">{error}</div>}
        <button type="submit" className="button" disabled={loading}>
          {loading ? 'Processing...' : 'Upload & Analyze'}
        </button>
      </form>
    </div>
  );
}

export default ArtifactUpload;

