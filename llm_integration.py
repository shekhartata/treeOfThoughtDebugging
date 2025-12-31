"""
LLM Integration for MongoDB Debugging Tool
Handles prompts and LLM-based scoring for hypotheses.

This module now uses the adapter pattern for swappable LLM providers.
To switch providers, set the LLM_PROVIDER environment variable:
  - export LLM_PROVIDER=openai  (default, GPT-5)
  - export LLM_PROVIDER=groq    (DeepSeek-R1-Distill via Groq, faster)

Or import and use adapters directly:
  from llm_adapters import get_adapter
  adapter = get_adapter("groq")
"""

import logging
from typing import List, Dict, Optional
import os
from dotenv import load_dotenv

# Import adapter system
from llm_adapters import get_adapter, ACTIVE_PROVIDER
from llm_adapters.base_adapter import BaseLLMAdapter

# Load environment variables from .env file
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)


class LLMIntegration:
    """
    Handles LLM interactions for hypothesis evaluation.
    
    This class is now a thin wrapper around the adapter system.
    All LLM calls are delegated to the active adapter.
    
    To switch LLM providers:
        1. Set LLM_PROVIDER environment variable (openai, groq)
        2. Or pass adapter directly: LLMIntegration(adapter=my_adapter)
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        require_llm: bool = True,
        adapter: Optional[BaseLLMAdapter] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize LLM integration.
        
        Args:
            api_key: API key (deprecated, use environment variables instead)
            require_llm: If True, raise error if LLM not available
            adapter: Optional pre-configured adapter instance
            provider: Optional provider name to use ("openai", "groq", "ollama")
            model: Optional model name to use (provider-specific)
            base_url: Optional base URL for Ollama/local instances
        """
        self.require_llm = require_llm
        self._adapter = adapter
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        
        # Try to initialize adapter
        try:
            if self._adapter is None:
                self._adapter = self._create_adapter()
            self.use_llm = True
            logger.info(f"LLM Integration initialized with {self._adapter.provider_name} ({self._adapter.model_name})")
        except ValueError as e:
            self.use_llm = False
            if self.require_llm:
                raise
            else:
                logger.warning(f"LLM not available: {e}. Using fallback mode.")
                print(f"⚠️  LLM not available: {e}. Using fallback mode.")
    
    def _create_adapter(self) -> BaseLLMAdapter:
        """Create the appropriate adapter based on configuration."""
        provider = self._provider or ACTIVE_PROVIDER
        
        # Build kwargs for adapter
        kwargs = {}
        if self._api_key:
            kwargs['api_key'] = self._api_key
        if self._model:
            kwargs['model'] = self._model
        if self._base_url:
            kwargs['base_url'] = self._base_url
        
        return get_adapter(provider, **kwargs)
    
    @property
    def adapter(self) -> BaseLLMAdapter:
        """Get the current adapter."""
        if self._adapter is None:
            raise ValueError("LLM adapter not initialized")
        return self._adapter
    
    @property
    def provider_name(self) -> str:
        """Get the name of the current LLM provider."""
        return self.adapter.provider_name if self._adapter else "None"
    
    @property
    def model_name(self) -> str:
        """Get the name of the current model."""
        return self.adapter.model_name if self._adapter else "None"
    
    # =========================================================================
    # Public API - Delegates to adapter
    # =========================================================================
    
    def generate_hypotheses_from_llm(self, problem_summary: str) -> Dict:
        """
        Generate initial hypotheses from LLM.
        
        Args:
            problem_summary: Description of the MongoDB issue
            
        Returns:
            Dict with 'hypotheses', 'next_requests', 'raw_analysis'
        """
        if not self.use_llm:
            raise ValueError("LLM is required for hypothesis generation but not available.")
        
        return self.adapter.generate_hypotheses(problem_summary)
    
    def evaluate_branches_with_llm(
        self, 
        branch_nodes: List, 
        artifact_content: str, 
        problem_summary: str
    ) -> Dict[str, Dict]:
        """
        Evaluate multiple hypothesis branches against a new artifact.
        
        Args:
            branch_nodes: List of ReasoningNode instances
            artifact_content: The artifact content to evaluate
            problem_summary: The original problem summary
            
        Returns:
            Dict mapping hypothesis_id to evaluation results
        """
        if not self.use_llm:
            raise ValueError("LLM is required for artifact evaluation but not available.")
        
        return self.adapter.evaluate_branches(branch_nodes, artifact_content, problem_summary)
    
    def generate_next_requests_llm(self, node, problem_summary: str) -> List[str]:
        """
        Generate next data requests based on current state.
        
        Args:
            node: Current ReasoningNode
            problem_summary: The original problem summary
            
        Returns:
            List of specific data requests
        """
        if not self.use_llm:
            raise ValueError("LLM is required for generating next requests but not available.")
        
        return self.adapter.generate_next_requests(node, problem_summary)
    
    def generate_final_analysis_llm(self, engine) -> Dict:
        """
        Generate comprehensive final root cause analysis.
        
        Args:
            engine: The TreeOfThoughtEngine instance
            
        Returns:
            Dict with analysis results
        """
        if not self.use_llm:
            raise ValueError("LLM is required for final analysis but not available.")
        
        return self.adapter.generate_final_analysis(engine)
    
    def generate_sub_hypotheses_from_node(self, node, engine) -> Dict:
        """
        Generate new sub-hypotheses from a specific node.
        
        Args:
            node: The ReasoningNode to expand from
            engine: The TreeOfThoughtEngine instance
            
        Returns:
            Dict with 'hypotheses' and 'next_requests'
        """
        if not self.use_llm:
            raise ValueError("LLM is required for node expansion but not available.")
        
        return self.adapter.generate_sub_hypotheses(node, engine)
    
    # =========================================================================
    # Legacy methods - kept for backward compatibility
    # =========================================================================
    
    def evaluate_hypotheses_with_llm(self, node, artifact_content: str, problem_summary: str) -> Dict:
        """
        Legacy method for single-node evaluation.
        Converts to branch evaluation format for backward compatibility.
        """
        if not self.use_llm:
            raise ValueError("LLM is required for artifact evaluation but not available.")
        
        # Create a single-branch list for the adapter
        results = self.adapter.evaluate_branches([node], artifact_content, problem_summary)
        
        # Convert back to legacy format
        scores = {}
        evidence_map = {}
        raw_analysis = ""
        
        for hyp_id, result in results.items():
            scores.update(result.get('scores', {}))
            evidence_map.update(result.get('evidence', {}))
            raw_analysis = result.get('llm_reasoning', '')
        
        return {
            'scores': scores,
            'evidence': evidence_map,
            'raw_analysis': raw_analysis
        }
    
    def get_initial_analysis(self, problem_summary: str) -> Dict:
        """Legacy method for initial analysis."""
        if not self.use_llm:
            return {
                'analysis': '',
                'hypotheses': [],
                'next_requests': [],
                'confidence_range': {}
            }
        
        try:
            result = self.generate_hypotheses_from_llm(problem_summary)
            return {
                'analysis': result.get('raw_analysis', ''),
                'hypotheses': result.get('hypotheses', []),
                'next_requests': result.get('next_requests', []),
                'confidence_range': {}
            }
        except Exception as e:
            logger.error(f"LLM hypothesis generation failed: {e}", exc_info=True)
            return {
                'analysis': f'Error: {e}',
                'hypotheses': [],
                'next_requests': [],
                'confidence_range': {}
            }
    
    def _get_default_requests(self) -> List[str]:
        """Default data requests if LLM doesn't provide them."""
        return self.adapter.get_default_requests() if self._adapter else [
            "db.currentOp() output showing running operations",
            "Sample slow query profiles (db.system.profile.find())",
            "db.serverStatus() output",
            "db.stats() for affected collections"
        ]
    
    # =========================================================================
    # Prompt methods - kept for reference/debugging (not used by adapters)
    # =========================================================================
    
    def _get_initial_prompt(self, problem_summary: str) -> str:
        """Generate initial prompt for LLM (for reference)."""
        return f"""You are an expert MongoDB consultant helping to debug a performance issue.

Problem Summary:
{problem_summary}

You do NOT have direct database access. You must request specific data artifacts from the consulting engineer.

Based on this problem, provide:
1. HYPOTHESES: List potential root causes (indexing, query shape, schema, cache, storage, replication, networking)
2. NEXT_REQUESTS: Specific MongoDB commands/outputs you need to see
3. CONFIDENCE_RANGE: Initial confidence assessment for each hypothesis

Format your response clearly with these sections."""

    def _get_followup_prompt(self, node, artifact_content: str) -> str:
        """Generate follow-up prompt for artifact evaluation (for reference)."""
        hypotheses_text = "\n".join([
            f"- {h.description} (Category: {h.category}, Current Confidence: {h.confidence:.2f})"
            for h in node.hypotheses if h.status == "active"
        ])
        
        return f"""You are evaluating new diagnostic data for a MongoDB performance issue.

Current Active Hypotheses:
{hypotheses_text}

New Artifact Received:
{artifact_content[:2000]}...

Based on this new evidence:
1. UPDATED_HYPOTHESES: Update confidence scores for each hypothesis (0.0-1.0)
2. NEXT_REQUESTS: What additional data would help confirm or rule out hypotheses?
3. PROGRESS_SUMMARY: Summary of what we've learned and what's most likely

Provide specific confidence scores for each hypothesis category."""

    def _get_final_prompt(self, engine) -> str:
        """Generate final prompt for root cause analysis (for reference)."""
        node = engine.get_current_node()
        if not node:
            return ""
        
        top_hypotheses = sorted(
            [h for h in node.hypotheses if h.status in ["active", "accepted"]],
            key=lambda x: x.confidence,
            reverse=True
        )[:3]
        
        hypotheses_text = "\n".join([
            f"- {h.description}: {h.confidence:.2f} confidence. Evidence: {', '.join(h.evidence[:3])}"
            for h in top_hypotheses
        ])
        
        all_artifacts = []
        for n in engine.nodes:
            all_artifacts.extend(n.artifacts_received)
        
        artifacts_summary = "\n".join([
            f"- {art['name']}: {len(art['content'])} chars"
            for art in all_artifacts[-5:]
        ])
        
        return f"""You are providing the final root cause analysis for a MongoDB performance issue.

Problem Summary:
{engine.problem_summary}

Top Hypotheses:
{hypotheses_text}

Artifacts Collected:
{artifacts_summary}

Provide:
1. ROOT_CAUSE: The most likely root cause with confidence level
2. EVIDENCE: Key evidence supporting this conclusion
3. MITIGATION: Specific steps to resolve the issue
4. NEXT_STEPS_IF_UNCERTAIN: Additional data to collect if more investigation is needed

Be specific and actionable."""
