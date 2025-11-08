"""
Flask Web Application for MongoDB Tree-of-Thought Debugging Tool
Provides interactive web interface for Consulting Engineers.
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from tot_engine import TreeOfThoughtEngine, ReasoningNode
from llm_integration import LLMIntegration
import os
import json
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Initialize global instances
engine: Optional[TreeOfThoughtEngine] = None
# LLM is now REQUIRED by default (require_llm=True)
# Set require_llm=False if you want to allow fallback mode
llm_integration = LLMIntegration(require_llm=True)

@app.route('/')
def index():
    """Serve the main application page."""
    return render_template('index.html')

@app.route('/api/initialize', methods=['POST'])
def initialize():
    """Initialize the ToT engine with a problem statement."""
    global engine
    
    data = request.json
    problem_summary = data.get('problem_summary', '')
    
    if not problem_summary:
        return jsonify({'error': 'Problem summary is required'}), 400
    
    # Initialize engine with LLM integration
    # LLM will generate hypotheses by default
    # Pass use_hardcoded_fallback=True in request to use fallback mode
    use_fallback = data.get('use_hardcoded_fallback', False)
    
    engine = TreeOfThoughtEngine(llm_integration=llm_integration)
    initial_node = engine.initialize(problem_summary, use_hardcoded_fallback=use_fallback)
    
    # Get LLM analysis text for display
    llm_analysis_text = ""
    if llm_integration.use_llm and not use_fallback:
        try:
            result = llm_integration.get_initial_analysis(problem_summary)
            llm_analysis_text = result.get('analysis', '')
        except:
            pass
    
    return jsonify({
        'success': True,
        'node': {
            'id': initial_node.id,
            'step_number': initial_node.step_number,
            'hypotheses': [
                {
                    'id': h.id,
                    'description': h.description,
                    'category': h.category,
                    'confidence': h.confidence,
                    'status': h.status
                }
                for h in initial_node.hypotheses
            ],
            'requested_data': initial_node.requested_data
        },
        'llm_analysis': llm_analysis_text,
        'tree_summary': engine.get_tree_summary()
    })

@app.route('/api/upload-artifact', methods=['POST'])
def upload_artifact():
    """Upload an artifact and process it across all active branches."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json
    artifact_name = data.get('artifact_name', 'Unknown Artifact')
    artifact_content = data.get('artifact_content', '')
    branch_ids = data.get('branch_ids', None)  # Optional: specific branches to evaluate
    
    if not artifact_content:
        return jsonify({'error': 'Artifact content is required'}), 400
    
    # Add artifact to engine (LLM evaluation is required)
    # This creates nodes in all active branches (or specified branches)
    try:
        new_nodes = engine.add_artifact(artifact_name, artifact_content, branch_ids=branch_ids)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # Prune low-confidence hypotheses (branches)
    engine.prune_hypotheses()
    
    # Get next requests (LLM is required)
    try:
        next_requests = engine.get_next_requests()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # Check if complete
    is_complete = engine.is_complete()
    
    # Build response with all branches
    root_node = engine.get_current_node()
    
    return jsonify({
        'success': True,
        'nodes_created': len(new_nodes),
        'branches': [
            {
                'hypothesis_id': node.hypothesis_id,
                'node_id': node.id,
                'step_number': node.step_number,
                'hypothesis': {
                    'id': node.hypothesis.id if node.hypothesis else None,
                    'description': node.hypothesis.description if node.hypothesis else None,
                    'category': node.hypothesis.category if node.hypothesis else None,
                    'confidence': node.hypothesis.confidence if node.hypothesis else 0.0,
                    'status': node.hypothesis.status if node.hypothesis else 'unknown',
                    'evidence': node.hypothesis.evidence if node.hypothesis else []
                },
                'artifacts_received': [
                    {
                        'name': art['name'],
                        'timestamp': art['timestamp']
                    }
                    for art in node.artifacts_received
                ]
            }
            for node in new_nodes
        ],
        'all_hypotheses': [
            {
                'id': h.id,
                'description': h.description,
                'category': h.category,
                'confidence': h.confidence,
                'status': h.status,
                'evidence': h.evidence
            }
            for h in root_node.hypotheses
        ] if root_node else [],
        'requested_data': next_requests,
        'tree_summary': engine.get_tree_summary(),
        'is_complete': is_complete,
        'next_requests': next_requests
    })

