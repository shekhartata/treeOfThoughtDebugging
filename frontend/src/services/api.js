import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

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
  const response = await api.get('/current-node', config);
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
  const config = sessionId ? { params: { session_id: sessionId } } : {};
  const response = await api.get('/history', config);
  return response.data;
};

// Session management APIs
export const listUnfinishedSessions = async () => {
  const response = await api.get('/sessions/unfinished');
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

export default api;

