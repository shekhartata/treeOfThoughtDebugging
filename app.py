"""
Flask Web Application for MongoDB Tree-of-Thought Debugging Tool
Provides interactive web interface for Consulting Engineers.
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from tot_engine import TreeOfThoughtEngine, ReasoningNode
from llm_integration import LLMIntegration
from session_manager import SessionManager
from auth import AuthManager, AuthError
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict
from dotenv import load_dotenv
import httpx
import uuid
import gzip
import secrets

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Initialize session manager and auth
session_manager = SessionManager()
auth_manager = AuthManager(session_manager.db)


def get_current_user():
    """Return current user dict from Authorization Bearer token, or None."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None
    payload = auth_manager.verify_token(token)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return auth_manager.get_user_by_id(user_id)


def get_board_token_from_request():
    """Return board share token from header X-Board-Token or query access_token."""
    # Header is case-insensitive in HTTP; try common casings for proxies/clients
    token = (
        request.headers.get("X-Board-Token")
        or request.headers.get("x-board-token")
        or request.args.get("access_token")
    )
    return (token or "").strip() or None


def can_access_board(session_id: str) -> bool:
    """Return True if request is allowed to access this board (owner, shared_with, or valid share token)."""
    session_doc = session_manager.sessions.find_one({"_id": session_id})
    if not session_doc:
        return False
    user = get_current_user()
    owner_id = session_doc.get("owner_id")
    shared_ids = [str(x) for x in (session_doc.get("shared_with") or [])]
    user_id = str((user or {}).get("id") or "")
    board_token = get_board_token_from_request()

    # Valid share token always grants access (owner or collaborator who joined via link)
    if board_token and session_doc.get("share_token") == board_token:
        return True

    # Sessions with owner_id: only owner or users in shared_with
    if owner_id is not None:
        if user and str(owner_id) == user_id:
            return True
        if user and user_id in shared_ids:
            return True
        return False

    # Legacy sessions (no owner_id): only allow with valid board token (no open access)
    return False


# In-memory session storage (session_id -> engine)
active_engines: Dict[str, TreeOfThoughtEngine] = {}
active_llm_integrations: Dict[str, LLMIntegration] = {}


def get_or_load_engine(session_id: str) -> Optional[TreeOfThoughtEngine]:
    """Get engine from memory, or load from MongoDB if not in memory."""
    import logging
    logger = logging.getLogger(__name__)
    
    # Check MongoDB first to see if session is finished (before loading from memory or MongoDB)
    session_doc = session_manager.sessions.find_one({'_id': session_id})
    if session_doc and session_doc.get('session_status') == 'finished':
        logger.info(f"Session {session_id} is finished, not loading")
        # Remove from memory if it exists
        if session_id in active_engines:
            del active_engines[session_id]
        if session_id in active_llm_integrations:
            del active_llm_integrations[session_id]
        return None
    
    # Always check memory first - this is the source of truth for active sessions
    if session_id in active_engines:
        engine = active_engines[session_id]
        # Verify engine has nodes
        if engine.nodes:
            logger.debug(f"Found session {session_id} in memory with {len(engine.nodes)} nodes")
            return engine
        else:
            logger.warning(f"Engine in memory for session {session_id} has no nodes. Root node ID: {engine.root_node_id}")
            # Even if no nodes, return the engine - it might be in a transitional state
            # The API will handle the error gracefully
            return engine
    
    # Load from MongoDB only if not in memory
    session_data = session_manager.load_session(session_id)
    if not session_data:
        return None
    
    # Check if session is finished (double check)
    if session_data.get("session_status") == "finished":
        return None
    
    # Load nodes
    nodes_data = session_manager.load_nodes(session_id)
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Loaded {len(nodes_data)} nodes from MongoDB for session {session_id}")
    if not nodes_data:
        logger.warning(f"No nodes found in MongoDB for session {session_id}. This session may not have been saved properly.")
        # Return None instead of empty engine - let the API handle the error
        return None
    
    # Recreate LLM integration
    metadata = session_data.get("metadata", {})
    llm_provider = metadata.get("llm_provider")
    llm_model = metadata.get("llm_model")
    
    llm_integration = None
    if llm_provider and llm_provider != "unknown":
        try:
            llm_integration = LLMIntegration(provider=llm_provider, model=llm_model)
        except Exception as e:
            logger.warning(f"Failed to recreate LLM integration: {e}")
    
    # Reconstruct engine
    engine = TreeOfThoughtEngine.from_normalized(session_data, nodes_data, llm_integration)
    
    # Verify nodes were reconstructed
    if not engine.nodes:
        logger.error(f"Failed to reconstruct nodes for session {session_id}. nodes_data had {len(nodes_data)} items.")
        return None
    
    # Cache in memory
    active_engines[session_id] = engine
    if llm_integration:
        active_llm_integrations[session_id] = llm_integration
    
    return engine


