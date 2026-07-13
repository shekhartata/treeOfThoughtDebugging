import React, { useState } from 'react';
import TreeSummary from './TreeSummary';
import HypothesesList from './HypothesesList';
import NextRequests from './NextRequests';
import ArtifactUpload from './ArtifactUpload';
import TreeView from './TreeView';
import FinalAnalysis from './FinalAnalysis';
import SessionManager from './SessionManager';
import AddHypothesisModal from './AddHypothesisModal';
import { resetSession, addBranch } from '../services/api';
import '../styles/CurrentState.css';

function CurrentState({ currentState, onStateUpdate, onRefresh, loading }) {
  const [showHistory, setShowHistory] = useState(false);
  const [showAddHypothesisModal, setShowAddHypothesisModal] = useState(false);

  if (!currentState) {
    return (
      <div className="current-state-loading">
        <p>Loading board…</p>
      </div>
    );
  }

  return (
    <>
      <div className="section">
        <SessionManager 
          sessionId={currentState.session_id} 
          onSaveSuccess={onRefresh}
        />
        <h2>Current Reasoning Step: {currentState.step_number || '-'}</h2>
        
        <TreeSummary summary={currentState.tree_summary} />
        
        <h3 style={{ marginTop: '20px' }}>Active Hypotheses</h3>
        <HypothesesList 
          hypotheses={currentState.all_hypotheses || []}
          onStateUpdate={onStateUpdate}
          onRefresh={onRefresh}
          sessionId={currentState.session_id}
        />
        
        <NextRequests requests={currentState.next_requests || currentState.requested_data || []} />
        
        <div className="section add-hypothesis-row">
          <button
            type="button"
            className="button button-primary"
            onClick={() => setShowAddHypothesisModal(true)}
            style={{ marginRight: '10px' }}
          >
            ➕ Add hypothesis (create branch)
          </button>
        </div>
        
        <ArtifactUpload 
          branches={currentState.branches || []}
          isFocused={currentState.is_focused || false}
          currentBranchIds={currentState.current_branch_ids || []}
          sessionId={currentState.session_id}
          onStateUpdate={onStateUpdate}
          onRefresh={onRefresh}
        />
      </div>

      <div className="section" style={{ marginTop: '20px' }}>
        <h3>📜 Reasoning History</h3>
        <button 
          className="button button-secondary" 
          onClick={() => {
            setShowHistory(!showHistory);
            if (!showHistory) {
              onRefresh();
            }
          }}
          style={{ marginBottom: '15px' }}
        >
          {showHistory ? 'Hide' : 'Show'} History View
        </button>
        {showHistory && (
          <TreeView 
            nodes={currentState.nodes || currentState.history_nodes || []}
            currentNodeId={currentState.current_node_id}
            rootNodeId={currentState.root_node_id}
            sessionId={currentState.session_id}
            onBacktrack={onStateUpdate}
            onExpand={onStateUpdate}
            onRefresh={onRefresh}
          />
        )}
      </div>

      <AddHypothesisModal
        isOpen={showAddHypothesisModal}
        onClose={() => setShowAddHypothesisModal(false)}
        sessionId={currentState.session_id}
        onSubmit={async (description, category) => {
          await addBranch(currentState.session_id, description, category);
          onRefresh();
        }}
      />

      <FinalAnalysis 
        isComplete={currentState.is_complete}
        sessionId={currentState.session_id}
        onStateUpdate={onStateUpdate}
      />
      
      <div className="section" style={{ marginTop: '20px', borderTop: '2px solid #ddd', paddingTop: '20px' }}>
        <button 
          className="button button-danger" 
          onClick={async () => {
            if (window.confirm('Are you sure you want to end this debugging session? This will clear all tree content and reset the session.')) {
                try {
                await resetSession(currentState.session_id);
                // Clear localStorage and add a flag to skip session detection on reload
                localStorage.removeItem('current_session_id');
                localStorage.setItem('skip_session_detection', 'true');
                alert('Session reset successfully! The page will reload.');
                window.location.reload();
            } catch (error) {
                alert('Error resetting session: ' + (error.response?.data?.error || error.message));
            }
            }
          }}
          style={{ 
            background: '#f44336', 
            color: 'white', 
            border: 'none',
            padding: '12px 24px',
            fontSize: '16px',
            borderRadius: '4px',
            cursor: 'pointer'
          }}
        >
          🔴 End Debugging Session
        </button>
      </div>
    </>
  );
}

export default CurrentState;

