import axios from 'axios';

const API_BASE = '/api';
const AUTH_TOKEN_KEY = 'auth_token';
const BOARD_TOKENS_KEY = 'board_tokens';

const API_TIMEOUT_MS = 15000;

const api = axios.create({
  baseURL: API_BASE,
  timeout: API_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
  },
});

function getBoardTokens() {
  try {
    return JSON.parse(localStorage.getItem(BOARD_TOKENS_KEY) || '{}');
  } catch {
    return {};
  }
}

export function setBoardToken(sessionId, token) {
  const t = getBoardTokens();
  t[sessionId] = token;
  localStorage.setItem(BOARD_TOKENS_KEY, JSON.stringify(t));
}

export function getBoardToken(sessionId) {
  return getBoardTokens()[sessionId] || null;
}

export function clearBoardToken(sessionId) {
  if (!sessionId) return;
  const t = getBoardTokens();
  delete t[sessionId];
  localStorage.setItem(BOARD_TOKENS_KEY, JSON.stringify(t));
}

export function clearCurrentSessionStorage() {
  localStorage.removeItem('current_session_id');
}

// Attach JWT and/or board token to every request when present; ensure session_id for board endpoints
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  let sessionId = config.params?.session_id ?? config.data?.session_id;
  if (!sessionId && typeof localStorage !== 'undefined') {
    sessionId = localStorage.getItem('current_session_id');
  }
  // Endpoints that require session_id: inject from localStorage if missing (e.g. after join-by-token)
  const url = config.url || '';
  const needsSessionId = url.includes('current-node') || url.includes('history');
  if (needsSessionId && sessionId && !config.params?.session_id) {
    config.params = { ...config.params, session_id: sessionId };
  }
  // Never send current-node or history without session_id (avoids 400; session_id comes from param or localStorage)
  if (needsSessionId && !(config.params?.session_id ?? config.data?.session_id)) {
    return Promise.reject(new Error('session_id is required for this request'));
  }
  if (sessionId) {
    config.headers['X-Session-ID'] = sessionId;
    const boardToken = getBoardToken(sessionId);
    if (boardToken) {
      config.headers['X-Board-Token'] = boardToken;
    }
  }
  return config;
});

// On 401, clear token so AuthContext can show login again
let onAuthInvalid = null;
export function setAuthInvalidCallback(callback) {
  onAuthInvalid = callback;
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      if (typeof onAuthInvalid === 'function') onAuthInvalid();
    }
    return Promise.reject(error);
  }
);

export const detectLocalOllama = async (baseUrl = 'http://localhost:11434', timeout = 2.0) => {
  try {
    const response = await api.get('/detect-local-llm', {
      params: {
        base_url: baseUrl,
        timeout: timeout
      }
    });
    console.log('Detection API response:', response.data); // Debug log
    return response.data;
  } catch (error) {
    // Log the full error for debugging
    console.error('Detection API error:', error);
    console.error('Error response:', error.response?.data);
    // Return error details
    return { 
      available: false, 
      error: error.response?.data?.error || error.message || 'Unknown error occurred'
    };
  }
};

export const initializeEngine = async (problemSummary, useHardcodedFallback = false, provider = null, model = null, baseUrl = null) => {
  const body = {
    problem_summary: problemSummary,
    use_hardcoded_fallback: useHardcodedFallback,
  };
  
  // Add provider/model selection if provided
  if (provider) {
    body.provider = provider;
  }
  if (model) {
    body.model = model;
  }
  if (baseUrl) {
    body.base_url = baseUrl;
  }
  
  const response = await api.post('/initialize', body);
  return response.data;
};

export const uploadArtifact = async (artifactName, artifactContent, branchIds = null, sessionId = null) => {
  const body = {
    artifact_name: artifactName,
    artifact_content: artifactContent,
  };
  if (branchIds) {
    body.branch_ids = branchIds;
  }
  if (sessionId) {
    body.session_id = sessionId;
  }
  const response = await api.post('/upload-artifact', body);
  return response.data;
};

export const getCurrentNode = async (config = {}) => {
  const sessionId = config?.params?.session_id ?? (typeof localStorage !== 'undefined' ? localStorage.getItem('current_session_id') : null);
  if (!sessionId) {
    return Promise.reject(new Error('session_id is required'));
  }
  const finalConfig = { ...config, params: { ...config?.params, session_id: sessionId } };
  const response = await api.get('/current-node', finalConfig);
  return response.data;
};

export const checkSession = async (config = {}) => {
  const response = await api.get('/check-session', config);
  return response.data;
};