def get_engine_from_request():
    """Helper to get engine from request (supports both query param and JSON body)."""
    # For GET requests, only check query params
    # For POST/PUT requests, check JSON body first, then query params
    session_id = None
    if request.method == 'GET':
        session_id = request.args.get('session_id')
    else:
        # For POST/PUT, try JSON body first, then query params
        try:
            if request.is_json and request.json:
                session_id = request.json.get('session_id')
        except:
            pass
        if not session_id:
            session_id = request.args.get('session_id')
    
    # If no session_id but client sent board share token (e.g. collaborator from share link),
    # resolve session_id from the token so the client does not need to send session_id.
    if not session_id:
        board_token = get_board_token_from_request()
        if board_token:
            session_doc = session_manager.sessions.find_one({'share_token': board_token})
            if session_doc:
                session_id = session_doc['_id']
    
    if not session_id:
        logging.getLogger(__name__).warning(
            "session_id missing: not in %s params/body and could not resolve from X-Board-Token",
            request.path,
        )
        return None, None, ({'error': 'session_id is required'}, 400)
    
    if not can_access_board(session_id):
        return None, session_id, ({'error': 'Access denied to this board'}, 403)
    
    engine = get_or_load_engine(session_id)
    if not engine:
        return None, session_id, ({'error': 'Session not found or finished'}, 404)
    
    return engine, session_id, None

@app.route('/')
def index():
    """Serve the main application page."""
    # Check if React build exists, otherwise serve old template
    if os.path.exists('static/index.html'):
        return send_from_directory('static', 'index.html')
    else:
        return render_template('index.html')


# ==================== Auth Endpoints ====================

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """Register a new user. Returns user and token."""
    data = request.json or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    name = (data.get('name') or '').strip() or None
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    if not password:
        return jsonify({'error': 'Password is required'}), 400
    try:
        user = auth_manager.register(email, password, name)
        token = auth_manager.create_token(user['id'], user['email'])
        return jsonify({'user': user, 'token': token})
    except AuthError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """Login with email and password. Returns user and token."""
    data = request.json or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    if not email:
        return jsonify({'error': 'Email is required'}), 400
    if not password:
        return jsonify({'error': 'Password is required'}), 400
    try:
        result = auth_manager.login(email, password)
        return jsonify(result)
    except AuthError as e:
        return jsonify({'error': str(e)}), 401


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """Return current user from JWT. Requires Authorization: Bearer <token>."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify({'user': user})


@app.route('/api/users/search', methods=['GET'])
def search_users():
    """Search users by name or email (enterprise members). Auth required."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    users = auth_manager.search_users(q, limit=limit)
    return jsonify({'users': users})


