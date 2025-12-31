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
import httpx

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Initialize global instances
engine: Optional[TreeOfThoughtEngine] = None
# LLM integration will be created per-session with selected provider/model
llm_integration: Optional[LLMIntegration] = None

@app.route('/')
def index():
    """Serve the main application page."""
    # Check if React build exists, otherwise serve old template
    if os.path.exists('static/index.html'):
        return send_from_directory('static', 'index.html')
    else:
        return render_template('index.html')

@app.route('/api/detect-local-llm', methods=['GET'])
def detect_local_llm():
    """
    Auto-detect if a local Ollama instance is running.
    Returns available models if detected, or null if not available.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    base_url = request.args.get('base_url', 'http://localhost:11434')
    timeout = float(request.args.get('timeout', 2.0))
    
    try:
        # Try to ping Ollama API
        ollama_url = f"{base_url}/api/tags"
        logger.info(f"Attempting to detect Ollama at {ollama_url} with timeout {timeout}s")
        
        with httpx.Client(timeout=timeout) as client:
            response = client.get(ollama_url)
            logger.info(f"Ollama response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Ollama response data: {data}")
                models = [model.get('name', '') for model in data.get('models', [])]
                models = [m for m in models if m]  # Filter out empty names
                logger.info(f"Parsed models: {models}")
                
                return jsonify({
                    'available': True,
                    'models': models,
                    'base_url': base_url
                })
            else:
                error_msg = f'Ollama returned status {response.status_code}'
                logger.warning(error_msg)
                return jsonify({
                    'available': False,
                    'error': error_msg
                })
                
    except httpx.TimeoutException as e:
        error_msg = f'Connection timeout after {timeout}s - Ollama not running or unreachable at {base_url}'
        logger.warning(error_msg)
        return jsonify({
            'available': False,
            'error': error_msg
        })
    except httpx.ConnectError as e:
        error_msg = f'Connection refused - Ollama not running at {base_url}'
        logger.warning(error_msg)
        return jsonify({
            'available': False,
            'error': error_msg
        })
    except Exception as e:
        error_msg = f'Unexpected error: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return jsonify({
            'available': False,
            'error': error_msg
        })

@app.route('/api/initialize', methods=['POST'])
def initialize():
    """Initialize the ToT engine with a problem statement."""
    global engine, llm_integration
    
    data = request.json
    problem_summary = data.get('problem_summary', '')
    
    if not problem_summary:
        return jsonify({'error': 'Problem summary is required'}), 400
    
    # Get provider and model from request (optional)
    provider = data.get('provider', None)  # 'openai', 'groq', 'ollama'
    model = data.get('model', None)  # Model name
    base_url = data.get('base_url', None)  # For Ollama, custom base URL
    use_fallback = data.get('use_hardcoded_fallback', False)
    
    # Create LLM integration with selected provider/model
    try:
        llm_kwargs = {}
        if provider:
            llm_kwargs['provider'] = provider
        if model:
            llm_kwargs['model'] = model
        if base_url and provider == 'ollama':
            llm_kwargs['base_url'] = base_url
        
        llm_integration = LLMIntegration(require_llm=not use_fallback, **llm_kwargs)
    except Exception as e:
        return jsonify({'error': f'Failed to initialize LLM: {str(e)}'}), 400
    
    # Initialize engine with LLM integration
    engine = TreeOfThoughtEngine(llm_integration=llm_integration)
    initial_node = engine.initialize(problem_summary, use_hardcoded_fallback=use_fallback)
    
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
    
    # Determine which branches were evaluated for pruning
    # If specific branches were evaluated (either via branch_ids or focused mode), only prune those.
    # Otherwise, prune all active branches.
    evaluated_branch_ids = None
    if branch_ids is not None:
        # User selected specific branches - extract the hypothesis IDs from the nodes that were actually created
        evaluated_branch_ids = [node.hypothesis_id for node in new_nodes if node.hypothesis_id]
    elif engine.current_branch_ids:
        # Focused mode (from backtrack) - only prune the focused branches
        evaluated_branch_ids = [node.hypothesis_id for node in new_nodes if node.hypothesis_id]
    # If branch_ids was None and current_branch_ids is empty, evaluated_branch_ids stays None, 
    # meaning prune all active branches
    
    # Prune low-confidence hypotheses (branches)
    # Only prune branches that were just evaluated (if specific branches were selected)
    engine.prune_hypotheses(evaluated_branch_ids=evaluated_branch_ids)
    
    # Get next requests (LLM is required)
    try:
        next_requests = engine.get_next_requests()
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # Check if complete
    is_complete = engine.is_complete()
    
    # Build response with all branches
    # Get ALL hypotheses by traversing the tree (not just root)
    all_hypotheses = engine.get_all_hypotheses_from_tree()
    
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
            for h in all_hypotheses
        ],
        'requested_data': next_requests,
        'tree_summary': engine.get_tree_summary(),
        'is_complete': is_complete,
        'next_requests': next_requests,
        'current_branch_ids': engine.current_branch_ids,
        'is_focused': len(engine.current_branch_ids) > 0
    })

@app.route('/api/check-session', methods=['GET'])
def check_session():
    """Check if an active session exists."""
    global engine
    return jsonify({
        'has_session': engine is not None and engine.root_node_id is not None
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
    
    # Get ALL hypotheses by traversing the tree (not just root)
    all_hypotheses = engine.get_all_hypotheses_from_tree()
    
    # Get all branches for branch selection UI
    branches = engine.get_all_branches_for_ui()
    
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
        'all_hypotheses': [
            {
                'id': h.id,
                'description': h.description,
                'category': h.category,
                'confidence': h.confidence,
                'status': h.status,
                'evidence': h.evidence
            }
            for h in all_hypotheses
        ],
        'branches': branches,  # Add branches for branch selection
        'tree_summary': engine.get_tree_summary(),
        'current_branch_ids': engine.current_branch_ids,
        'is_focused': len(engine.current_branch_ids) > 0,
        'step_number': node.step_number,
        'current_node_id': engine.current_node_id,
        'root_node_id': engine.root_node_id
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
        auto_restore = data.get('auto_restore', True)  # Default to True
        node, was_restored = engine.backtrack(node_id=node_id, hypothesis_id=hypothesis_id, auto_restore=auto_restore)
        
        # Get branch information if hypothesis_id was provided
        branch_info = None
        if hypothesis_id:
            branch_path = engine.get_branch_path(hypothesis_id)
            branch_info = {
                'hypothesis_id': hypothesis_id,
                'path_length': len(branch_path),
                'leaf_node_id': branch_path[-1].id if branch_path else None
            }
        
        # Get updated hypothesis status after potential restoration
        root_node = engine._get_node(engine.root_node_id) if engine.root_node_id else None
        restored_hypothesis = None
        if was_restored and node.hypothesis_id and root_node:
            hyp = next((h for h in root_node.hypotheses if h.id == node.hypothesis_id), None)
            if hyp:
                restored_hypothesis = {
                    'id': hyp.id,
                    'description': hyp.description,
                    'status': hyp.status,
                    'confidence': hyp.confidence
                }
        
        # Get ALL hypotheses and branches for UI update
        all_hypotheses = engine.get_all_hypotheses_from_tree()
        branches = engine.get_all_branches_for_ui()
        
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
            'all_hypotheses': [
                {
                    'id': h.id,
                    'description': h.description,
                    'category': h.category,
                    'confidence': h.confidence,
                    'status': h.status,
                    'evidence': h.evidence
                }
                for h in all_hypotheses
            ],
            'branches': branches,
            'branch_info': branch_info,
            'current_branch_ids': engine.current_branch_ids,
            'is_focused': len(engine.current_branch_ids) > 0,
            'was_restored': was_restored,
            'restored_hypothesis': restored_hypothesis,
            'tree_summary': engine.get_tree_summary(),
            'step_number': node.step_number,
            'current_node_id': engine.current_node_id,
            'root_node_id': engine.root_node_id
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
                'timestamp': node.timestamp.isoformat() if isinstance(node.timestamp, datetime) else str(node.timestamp),
                'evaluation_details': node.evaluation_details if hasattr(node, 'evaluation_details') and node.evaluation_details else None,
                'pruning_details': node.pruning_details if hasattr(node, 'pruning_details') and node.pruning_details else None
            }
            for node in engine.nodes
        ],
        'root_node_id': engine.root_node_id,
        'current_node_id': engine.current_node_id,  # Return current node ID
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
            recommended_hyp_id = recommendation.get('recommended_hypothesis_id')
            recommended_node_id = recommendation.get('recommended_node_id')
            
            if recommended_hyp_id is not None:
                # Valid hypothesis ID provided
                node = engine.backtrack(hypothesis_id=recommended_hyp_id)
            elif recommended_node_id is not None:
                # Valid node ID provided
                node = engine.backtrack(node_id=recommended_node_id)
            else:
                # No valid backtrack target (e.g., all hypotheses pruned)
                return jsonify({
                    'error': recommendation.get('message', 'Cannot backtrack: No valid target available. All hypotheses may be pruned.'),
                    'reason': recommendation.get('reason', 'dead_end'),
                    'should_backtrack': True,
                    'executed': False
                }), 400
                
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

@app.route('/api/focus-branch', methods=['POST'])
def focus_branch():
    """Focus on a specific branch for future artifact evaluation."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json
    hypothesis_id = data.get('hypothesis_id')
    
    if not hypothesis_id:
        return jsonify({'error': 'hypothesis_id is required'}), 400
    
    try:
        # Set current_branch_ids to focus on this hypothesis
        engine.current_branch_ids = [hypothesis_id]
        
        # Get all hypotheses to return updated state
        all_hypotheses = engine.get_all_hypotheses_from_tree()
        branches = engine.get_all_branches_for_ui()
        
        return jsonify({
            'success': True,
            'message': f'Focused on branch {hypothesis_id}. Future artifacts will only evaluate this branch.',
            'current_branch_ids': engine.current_branch_ids,
            'is_focused': True,
            'all_hypotheses': [
                {
                    'id': h.id,
                    'description': h.description,
                    'category': h.category,
                    'confidence': h.confidence,
                    'status': h.status,
                    'evidence': h.evidence
                }
                for h in all_hypotheses
            ],
            'branches': branches
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/unfocus', methods=['POST'])
def unfocus():
    """Clear branch focus and return to evaluating all active branches."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    try:
        engine.unfocus()
        return jsonify({
            'success': True,
            'message': 'Focus cleared. Future artifacts will evaluate all active branches.',
            'current_branch_ids': [],
            'is_focused': False
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-node', methods=['POST'])
def generate_node():
    """Expand a node by generating new sub-hypotheses or exploration directions."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json
    node_id = data.get('node_id')
    
    if not node_id:
        return jsonify({'error': 'node_id is required'}), 400
    
    try:
        new_nodes = engine.expand_node(node_id)
        
        # Get ALL hypotheses by traversing the tree (includes new ones from parent node)
        all_hypotheses = engine.get_all_hypotheses_from_tree()
        branches = engine.get_all_branches_for_ui()
        
        return jsonify({
            'success': True,
            'nodes_created': len(new_nodes),
            'new_nodes': [
                {
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
                    'parent_id': node.parent_id
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
                for h in all_hypotheses
            ],
            'branches': branches,
            'message': f'Generated {len(new_nodes)} new exploration directions from node {node_id}'
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
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

@app.route('/api/node-evaluation-details/<node_id>', methods=['GET'])
def get_node_evaluation_details(node_id):
    """Get evaluation and pruning details for a specific node."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    try:
        node = engine._get_node(node_id)
        
        return jsonify({
            'node_id': node_id,
            'evaluation_details': node.evaluation_details if hasattr(node, 'evaluation_details') and node.evaluation_details else None,
            'pruning_details': node.pruning_details if hasattr(node, 'pruning_details') and node.pruning_details else None,
            'has_evaluation': hasattr(node, 'evaluation_details') and node.evaluation_details is not None,
            'has_pruning': hasattr(node, 'pruning_details') and node.pruning_details is not None
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
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
        
        # Get updated state after unpruning
        all_hypotheses = engine.get_all_hypotheses_from_tree()
        branches = engine.get_all_branches_for_ui()
        node = engine.get_current_node()
        
        return jsonify({
            'success': True,
            'message': f'Branch {hypothesis_id} restored to active',
            'hypothesis_id': hypothesis_id,
            'all_hypotheses': [
                {
                    'id': h.id,
                    'description': h.description,
                    'category': h.category,
                    'confidence': h.confidence,
                    'status': h.status,
                    'evidence': h.evidence
                }
                for h in all_hypotheses
            ],
            'branches': branches,
            'tree_summary': engine.get_tree_summary(),
            'current_branch_ids': engine.current_branch_ids,
            'is_focused': len(engine.current_branch_ids) > 0,
            'step_number': node.step_number if node else None,
            'current_node_id': engine.current_node_id,
            'root_node_id': engine.root_node_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset', methods=['POST'])
def reset_session():
    """Reset the debugging session - clears all tree content."""
    global engine, llm_integration
    
    # Clear the engine and LLM integration completely
    engine = None
    llm_integration = None
    
    return jsonify({
        'success': True,
        'message': 'Session reset successfully. Ready for a new issue.'
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)

