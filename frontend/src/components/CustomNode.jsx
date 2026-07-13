import React from 'react';
import { Handle, Position } from 'reactflow';
import '../styles/CustomNode.css';

function CustomNode({ data }) {
  const { label, node, isCurrent, status, onBacktrack, onGenerate, onViewDetails } = data;
  
  const confidence = node.hypothesis?.confidence || node.confidence || 0;
  const confidencePercent = (confidence * 100).toFixed(0);
  const artifactCount = node.artifacts?.length || 0;
  const hasEvaluationDetails = node.evaluation_details || node.pruning_details;

  const getStatusColor = () => {
    if (isCurrent) return '#9c27b0';
    if (status === 'pruned') return '#f44336';
    if (status === 'accepted') return '#2196f3';
    return '#4caf50';
  };

  return (
    <div className={`custom-node ${status} ${isCurrent ? 'current' : ''}`}>
      <Handle type="target" position={Position.Top} />
      
      <div className="node-header">
        <div className="node-title">{label}</div>
        {isCurrent && <span className="current-badge">Current</span>}
      </div>
      
      <div className="node-badges">
        <span className="confidence-badge" style={{ 
          background: confidence >= 0.7 ? '#4caf50' : confidence >= 0.4 ? '#ff9800' : '#f44336' 
        }}>
          {confidencePercent}%
        </span>
        <span className="artifact-badge">{artifactCount} artifact(s)</span>
      </div>
      
      <div className="node-actions">
        {onBacktrack && (
          <button 
            className="node-button backtrack-button"
            onClick={() => onBacktrack()}
          >
            Backtrack
          </button>
        )}
        {onGenerate && (
          <button 
            className="node-button expand-button"
            onClick={() => onGenerate()}
          >
            Generate
          </button>
        )}
        {hasEvaluationDetails && onViewDetails && (
          <button 
            className="node-button details-button"
            onClick={() => onViewDetails(node.id)}
            title="View evaluation and pruning details"
          >
            View Details
          </button>
        )}
      </div>
      
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default CustomNode;