@app.route('/api/join', methods=['GET'])
def join_board():
    """Join a board with a share token. Requires login; user must be owner or in shared_with."""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Sign in required to open this shared board'}), 401
    token = request.args.get('token', '').strip()
    if not token:
        return jsonify({'error': 'Token is required'}), 400
    session_doc = session_manager.sessions.find_one({'share_token': token})
    if not session_doc:
        return jsonify({'error': 'Invalid or expired token'}), 404
    if session_doc.get('session_status') == 'finished':
        return jsonify({'error': 'This board is closed'}), 400
    owner_id = session_doc.get('owner_id')
    shared_with = [str(x) for x in (session_doc.get('shared_with') or [])]
    user_id = str(user.get('id') or '')
    # Legacy sessions (no owner_id): any logged-in user with token can join
    if owner_id is None:
        pass  # allow
    elif str(owner_id) == user_id:
        pass  # owner
    elif user_id in shared_with:
        pass  # shared with this user
    else:
        return jsonify({'error': 'You do not have access to this board. It was shared with specific people only.'}), 403
    return jsonify({
        'session_id': session_doc['_id'],
        'problem_summary': session_doc.get('problem_summary', ''),
        'share_token': token,
    })


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
    data = request.json
    problem_summary = data.get('problem_summary', '')
    
    if not problem_summary:
        return jsonify({'error': 'Problem summary is required'}), 400
    
    # Generate new session ID
    session_id = str(uuid.uuid4())
    
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
    
    # Store in memory
    active_engines[session_id] = engine
    active_llm_integrations[session_id] = llm_integration
    
    # Owner for board access (logged-in user who creates the session)
    owner_id = (get_current_user() or {}).get('id')
    
    # Auto-save after initialization to ensure nodes are persisted (non-blocking)
    import threading
    def auto_save_async():
        try:
            # Small delay to ensure engine is fully initialized
            import time
            time.sleep(0.1)
            
            llm_provider = llm_integration.provider_name if llm_integration else None
            llm_model = llm_integration.model_name if llm_integration else None
            session_data, nodes_data = engine.to_dict_for_db(session_id, llm_provider, llm_model)
            if owner_id:
                session_data['owner_id'] = owner_id
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Auto-saving session {session_id}: {len(engine.nodes)} nodes in engine, {len(nodes_data)} nodes to save")
            
            if not nodes_data:
                logger.error(f"WARNING: No nodes to save for session {session_id}! Engine has {len(engine.nodes)} nodes.")
                return
            
            session_manager.save_session(session_id, session_data, nodes_data)
            logger.info(f"Auto-saved session {session_id} after initialization with {len(nodes_data)} nodes")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to auto-save session after initialization: {e}", exc_info=True)
    
    # Start auto-save in background thread (non-blocking)
    save_thread = threading.Thread(target=auto_save_async, daemon=True)
    save_thread.start()
    
    is_owner = bool(owner_id)
    return jsonify({
        'success': True,
        'session_id': session_id,
        'is_owner': is_owner,
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
    data = request.json
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'session_id is required'}), 400
    
    engine = get_or_load_engine(session_id)
    if not engine:
        return jsonify({'error': 'Session not found or finished'}), 404
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

# ==================== Session Management Endpoints ====================

@app.route('/api/sessions/unfinished', methods=['GET'])
def list_unfinished_sessions():
    """List all active (unfinished) sessions."""
    sessions = session_manager.list_unfinished_sessions()
    return jsonify({"sessions": sessions})