export const backtrack = async (nodeId, autoRestore = true, sessionId = null) => {
  const body = {
    node_id: nodeId,
    auto_restore: autoRestore,
  };
  if (sessionId) body.session_id = sessionId;
  const response = await api.post('/backtrack', body);
  return response.data;
};

export const unfocusBranches = async (sessionId = null) => {
  const body = {};
  if (sessionId) body.session_id = sessionId;
  const response = await api.post('/unfocus', body);
  return response.data;
};

export const generateNode = async (nodeId, sessionId = null) => {
  const body = { node_id: nodeId };
  if (sessionId) body.session_id = sessionId;
  const response = await api.post('/generate-node', body);
  return response.data;
};

export const pruneBranch = async (hypothesisId, sessionId = null) => {
  const body = { hypothesis_id: hypothesisId };
  if (sessionId) body.session_id = sessionId;
  const response = await api.post('/prune-branch', body);
  return response.data;
};

export const unpruneBranch = async (hypothesisId, sessionId = null) => {
  const body = { hypothesis_id: hypothesisId };
  if (sessionId) body.session_id = sessionId;
  const response = await api.post('/unprune-branch', body);
  return response.data;
};

export const focusBranch = async (hypothesisId, sessionId = null) => {
  const body = { hypothesis_id: hypothesisId };
  if (sessionId) body.session_id = sessionId;
  const response = await api.post('/focus-branch', body);
  return response.data;
};

export const getFinalAnalysis = async (sessionId = null) => {
  const config = sessionId ? { params: { session_id: sessionId } } : {};
  const response = await api.get('/final-analysis', config);
  return response.data;
};

export const resetSession = async (sessionId = null) => {
  const body = sessionId ? { session_id: sessionId } : {};
  const response = await api.post('/reset', body);
  return response.data;
};

export const getNodeEvaluationDetails = async (nodeId, sessionId = null) => {
  const config = sessionId ? { params: { session_id: sessionId } } : {};
  const response = await api.get(`/node-evaluation-details/${nodeId}`, config);
  return response.data;
};

export const getHistory = async (sessionId = null) => {
  const sid = sessionId ?? (typeof localStorage !== 'undefined' ? localStorage.getItem('current_session_id') : null);
  if (!sid) {
    return Promise.reject(new Error('session_id is required'));
  }
  const config = { params: { session_id: sid } };
  const response = await api.get('/history', config);
  return response.data;
};

// Session management APIs
export const listUnfinishedSessions = async () => {
  const response = await api.get('/sessions/unfinished');
  return response.data;
};

/** List active sessions the current user can access (owner or shared_with). Requires auth. */
export const getMySessions = async () => {
  const response = await api.get('/sessions/my-sessions');
  return response.data;
};

export const loadSession = async (sessionId) => {
  const response = await api.get(`/sessions/${sessionId}/load`);
  return response.data;
};

export const saveSession = async (sessionId) => {
  const response = await api.post(`/sessions/${sessionId}/save`);
  return response.data;
};

export const getSessionStatus = async (sessionId) => {
  const response = await api.get(`/sessions/${sessionId}/status`);
  return response.data;
};

// Auth APIs
export const authLogin = async (email, password) => {
  const response = await api.post('/auth/login', { email, password });
  return response.data;
};

export const authRegister = async (email, password, name = null) => {
  const response = await api.post('/auth/register', { email, password, name: name || undefined });
  return response.data;
};

export const authMe = async () => {
  const response = await api.get('/auth/me');
  return response.data;
};

// Join board with share token (no auth required)
export const joinBoard = async (token) => {
  const response = await api.get('/join', { params: { token } });
  return response.data;
};

// Get or create share token (owner only)
export const getShareToken = async (sessionId) => {
  const response = await api.post(`/sessions/${sessionId}/share-token`);
  return response.data;
};

// Search users by name or email (auth required)
export const searchUsers = async (q, limit = 20) => {
  const response = await api.get('/users/search', { params: { q, limit } });
  return response.data;
};

// Add a user to board's shared_with (owner only)
export const shareWithUser = async (sessionId, userId) => {
  const response = await api.post(`/sessions/${sessionId}/share-with`, { user_id: userId });
  return response.data;
};

// List users this board is shared with
export const getSharedWith = async (sessionId) => {
  const response = await api.get(`/sessions/${sessionId}/shared-with`);
  return response.data;
};

// Add user-created hypothesis (manual branch)
export const addBranch = async (sessionId, description, category = null, parentNodeId = null) => {
  const body = { session_id: sessionId, description };
  if (category) body.category = category;
  if (parentNodeId) body.parent_node_id = parentNodeId;
  const response = await api.post('/add-branch', body);
  return response.data;
};

export default api;

