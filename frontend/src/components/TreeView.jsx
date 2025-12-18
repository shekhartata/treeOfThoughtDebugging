import React, { useCallback, useMemo, useEffect, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import CustomNode from './CustomNode';
import EvaluationDetailsModal from './EvaluationDetailsModal';
import api from '../services/api';
import '../styles/TreeView.css';

const nodeTypes = {
  custom: CustomNode,
};

function TreeView({ nodes: initialNodes, currentNodeId, rootNodeId, onBacktrack, onExpand, onRefresh }) {
  const [nodes, setNodes] = useState(initialNodes || []);
  const [reactNodes, setReactNodes, onNodesChange] = useNodesState([]);
  const [reactEdges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Load history if not provided
  useEffect(() => {
    if (!initialNodes || initialNodes.length === 0) {
      loadHistory();
    } else {
      setNodes(initialNodes);
    }
  }, [initialNodes]);

  const loadHistory = async () => {
    try {
      setLoading(true);
      const response = await api.get('/history');
      if (response.data && response.data.nodes) {
        setNodes(response.data.nodes);
      }
    } catch (error) {
      console.error('Error loading history:', error);
    } finally {
      setLoading(false);
    }
  };

  // Build tree structure from nodes
  useMemo(() => {
    if (!nodes || nodes.length === 0) {
      setReactNodes([]);
      setEdges([]);
      return;
    }

    // Create a map of nodes
    const nodesMap = new Map();
    nodes.forEach(node => {
      nodesMap.set(node.id, node);
    });

    // Build React Flow nodes and edges
    const flowNodes = [];
    const flowEdges = [];
    const processed = new Set();
    let yOffset = 0;

    const buildTree = (nodeId, parentPos = null, level = 0) => {
      if (processed.has(nodeId)) return null;
      processed.add(nodeId);

      const node = nodesMap.get(nodeId);
      if (!node) return null;

      const isCurrent = nodeId === currentNodeId;
      const status = node.hypothesis?.status || node.branch_status || 'active';
      
      // Calculate position (horizontal layout with better spacing)
      const x = level * 350;
      const y = yOffset;
      yOffset += 180;

      const flowNode = {
        id: nodeId,
        type: 'custom',
        position: { x, y },
        data: {
          label: node.hypothesis?.description || (node.hypotheses_count > 0 ? `${node.hypotheses_count} Initial Hypotheses` : 'Root Node'),
          node: node,
          isCurrent,
          status,
          onBacktrack: () => handleBacktrack(nodeId),
          onGenerate: () => handleGenerate(nodeId),
          onViewDetails: (id) => {
            setSelectedNodeId(id);
            setIsModalOpen(true);
          },
        },
      };

      flowNodes.push(flowNode);

      // Add edge from parent
      if (node.parent_id) {
        flowEdges.push({
          id: `e${node.parent_id}-${nodeId}`,
          source: node.parent_id,
          target: nodeId,
          type: 'smoothstep',
          animated: status === 'active',
        });
      }

      // Process children (use children_ids if available, otherwise children)
      const children = node.children_ids || node.children || [];
      if (children.length > 0) {
        children.forEach(childId => {
          buildTree(childId, { x, y }, level + 1);
        });
      }

      return flowNode;
    };

    // Start from root
    const rootId = rootNodeId || nodes.find(n => !n.parent_id)?.id;
    if (rootId) {
      buildTree(rootId);
    }

    setReactNodes(flowNodes);
    setEdges(flowEdges);
  }, [nodes, currentNodeId, rootNodeId, setReactNodes, setEdges]);

  const handleBacktrack = async (nodeId) => {
    try {
      const { backtrack } = await import('../services/api');
      const data = await backtrack(nodeId, true);
      if (onBacktrack) onBacktrack(data);
      if (onRefresh) onRefresh();
    } catch (error) {
      alert('Error backtracking: ' + (error.response?.data?.error || error.message));
    }
  };

  const handleGenerate = async (nodeId) => {
    try {
      const { generateNode } = await import('../services/api');
      const data = await generateNode(nodeId);
      if (onExpand) onExpand(data);
      if (onRefresh) onRefresh();
    } catch (error) {
      alert('Error generating new ideas: ' + (error.response?.data?.error || error.message));
    }
  };

  if (loading) {
    return <div className="tree-empty">Loading history...</div>;
  }

  if (!nodes || nodes.length === 0) {
    return <div className="tree-empty">No history available yet.</div>;
  }

  return (
    <div className="tree-view-container">
      <div className="tree-controls">
        <div className="tree-legend">
          <div className="legend-item">
            <div className="legend-color active"></div>
            <span>Active Branch</span>
          </div>
          <div className="legend-item">
            <div className="legend-color pruned"></div>
            <span>Pruned Branch</span>
          </div>
          <div className="legend-item">
            <div className="legend-color accepted"></div>
            <span>Accepted Branch</span>
          </div>
          <div className="legend-item">
            <div className="legend-color current"></div>
            <span>Current Node</span>
          </div>
        </div>
        <div className="tree-hint">
          💡 Click "Backtrack" or "Expand" buttons on nodes to interact
        </div>
      </div>
      <div style={{ width: '100%', height: '600px', border: '1px solid #ddd', borderRadius: '8px' }}>
        <ReactFlow
          nodes={reactNodes}
          edges={reactEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          attributionPosition="bottom-left"
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
      <EvaluationDetailsModal
        nodeId={selectedNodeId}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedNodeId(null);
        }}
      />
    </div>
  );
}

export default TreeView;