@app.route('/api/sessions/<session_id>/load', methods=['GET'])
def load_session(session_id: str):
    """Load an existing session (resume debugging). Requires owner or valid share token."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        if not can_access_board(session_id):
            return jsonify({"error": "Access denied to this board"}), 403
        # First check if session exists in MongoDB
        session_data = session_manager.load_session(session_id)
        if not session_data:
            return jsonify({"error": "Session not found"}), 404
        
        if session_data.get("session_status") == "finished":
            return jsonify({
                "error": "Session is finished. Cannot resume finished sessions.",
                "session_status": "finished"
            }), 400
        
        # Try to load engine (from memory or MongoDB)
        engine = get_or_load_engine(session_id)
        if not engine:
            return jsonify({
                "error": "Failed to load session engine. The session may be corrupted or nodes may not have been saved.",
                "session_id": session_id
            }), 500
        
        # Check if engine has nodes
        if not engine.nodes:
            logger.warning(f"Engine loaded for session {session_id} but has no nodes")
            return jsonify({
                "error": "Session loaded but has no nodes. The session may not have been saved properly.",
                "session_id": session_id,
                "suggestion": "Please initialize a new session."
            }), 500
        
        # Get tree summary safely
        try:
            tree_summary = engine.get_tree_summary()
        except Exception as e:
            logger.error(f"Error getting tree summary: {e}", exc_info=True)
            tree_summary = {
                "total_nodes": len(engine.nodes),
                "current_step": engine.step_counter,
                "problem_summary": engine.problem_summary,
                "active_hypotheses": 0,
                "pruned_hypotheses": 0,
                "accepted_hypotheses": 0,
                "active_branches": 0
            }
        
        user = get_current_user()
        owner_id = session_data.get("owner_id")
        user_id = str((user or {}).get("id") or "")
        is_owner = bool(
            user
            and (str(owner_id or "") == user_id or owner_id is None)
        )
        return jsonify({
            "success": True,
            "session_id": session_id,
            "is_owner": is_owner,
            "session": {
                "problem_summary": session_data.get("problem_summary"),
                "session_status": session_data.get("session_status"),
                "step_counter": session_data.get("step_counter"),
                "current_node_id": session_data.get("current_node_id"),
                "root_node_id": session_data.get("root_node_id")
            },
            "tree_summary": tree_summary
        })
    except Exception as e:
        logger.error(f"Error loading session {session_id}: {e}", exc_info=True)
        return jsonify({
            "error": f"Failed to load session: {str(e)}",
            "session_id": session_id
        }), 500


@app.route('/api/sessions/<session_id>/share-token', methods=['POST', 'GET'])
def share_token(session_id: str):
    """Get or create share token for the board. Owner only. Returns share_token and share_url."""
    session_doc = session_manager.sessions.find_one({'_id': session_id})
    if not session_doc:
        return jsonify({'error': 'Session not found'}), 404
    user = get_current_user()
    owner_id = session_doc.get('owner_id')
    user_id = str((user or {}).get('id') or '')
    is_owner = user and (str(owner_id or '') == user_id or owner_id is None)
    if not is_owner:
        return jsonify({'error': 'Only the board owner can share this board'}), 403
    share_token_value = session_doc.get('share_token')
    if not share_token_value:
        share_token_value = secrets.token_urlsafe(32)
        session_manager.sessions.update_one(
            {'_id': session_id},
            {'$set': {'share_token': share_token_value, 'updated_at': datetime.utcnow()}}
        )
    # Frontend will build URL; we give origin-agnostic path or full URL from request
    base = request.host_url.rstrip('/')
    share_url = f"{base}?token={share_token_value}"
    return jsonify({'share_token': share_token_value, 'share_url': share_url})


@app.route('/api/sessions/<session_id>/share-with', methods=['POST'])
def share_with_user(session_id: str):
    """Add a user to this board's shared_with list (owner only). Link can then be used by that user."""
    session_doc = session_manager.sessions.find_one({'_id': session_id})
    if not session_doc:
        return jsonify({'error': 'Session not found'}), 404
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    owner_id = session_doc.get('owner_id')
    user_id = str((user or {}).get('id') or '')
    is_owner = str(owner_id or '') == user_id or owner_id is None
    if not is_owner:
        return jsonify({'error': 'Only the board owner can share with others'}), 403
    data = request.json or {}
    target_user_id = (data.get('user_id') or '').strip()
    if not target_user_id:
        return jsonify({'error': 'user_id is required'}), 400
    # Ensure target user exists
    target = auth_manager.get_user_by_id(target_user_id)
    if not target:
        return jsonify({'error': 'User not found'}), 404
    target_user_id = str(target_user_id)
    shared_with = [str(x) for x in (session_doc.get('shared_with') or [])]
    if target_user_id not in shared_with:
        shared_with.append(target_user_id)
        session_manager.sessions.update_one(
            {'_id': session_id},
            {'$set': {'shared_with': shared_with, 'updated_at': datetime.utcnow()}}
        )
    return jsonify({
        'shared_with': shared_with,
        'added': {'id': target['id'], 'email': target['email'], 'name': target.get('name')}
    })


@app.route('/api/sessions/<session_id>/shared-with', methods=['GET'])
def get_shared_with(session_id: str):
    """List users this board is shared with (owner or shared users)."""
    if not can_access_board(session_id):
        return jsonify({'error': 'Access denied to this board'}), 403
    session_doc = session_manager.sessions.find_one({'_id': session_id})
    if not session_doc:
        return jsonify({'error': 'Session not found'}), 404
    shared_ids = session_doc.get('shared_with') or []
    users = []
    for uid in shared_ids:
        u = auth_manager.get_user_by_id(uid)
        if u:
            users.append({'id': u['id'], 'email': u['email'], 'name': u.get('name')})
    return jsonify({'shared_with': users})


