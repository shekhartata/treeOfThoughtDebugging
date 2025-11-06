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
    """Upload an artifact and process it."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json
    artifact_name = data.get('artifact_name', 'Unknown Artifact')
    artifact_content = data.get('artifact_content', '')
    
    if not artifact_content:
        return jsonify({'error': 'Artifact content is required'}), 400
    
    # Add artifact to engine (LLM evaluation is required)
    try:
        new_node = engine.add_artifact(artifact_name, artifact_content)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # Prune low-confidence hypotheses
    engine.prune_hypotheses()
    
    # Get next requests (LLM is required)
    try:
        next_requests = engine.get_next_requests(new_node)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # Check if complete
    is_complete = engine.is_complete()
    
    return jsonify({
        'success': True,
        'node': {
            'id': new_node.id,
            'step_number': new_node.step_number,
            'hypotheses': [
                {
                    'id': h.id,
                    'description': h.description,
                    'category': h.category,
                    'confidence': h.confidence,
                    'status': h.status,
                    'evidence': h.evidence
                }
                for h in new_node.hypotheses
            ],
            'requested_data': next_requests,
            'artifacts_received': [
                {
                    'name': art['name'],
                    'timestamp': art['timestamp']
                }
                for art in new_node.artifacts_received
            ]
        },
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
    """Backtrack to a previous node."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    data = request.json
    node_id = data.get('node_id')
    
    if not node_id:
        return jsonify({'error': 'Node ID is required'}), 400
    
    try:
        node = engine.backtrack(node_id)
        return jsonify({
            'success': True,
            'node': {
                'id': node.id,
                'step_number': node.step_number,
                'hypotheses': [
                    {
                        'id': h.id,
                        'description': h.description,
                        'category': h.category,
                        'confidence': h.confidence,
                        'status': h.status
                    }
                    for h in node.hypotheses
                ]
            }
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
    """Get full history of reasoning nodes."""
    global engine
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    return jsonify({
        'nodes': [
            {
                'id': node.id,
                'step_number': node.step_number,
                'parent_id': node.parent_id,
                'children_ids': node.children_ids,
                'hypotheses_count': len(node.hypotheses),
                'artifacts_count': len(node.artifacts_received),
                'timestamp': node.timestamp.isoformat()
            }
            for node in engine.nodes
        ]
    })

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

