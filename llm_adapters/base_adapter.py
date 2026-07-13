"""
Base LLM Adapter - Abstract interface for all LLM providers.
All adapters must implement these methods.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tot_engine import ReasoningNode, TreeOfThoughtEngine


class BaseLLMAdapter(ABC):
    """
    Abstract base class for LLM adapters.
    All LLM providers must implement these methods.
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this LLM provider."""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name being used."""
        pass
    
    @abstractmethod
    def generate_hypotheses(self, problem_summary: str) -> Dict:
        """
        Generate initial hypotheses from the problem summary.
        
        Args:
            problem_summary: Description of the MongoDB issue
            
        Returns:
            Dict with keys:
                - 'hypotheses': List of hypothesis dicts with description, category, prior_score, confidence
                - 'next_requests': List of data requests
                - 'raw_analysis': Raw LLM output
        """
        pass
    
    @abstractmethod
    def evaluate_branches(
        self, 
        branch_nodes: List['ReasoningNode'], 
        artifact_content: str, 
        problem_summary: str
    ) -> Dict[str, Dict]:
        """
        Evaluate multiple hypothesis branches against a new artifact.
        
        Args:
            branch_nodes: List of nodes, one per active branch
            artifact_content: The artifact content to evaluate
            problem_summary: The original problem summary
            
        Returns:
            Dict mapping hypothesis_id to evaluation results:
                - 'scores': Dict[category, score]
                - 'evidence': Dict[category, evidence_text]
                - 'status': 'supported'/'contradicted'/'neutral'
                - 'llm_reasoning': Raw LLM reasoning
                - 'evidence_summary': Summary of findings
        """
        pass
    
    @abstractmethod
    def generate_next_requests(
        self, 
        node: 'ReasoningNode', 
        problem_summary: str
    ) -> List[str]:
        """
        Generate next data requests based on current state.
        
        Args:
            node: Current reasoning node with hypotheses and artifacts
            problem_summary: The original problem summary
            
        Returns:
            List of specific data requests (MongoDB commands, outputs needed)
        """
        pass
    
    @abstractmethod
    def generate_final_analysis(self, engine: 'TreeOfThoughtEngine') -> Dict:
        """
        Generate comprehensive final root cause analysis.
        
        Args:
            engine: The ToT engine instance with full tree state
            
        Returns:
            Dict with keys:
                - 'raw_analysis': Full LLM output
                - 'root_cause': Primary root cause description
                - 'confidence': Confidence score (0.0-1.0)
                - 'evidence': List of evidence strings
                - 'mitigation': Mitigation steps
                - 'next_steps': List of next steps
                - 'alternative_hypotheses': List of alternatives
        """
        pass
    
    @abstractmethod
    def generate_sub_hypotheses(
        self, 
        node: 'ReasoningNode', 
        engine: 'TreeOfThoughtEngine'
    ) -> Dict:
        """
        Generate new sub-hypotheses from a specific node (tree expansion).
        
        Args:
            node: The node to expand from
            engine: The ToT engine instance for context
            
        Returns:
            Dict with keys:
                - 'hypotheses': List of new hypothesis dicts
                - 'next_requests': List of data requests for new directions
        """
        pass
    
    def get_default_requests(self) -> List[str]:
        """Default data requests if LLM doesn't provide them."""
        return [
            "db.currentOp() output showing running operations",
            "Sample slow query profiles (db.system.profile.find())",
            "db.serverStatus() output",
            "db.stats() for affected collections"
        ]