@app.route('/api/sessions/<session_id>/save', methods=['POST'])
def save_session(session_id: str):
    """Save session to MongoDB (explicit save by user)."""
    if not can_access_board(session_id):
        return jsonify({'error': 'Access denied to this board'}), 403
    engine = get_or_load_engine(session_id)
    if not engine:
        return jsonify({"error": "Session not found"}), 404
    
    # Check if engine has nodes
    if not engine.nodes:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Engine for session {session_id} has no nodes. This might indicate a problem.")
        # If engine has no nodes but has root_node_id, this is a corrupted state
        if engine.root_node_id:
            logger.error(f"Session {session_id} has root_node_id ({engine.root_node_id}) but no nodes. Session may be corrupted.")
            return jsonify({
                "error": "Session has no nodes. Please initialize a new session.",
                "session_id": session_id
            }), 400
    
    # Get LLM provider/model info
    llm_integration = active_llm_integrations.get(session_id)
    llm_provider = llm_integration.provider_name if llm_integration else None
    llm_model = llm_integration.model_name if llm_integration else None
    
    # Convert to dict format
    session_data, nodes_data = engine.to_dict_for_db(session_id, llm_provider, llm_model)
    # Preserve owner_id and shared_with from existing session (don't overwrite with engine-only data)
    existing = session_manager.load_session(session_id)
    if existing:
        if existing.get("owner_id") is not None:
            session_data["owner_id"] = existing["owner_id"]
        if existing.get("shared_with") is not None:
            session_data["shared_with"] = existing["shared_with"]
        if existing.get("share_token") is not None:
            session_data["share_token"] = existing["share_token"]

    # Log for debugging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Saving session {session_id}: {len(engine.nodes)} nodes in engine, {len(nodes_data)} nodes in nodes_data")

    # Save to MongoDB
    try:
        session_manager.save_session(session_id, session_data, nodes_data)
        return jsonify({
            "success": True,
            "message": "Session saved successfully",
            "session_id": session_id,
            "nodes_saved": len(nodes_data),
            "nodes_in_engine": len(engine.nodes)
        })
    except Exception as e:
        logger.error(f"Error saving session: {e}", exc_info=True)
        return jsonify({"error": f"Failed to save session: {str(e)}"}), 500


@app.route('/api/sessions/<session_id>/status', methods=['GET'])
def get_session_status(session_id: str):
    """Check if session has unsaved changes."""
    if not can_access_board(session_id):
        return jsonify({'error': 'Access denied to this board'}), 403
    session = session_manager.load_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    
    has_unsaved_changes = (
        session.get("last_saved_at") is None or
        session.get("updated_at", datetime.utcnow()) > session.get("last_saved_at")
    )
    
    return jsonify({
        "session_id": session_id,
        "session_status": session.get("session_status"),
        "has_unsaved_changes": has_unsaved_changes,
        "last_saved_at": session.get("last_saved_at").isoformat() if session.get("last_saved_at") else None,
        "updated_at": session.get("updated_at").isoformat() if session.get("updated_at") else None
    })


@app.route('/api/check-session', methods=['GET'])
def check_session():
    """Check if an active (unfinished) session exists (backward compatibility)."""
    session_id = request.args.get('session_id')
    if session_id:
        if not can_access_board(session_id):
            return jsonify({'has_session': False, 'session_id': session_id})
        # First check if session exists and is not finished
        session_doc = session_manager.sessions.find_one({'_id': session_id})
        if session_doc and session_doc.get('session_status') == 'finished':
            return jsonify({
                'has_session': False,
                'session_id': session_id,
                'reason': 'Session is finished'
            })
        
        # If session exists and is active, try to load engine
        engine = get_or_load_engine(session_id)
        return jsonify({
            'has_session': engine is not None and engine.root_node_id is not None,
            'session_id': session_id
        })
    
    # If no session_id provided, check for any unfinished sessions this user can access
    unfinished = session_manager.list_unfinished_sessions()
    if unfinished:
        accessible = [s for s in unfinished if can_access_board(s.get('session_id') or '')]
        if accessible:
            most_recent = max(accessible, key=lambda s: s.get('created_at', ''))
            return jsonify({
                'has_session': True,
                'session_id': most_recent.get('session_id')
            })
    
    return jsonify({'has_session': False})