@app.route('/api/current-node', methods=['GET'])
def get_current_node():
    """Get the current reasoning node."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    node = engine.get_current_node()
    if not node:
        return jsonify({'error': 'No current node'}), 404
    
    return jsonify({
        'node': {
            'id': node.id,
            'step_number': node.step_number,
            'hypotheses': [
                {
                    'id': h.id,
                    'description': h.description,
                    'category': h.category,
                    'confidence': h.confidence,
                    'status': h.status,
                    'evidence': h.evidence
                }
                for h in node.hypotheses
            ],
            'requested_data': node.requested_data,
            'artifacts_received': [
                {
                    'name': art['name'],
                    'timestamp': art['timestamp']
                }
                for art in node.artifacts_received
            ]
        },
        'tree_summary': engine.get_tree_summary()
    })

@app.route('/api/backtrack', methods=['POST'])
def backtrack():
    """Backtrack to a previous node or focus on a specific branch."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json
    node_id = data.get('node_id')
    hypothesis_id = data.get('hypothesis_id')
    
    if not node_id and not hypothesis_id:
        return jsonify({'error': 'Either node_id or hypothesis_id is required'}), 400
    
    try:
        node = engine.backtrack(node_id=node_id, hypothesis_id=hypothesis_id)
        
        # Get branch information if hypothesis_id was provided
        branch_info = None
        if hypothesis_id:
            branch_path = engine.get_branch_path(hypothesis_id)
            branch_info = {
                'hypothesis_id': hypothesis_id,
                'path_length': len(branch_path),
                'leaf_node_id': branch_path[-1].id if branch_path else None
            }
        
        return jsonify({
            'success': True,
            'node': {
                'id': node.id,
                'step_number': node.step_number,
                'hypothesis_id': node.hypothesis_id,
                'hypothesis': {
                    'id': node.hypothesis.id if node.hypothesis else None,
                    'description': node.hypothesis.description if node.hypothesis else None,
                    'category': node.hypothesis.category if node.hypothesis else None,
                    'confidence': node.hypothesis.confidence if node.hypothesis else 0.0,
                    'status': node.hypothesis.status if node.hypothesis else 'unknown'
                } if node.hypothesis else None,
                'hypotheses': [
                    {
                        'id': h.id,
                        'description': h.description,
                        'category': h.category,
                        'confidence': h.confidence,
                        'status': h.status
                    }
                    for h in node.hypotheses
                ] if hasattr(node, 'hypotheses') and node.hypotheses else []
            },
            'branch_info': branch_info,
            'current_branch_ids': engine.current_branch_ids
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/final-analysis', methods=['GET'])
def get_final_analysis():
    """Get final root cause analysis."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    # Final analysis is now LLM-driven within engine.get_final_analysis()
    try:
        engine_analysis = engine.get_final_analysis()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    return jsonify({
        'analysis': engine_analysis,
        'raw_llm_analysis': engine_analysis.get('raw_llm_analysis', ''),
        'tree_summary': engine.get_tree_summary()
    })

@app.route('/api/tree-summary', methods=['GET'])
def get_tree_summary():
    """Get summary of the reasoning tree."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    return jsonify(engine.get_tree_summary())

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get full history of reasoning nodes with detailed information (branch-based)."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    return jsonify({
        'nodes': [
            {
                'id': node.id,
                'step_number': node.step_number,
                'hypothesis_id': node.hypothesis_id,
                'parent_id': node.parent_id,
                'children_ids': node.children_ids,
                'branch_status': node.branch_status,
                'hypothesis': {
                    'id': node.hypothesis.id if node.hypothesis else None,
                    'description': node.hypothesis.description if node.hypothesis else None,
                    'category': node.hypothesis.category if node.hypothesis else None,
                    'confidence': node.hypothesis.confidence if node.hypothesis else 0.0,
                    'status': node.hypothesis.status if node.hypothesis else 'unknown'
                } if node.hypothesis else None,
                'hypotheses_count': len(node.hypotheses) if hasattr(node, 'hypotheses') and node.hypotheses else 0,
                'active_hypotheses_count': len([h for h in node.hypotheses if h.status == "active"]) if hasattr(node, 'hypotheses') and node.hypotheses else 0,
                'artifacts_count': len(node.artifacts_received),
                'artifacts': [{'name': art['name'], 'timestamp': art['timestamp']} for art in node.artifacts_received],
                'confidence': node.hypothesis.confidence if node.hypothesis else 0.0,
                'timestamp': node.timestamp.isoformat() if isinstance(node.timestamp, datetime) else str(node.timestamp)
            }
            for node in engine.nodes
        ],
        'root_node_id': engine.root_node_id,
        'current_branch_ids': engine.current_branch_ids
    })

