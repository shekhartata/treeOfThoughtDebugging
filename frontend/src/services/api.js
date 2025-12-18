import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const initializeEngine = async (problemSummary, useHardcodedFallback = false) => {
  const response = await api.post('/initialize', {
    problem_summary: problemSummary,
    use_hardcoded_fallback: useHardcodedFallback,
  });
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