@app.route('/api/current-node', methods=['GET'])
def get_current_node():
    """Get the current reasoning node."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
    if not engine:
        # Check if session is finished
        if session_id:
            session_doc = session_manager.sessions.find_one({'_id': session_id})
            if session_doc and session_doc.get('session_status') == 'finished':
                return jsonify({
                    'error': 'Session is finished',
                    'session_status': 'finished',
                    'session_id': session_id
                }), 404
        return jsonify({'error': 'Engine not initialized'}), 404
    
    # Check if engine has nodes
    if not engine.nodes:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Engine for session {session_id} has no nodes. Root node ID: {engine.root_node_id}")
        
        # If this is a fresh session (just initialized), it might be in memory but not saved yet
        # Check if it's in active_engines (in-memory)
        if session_id in active_engines:
            in_memory_engine = active_engines[session_id]
            if in_memory_engine.nodes:
                logger.info(f"Found session {session_id} in memory with {len(in_memory_engine.nodes)} nodes. Using in-memory engine.")
                engine = in_memory_engine
            else:
                return jsonify({
                    'error': 'No nodes found in session. The session may not have been saved properly.',
                    'session_id': session_id,
                    'root_node_id': engine.root_node_id,
                    'suggestion': 'Please initialize a new session or check if the session was saved correctly.'
                }), 404
        else:
            return jsonify({
                'error': 'No nodes found in session. The session may not have been saved properly.',
                'session_id': session_id,
                'root_node_id': engine.root_node_id,
                'suggestion': 'Please initialize a new session or check if the session was saved correctly.'
            }), 404
    
    node = engine.get_current_node()
    if not node:
        return jsonify({
            'error': 'No current node found',
            'session_id': session_id,
            'root_node_id': engine.root_node_id,
            'nodes_count': len(engine.nodes)
        }), 404
    
    # Get ALL hypotheses by traversing the tree (not just root)
    all_hypotheses = engine.get_all_hypotheses_from_tree()
    
    # Get all branches for branch selection UI
    branches = engine.get_all_branches_for_ui()
    session_doc = session_manager.sessions.find_one({'_id': session_id})
    user = get_current_user()
    # Logged-in user is owner if they created the board, or if board has no owner (legacy)
    owner_id = session_doc.get('owner_id') if session_doc else None
    user_id = str((user or {}).get('id') or '')
    is_owner = bool(
        user
        and session_doc
        and (
            str(owner_id or '') == user_id
            or owner_id is None
        )
    )
    return jsonify({
        'is_owner': is_owner,
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
        'root_node_id': engine.root_node_id,
        'session_id': session_id
    })

@app.route('/api/backtrack', methods=['POST'])
def backtrack():
    """Backtrack to a previous node or focus on a specific branch."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
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
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    # Final analysis is now LLM-driven within engine.get_final_analysis()
    try:
        engine_analysis = engine.get_final_analysis()
        
        # Extract mitigation steps and compress them
        mitigation_text = engine_analysis.get('mitigation', '')
        mitigation_steps = []
        
        # Try to extract steps from mitigation text (could be a list or formatted text)
        if isinstance(mitigation_text, list):
            mitigation_steps = mitigation_text
        else:
            # Try to parse steps from text (look for numbered items, bullets, etc.)
            lines = mitigation_text.split('\n')
            for line in lines:
                line = line.strip()
                if line and (line.startswith('-') or line.startswith('•') or 
                            line[0].isdigit() or line.startswith('*')):
                    # Remove bullet/number prefix
                    step = line.lstrip('-•*0123456789. ').strip()
                    if step:
                        mitigation_steps.append(step)
            # If no steps found, use the whole text as one step
            if not mitigation_steps and mitigation_text:
                mitigation_steps = [mitigation_text]
        
        # Compress mitigation steps using gzip
        mitigation_json = json.dumps(mitigation_steps)
        compressed_mitigation = gzip.compress(mitigation_json.encode('utf-8'))
        
        # Save final_mitigation to database
        try:
            session_manager.sessions.update_one(
                {'_id': session_id},
                {'$set': {
                    'final_mitigation': compressed_mitigation,
                    'final_mitigation_updated_at': datetime.utcnow()
                }}
            )
        except Exception as e:
            logging.warning(f"Failed to save final_mitigation for session {session_id}: {str(e)}")
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    return jsonify({
        'analysis': engine_analysis,
        'raw_llm_analysis': engine_analysis.get('raw_llm_analysis', ''),
        'final_mitigation': mitigation_steps,  # Return uncompressed for frontend
        'tree_summary': engine.get_tree_summary()
    })