@app.route('/api/auto-backtrack', methods=['POST'])
def auto_backtrack():
    """Auto-backtrack based on detection logic. Returns recommendation or executes backtrack."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json or {}
    execute = data.get('execute', False)  # If True, actually backtrack; if False, just return recommendation
    
    try:
        recommendation = engine.should_auto_backtrack()
        
        if not recommendation:
            return jsonify({
                'should_backtrack': False,
                'message': 'No backtrack recommendation. Current path looks good.'
            })
        
        if execute:
            # Actually perform the backtrack
            # Check if recommendation has hypothesis_id (branch-based) or node_id (legacy)
            if 'recommended_hypothesis_id' in recommendation:
                node = engine.backtrack(hypothesis_id=recommendation['recommended_hypothesis_id'])
            elif 'recommended_node_id' in recommendation:
                node = engine.backtrack(node_id=recommendation['recommended_node_id'])
            else:
                return jsonify({'error': 'Invalid recommendation format'}), 400
                
            return jsonify({
                'should_backtrack': True,
                'executed': True,
                'reason': recommendation['reason'],
                'message': recommendation['message'],
                'backtracked_to': {
                    'node_id': node.id,
                    'step_number': node.step_number,
                    'hypothesis_id': node.hypothesis_id
                },
                'recommendation': recommendation
            })
        else:
            # Just return the recommendation
            return jsonify({
                'should_backtrack': True,
                'executed': False,
                'reason': recommendation['reason'],
                'message': recommendation['message'],
                'recommendation': recommendation
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/branches', methods=['GET'])
def get_all_branches():
    """Get all branches (active and pruned) for UI display using pre-order traversal."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    try:
        branches = engine.get_all_branches_for_ui()
        return jsonify({
            'branches': branches,
            'active_count': len([b for b in branches if b['status'] == 'active']),
            'pruned_count': len([b for b in branches if b['status'] == 'pruned']),
            'accepted_count': len([b for b in branches if b['status'] == 'accepted'])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/prune-branch', methods=['POST'])
def prune_branch():
    """Prune a specific branch (mark as pruned but keep in memory)."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json
    hypothesis_id = data.get('hypothesis_id')
    
    if not hypothesis_id:
        return jsonify({'error': 'hypothesis_id is required'}), 400
    
    try:
        engine.prune_branch(hypothesis_id)
        return jsonify({
            'success': True,
            'message': f'Branch {hypothesis_id} pruned successfully',
            'hypothesis_id': hypothesis_id,
            'tree_summary': engine.get_tree_summary()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/unprune-branch', methods=['POST'])
def unprune_branch():
    """Unprune a branch (restore it to active status)."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json
    hypothesis_id = data.get('hypothesis_id')
    
    if not hypothesis_id:
        return jsonify({'error': 'hypothesis_id is required'}), 400
    
    try:
        engine.unprune_branch(hypothesis_id)
        return jsonify({
            'success': True,
            'message': f'Branch {hypothesis_id} restored to active',
            'hypothesis_id': hypothesis_id,
            'tree_summary': engine.get_tree_summary()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset', methods=['POST'])
def reset_session():
    """Reset the debugging session - clears all tree content."""
    global engine
    
    # Clear the engine completely
    engine = None
    
    return jsonify({
        'success': True,
        'message': 'Session reset successfully. Ready for a new issue.'
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)

