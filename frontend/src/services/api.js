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

export const uploadArtifact = async (artifactName, artifactContent, branchIds = null) => {
  const body = {
    artifact_name: artifactName,
    artifact_content: artifactContent,
  };
  if (branchIds) {
    body.branch_ids = branchIds;
  }
  const response = await api.post('/upload-artifact', body);
  return response.data;
};

export const getCurrentNode = async () => {
  const response = await api.get('/current-node');
  return response.data;
};

export const checkSession = async () => {
  const response = await api.get('/check-session');
  return response.data;
};

export const backtrack = async (nodeId, autoRestore = true) => {
  const response = await api.post('/backtrack', {
    node_id: nodeId,
    auto_restore: autoRestore,
  });
  return response.data;
};

export const unfocusBranches = async () => {
  const response = await api.post('/unfocus');
  return response.data;
};

export const generateNode = async (nodeId) => {
  const response = await api.post('/generate-node', {
    node_id: nodeId,
  });
  return response.data;
};

export const pruneBranch = async (hypothesisId) => {
  const response = await api.post('/prune-branch', {
    hypothesis_id: hypothesisId,
  });
  return response.data;
};

export const unpruneBranch = async (hypothesisId) => {
  const response = await api.post('/unprune-branch', {
    hypothesis_id: hypothesisId,
  });
  return response.data;
};

export const focusBranch = async (hypothesisId) => {
  const response = await api.post('/focus-branch', {
    hypothesis_id: hypothesisId,
  });
  return response.data;
};

export const getFinalAnalysis = async () => {
  const response = await api.get('/final-analysis');
  return response.data;
};

export const resetSession = async () => {
  const response = await api.post('/reset');
  return response.data;
};

export const getNodeEvaluationDetails = async (nodeId) => {
  const response = await api.get(`/node-evaluation-details/${nodeId}`);
  return response.data;
};

export default api;