@app.route('/api/tree-summary', methods=['GET'])
def get_tree_summary():
    """Get summary of the reasoning tree."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[1]), error_response[1]
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    return jsonify(engine.get_tree_summary())

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get full history of reasoning nodes with detailed information (branch-based)."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
    if not engine:
        # Check if session is finished
        if session_id:
            session_doc = session_manager.sessions.find_one({'_id': session_id})
            if session_doc and session_doc.get('session_status') == 'finished':
                return jsonify({
                    'error': 'Session is finished',
                    'session_status': 'finished',
                    'nodes': [],
                    'session_id': session_id
                }), 404
        return jsonify({'error': 'Engine not initialized', 'nodes': []}), 404
    
    try:
        nodes_list = engine.nodes if engine.nodes else []
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
                for node in nodes_list
            ],
            'root_node_id': engine.root_node_id,
            'current_node_id': engine.current_node_id,  # Return current node ID
            'current_branch_ids': engine.current_branch_ids,
            'session_id': session_id
        })
    except Exception as e:
        logging.error(f"Error getting history for session {session_id}: {str(e)}")
        return jsonify({'error': str(e), 'nodes': []}), 500

@app.route('/api/auto-backtrack', methods=['POST'])
def auto_backtrack():
    """Auto-backtrack based on detection logic. Returns recommendation or executes backtrack."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
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
                node, _ = engine.backtrack(hypothesis_id=recommended_hyp_id)
            elif recommended_node_id is not None:
                # Valid node ID provided
                node, _ = engine.backtrack(node_id=recommended_node_id)
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
                'recommendation': recommendation,
                'session_id': session_id
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
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
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
            'branches': branches,
            'session_id': session_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/unfocus', methods=['POST'])
def unfocus():
    """Clear branch focus and return to evaluating all active branches."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    try:
        engine.unfocus()
        return jsonify({
            'success': True,
            'message': 'Focus cleared. Future artifacts will evaluate all active branches.',
            'current_branch_ids': [],
            'is_focused': False,
            'session_id': session_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-node', methods=['POST'])
def generate_node():
    """Expand a node by generating new sub-hypotheses or exploration directions."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
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
            'message': f'Generated {len(new_nodes)} new exploration directions from node {node_id}',
            'session_id': session_id
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/add-branch', methods=['POST'])
def add_branch():
    """Add a user-created hypothesis as a new node (manual branch). Owner or collaborator with token."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    data = request.json or {}
    description = (data.get('description') or '').strip()
    category = (data.get('category') or '').strip() or None
    parent_node_id = data.get('parent_node_id')
    if not description:
        return jsonify({'error': 'Hypothesis description is required'}), 400
    try:
        new_node = engine.add_manual_hypothesis(
            description=description,
            category=category,
            parent_node_id=parent_node_id,
        )
        all_hypotheses = engine.get_all_hypotheses_from_tree()
        branches = engine.get_all_branches_for_ui()
        return jsonify({
            'success': True,
            'node': {
                'id': new_node.id,
                'step_number': new_node.step_number,
                'hypothesis_id': new_node.hypothesis_id,
                'hypothesis': {
                    'id': new_node.hypothesis.id if new_node.hypothesis else None,
                    'description': new_node.hypothesis.description if new_node.hypothesis else None,
                    'category': new_node.hypothesis.category if new_node.hypothesis else None,
                    'confidence': new_node.hypothesis.confidence if new_node.hypothesis else 0.0,
                    'status': new_node.hypothesis.status if new_node.hypothesis else 'active',
                } if new_node.hypothesis else None,
                'parent_id': new_node.parent_id,
            },
            'all_hypotheses': [
                {'id': h.id, 'description': h.description, 'category': h.category, 'confidence': h.confidence, 'status': h.status, 'evidence': h.evidence}
                for h in all_hypotheses
            ],
            'branches': branches,
            'tree_summary': engine.get_tree_summary(),
            'session_id': session_id,
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/branches', methods=['GET'])
def get_all_branches():
    """Get all branches (active and pruned) for UI display using pre-order traversal."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    try:
        branches = engine.get_all_branches_for_ui()
        return jsonify({
            'branches': branches,
            'active_count': len([b for b in branches if b['status'] == 'active']),
            'pruned_count': len([b for b in branches if b['status'] == 'pruned']),
            'accepted_count': len([b for b in branches if b['status'] == 'accepted']),
            'session_id': session_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/prune-branch', methods=['POST'])
def prune_branch():
    """Prune a specific branch (mark as pruned but keep in memory)."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
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
            'tree_summary': engine.get_tree_summary(),
            'session_id': session_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/node-evaluation-details/<node_id>', methods=['GET'])
def get_node_evaluation_details(node_id):
    """Get evaluation and pruning details for a specific node."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
    if not engine:
        return jsonify({'error': 'Engine not initialized'}), 400
    
    try:
        node = engine._get_node(node_id)
        
        return jsonify({
            'node_id': node_id,
            'evaluation_details': node.evaluation_details if hasattr(node, 'evaluation_details') and node.evaluation_details else None,
            'pruning_details': node.pruning_details if hasattr(node, 'pruning_details') and node.pruning_details else None,
            'has_evaluation': hasattr(node, 'evaluation_details') and node.evaluation_details is not None,
            'has_pruning': hasattr(node, 'pruning_details') and node.pruning_details is not None,
            'session_id': session_id
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/unprune-branch', methods=['POST'])
def unprune_branch():
    """Unprune a branch (restore it to active status)."""
    engine, session_id, error_response = get_engine_from_request()
    if error_response:
        return jsonify(error_response[0]), error_response[1]
    
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
            'root_node_id': engine.root_node_id,
            'session_id': session_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reset', methods=['POST'])
def reset_session():
    """Reset the debugging session - saves current state, marks as finished, then clears from memory."""
    try:
        data = request.json if request.is_json else {}
    except Exception:
        data = {}
    session_id = data.get('session_id') or request.args.get('session_id')
    
    if session_id:
        # First, save the current session state to database
        engine = get_or_load_engine(session_id)
        if engine and engine.nodes:
            try:
                llm_integration = active_llm_integrations.get(session_id)
                llm_provider = llm_integration.provider_name if llm_integration else None
                llm_model = llm_integration.model_name if llm_integration else None
                session_data, nodes_data = engine.to_dict_for_db(session_id, llm_provider, llm_model)
                existing = session_manager.load_session(session_id)
                if existing:
                    if existing.get("owner_id") is not None:
                        session_data["owner_id"] = existing["owner_id"]
                    if existing.get("shared_with") is not None:
                        session_data["shared_with"] = existing["shared_with"]
                    if existing.get("share_token") is not None:
                        session_data["share_token"] = existing["share_token"]
                session_manager.save_session(session_id, session_data, nodes_data)
                logging.info(f"Auto-saved session {session_id} before reset with {len(nodes_data)} nodes")
            except Exception as e:
                logging.warning(f"Failed to auto-save session {session_id} before reset: {str(e)}")
        
        # Remove specific session from memory
        if session_id in active_engines:
            del active_engines[session_id]
        if session_id in active_llm_integrations:
            del active_llm_integrations[session_id]
        
        # Mark session as finished in MongoDB (don't delete, just mark as finished)
        try:
            session_manager.sessions.update_one(
                {'_id': session_id},
                {'$set': {'session_status': 'finished', 'finished_at': datetime.utcnow()}}
            )
        except Exception as e:
            logging.warning(f"Failed to mark session {session_id} as finished: {str(e)}")
        return jsonify({
            'success': True,
            'message': f'Session {session_id} reset successfully. Ready for a new issue.',
            'session_id': session_id
        })
    else:
        # Clear all sessions (for backward compatibility)
        active_engines.clear()
        active_llm_integrations.clear()
        return jsonify({
            'success': True,
            'message': 'All sessions reset successfully. Ready for a new issue.'
        })

if __name__ == '__main__':
    app.run(debug=True, port=5000)

