"""
Tree-of-Thought Engine for MongoDB Debugging Tool
Implements the core reasoning logic with hypothesis evaluation and pruning.
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    HIGH = (0.7, 1.0)
    MEDIUM = (0.4, 0.69)
    LOW = (0.0, 0.39)


@dataclass
class Hypothesis:
    """Represents a hypothesis about a MongoDB issue."""
    id: str
    description: str
    category: str  # indexing, query_shape, schema, wt_cache, storage, replication, networking
    prior_score: float
    evidence: List[str] = field(default_factory=list)
    rule_score: float = 0.0
    llm_score: float = 0.0
    user_feedback: float = 0.0
    confidence: float = 0.0
    status: str = "active"  # active, pruned, accepted
    
    def update_confidence(self, weights: Dict[str, float]):
        """Update confidence score using weighted formula."""
        self.confidence = (
            weights['prior'] * self.prior_score +
            weights['rule'] * self.rule_score +
            weights['llm'] * self.llm_score +
            weights['user'] * self.user_feedback
        )
        # Clamp between 0 and 1
        self.confidence = max(0.0, min(1.0, self.confidence))


@dataclass
class ReasoningNode:
    """A node in the Tree-of-Thought representing a reasoning step."""
    id: str
    step_number: int
    hypotheses: List[Hypothesis] = field(default_factory=list)
    requested_data: List[str] = field(default_factory=list)
    artifacts_received: List[Dict] = field(default_factory=list)
    evaluation_summary: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)


class TreeOfThoughtEngine:
    """Main engine for Tree-of-Thought reasoning."""
    
    # Category priors as specified in the document
    CATEGORY_PRIORS = {
        'indexing': 0.35,
        'query_shape': 0.25,
        'schema': 0.20,
        'wt_cache': 0.15,
        'storage': 0.15,
        'replication': 0.10,
        'networking': 0.05
    }
    
    # Scoring weights
    DEFAULT_WEIGHTS = {
        'prior': 0.3,
        'rule': 0.4,
        'llm': 0.25,
        'user': 0.05
    }
    
    # Thresholds
    PRUNE_THRESHOLD = 0.3
    SUCCESS_THRESHOLD = 0.7
    
    # Rule-based scoring patterns
    RULE_PATTERNS = {
        'COLLSCAN': {'category': 'indexing', 'score': 0.5},  # Strong evidence
        '$push_large_arrays': {'category': 'schema', 'score': 0.5},  # Strong evidence
        'wt_cache_high': {'category': 'wt_cache', 'score': 0.3},  # >85%
        'replication_lag_low': {'category': 'replication', 'score': -0.2},  # <3s
        'disk_iops_high': {'category': 'storage', 'score': 0.3}  # >85%
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None, llm_integration=None):
        self.nodes: List[ReasoningNode] = []
        self.current_node_id: Optional[str] = None
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.problem_summary: str = ""
        self.step_counter: int = 0
        self.llm_integration = llm_integration  # LLM integration instance
    
    def initialize(self, problem_summary: str, use_hardcoded_fallback: bool = False) -> ReasoningNode:
        """Initialize the ToT engine with a problem statement.
        
        Args:
            problem_summary: Description of the MongoDB issue
            use_hardcoded_fallback: If True, use hardcoded hypotheses instead of LLM (fallback mode)
        """
        self.problem_summary = problem_summary
        self.step_counter = 1
        
        initial_hypotheses = []
        requested_data = []
        
        # PRIMARY: Try LLM first (unless fallback is explicitly requested)
        if not use_hardcoded_fallback and self.llm_integration and self.llm_integration.use_llm:
            try:
                llm_result = self.llm_integration.generate_hypotheses_from_llm(problem_summary)
                llm_hypotheses = llm_result.get('hypotheses', [])
                requested_data = llm_result.get('next_requests', [])
                
                if llm_hypotheses:
                    # Convert LLM hypotheses to Hypothesis objects
                    initial_hypotheses = [
                        Hypothesis(
                            id=f"hyp_{i+1}",
                            description=h['description'],
                            category=h['category'],
                            prior_score=h['prior_score'],
                            confidence=h['confidence']
                        )
                        for i, h in enumerate(llm_hypotheses)
                    ]
                    print(f"✓ Generated {len(initial_hypotheses)} hypotheses from LLM")
                    
                    # Use LLM-generated requests (already included in llm_result)
                    if not requested_data:
                        # If LLM didn't provide requests, try to generate them now
                        if self.llm_integration and self.llm_integration.use_llm:
                            try:
                                temp_node = ReasoningNode(
                                    id="temp_init",
                                    step_number=1,
                                    hypotheses=initial_hypotheses
                                )
                                requested_data = self.llm_integration.generate_next_requests_llm(
                                    temp_node, problem_summary
                                )
                            except Exception as e:
                                # If LLM request generation fails, log error and fall back to hardcoded requests
                                logger.error(f"LLM request generation failed: {e}", exc_info=True)
                                logger.error(f"Error type: {type(e).__name__}")
                                logger.error(f"Error details: {str(e)}")
                                print(f"⚠️  LLM request generation failed: {e}")
                                print("   Using hardcoded initial requests...")
                                requested_data = self._get_initial_requests()
                        else:
                            # If LLM not available, use hardcoded requests
                            requested_data = self._get_initial_requests()
            except Exception as e:
                logger.error(f"LLM hypothesis generation failed: {e}", exc_info=True)
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error details: {str(e)}")
                print(f"⚠️  LLM hypothesis generation failed: {e}")
                print("   Falling back to hardcoded hypotheses...")
                use_hardcoded_fallback = True
        
        # FALLBACK: Use hardcoded hypotheses if LLM failed or was requested
        if use_hardcoded_fallback or not initial_hypotheses:
            initial_hypotheses = self._get_hardcoded_hypotheses()
            # Try to get LLM-generated requests if available
            if self.llm_integration and self.llm_integration.use_llm:
                try:
                    requested_data = self.llm_integration.generate_next_requests_llm(
                        ReasoningNode(id="temp", step_number=1, hypotheses=initial_hypotheses),
                        problem_summary
                    )
                except Exception as e:
                    # If LLM request generation fails, log error and fall back to hardcoded requests
                    logger.error(f"LLM request generation failed in fallback mode: {e}", exc_info=True)
                    logger.error(f"Error type: {type(e).__name__}")
                    logger.error(f"Error details: {str(e)}")
                    print(f"⚠️  LLM request generation failed: {e}")
                    print("   Using hardcoded initial requests...")
                    requested_data = self._get_initial_requests()
            else:
                # If LLM not available, use hardcoded requests
                requested_data = self._get_initial_requests()
            if use_hardcoded_fallback:
                print("✓ Using hardcoded hypotheses (fallback mode)")
        
        initial_node = ReasoningNode(
            id="node_1",
            step_number=1,
            hypotheses=initial_hypotheses,
            requested_data=requested_data
        )
        
        self.nodes.append(initial_node)
        self.current_node_id = initial_node.id
        
        return initial_node
    
    def _get_hardcoded_hypotheses(self) -> List[Hypothesis]:
        """Get hardcoded hypotheses as fallback option."""
        return [
            Hypothesis(
                id=f"hyp_{i+1}",
                description=desc,
                category=cat,
                prior_score=prior,
                confidence=prior
            )
            for i, (cat, (desc, prior)) in enumerate([
                ('indexing', ('Missing or inefficient indexes', 0.35)),
                ('query_shape', ('Query shape issues (e.g., large result sets)', 0.25)),
                ('schema', ('Schema design problems (e.g., large arrays)', 0.20)),
                ('wt_cache', ('WiredTiger cache pressure', 0.15)),
                ('storage', ('Storage/IOPS issues', 0.15)),
                ('replication', ('Replication lag or conflicts', 0.10)),
                ('networking', ('Network latency or bandwidth issues', 0.05))
            ])
        ]
    
    def _get_initial_requests(self) -> List[str]:
        """Fallback: Get initial data requests. Should not be used if LLM is available."""
        # This is only a minimal fallback - LLM should always be used
        return [
            "Please provide diagnostic data relevant to the problem"
        ]
    
    def add_artifact(self, artifact_name: str, artifact_content: str) -> ReasoningNode:
        """Add an artifact and create a new reasoning node."""
        if not self.current_node_id:
            raise ValueError("Engine not initialized. Call initialize() first.")
        
        current_node = self._get_node(self.current_node_id)
        self.step_counter += 1
        
        # Create new node as child of current
        new_node = ReasoningNode(
            id=f"node_{self.step_counter}",
            step_number=self.step_counter,
            parent_id=current_node.id,
            artifacts_received=[{
                'name': artifact_name,
                'content': artifact_content,
                'timestamp': datetime.now().isoformat()
            }]
        )
        
        # Copy hypotheses from parent
        new_node.hypotheses = [
            Hypothesis(
                id=h.id,
                description=h.description,
                category=h.category,
                prior_score=h.prior_score,
                evidence=h.evidence.copy(),
                rule_score=h.rule_score,
                llm_score=h.llm_score,
                user_feedback=h.user_feedback,
                confidence=h.confidence,
                status=h.status
            ) for h in current_node.hypotheses if h.status == "active"
        ]
        
        # Evaluate artifacts against hypotheses using LLM (REQUIRED)
        if not self.llm_integration or not self.llm_integration.use_llm:
            raise ValueError("LLM is required for artifact evaluation. Please ensure OPENAI_API_KEY is set.")
        
        try:
            evaluation_result = self.llm_integration.evaluate_hypotheses_with_llm(
                new_node, artifact_content, self.problem_summary
            )
            scores = evaluation_result.get('scores', {})
            evidence_map = evaluation_result.get('evidence', {})
            
            # Update hypotheses with LLM scores and evidence
            for hypothesis in new_node.hypotheses:
                if hypothesis.status == "active":
                    if hypothesis.category in scores:
                        hypothesis.llm_score = scores[hypothesis.category]
                        # Add LLM-generated evidence
                        if hypothesis.category in evidence_map:
                            hypothesis.evidence.append(evidence_map[hypothesis.category])
                    
                    # Update confidence (LLM score is primary now)
                    hypothesis.update_confidence(self.weights)
                    
                    # Update status based on confidence
                    # Note: Pruning will be done in prune_hypotheses() to ensure we keep top 2
                    if hypothesis.confidence >= self.SUCCESS_THRESHOLD:
                        hypothesis.status = "accepted"
        except Exception as e:
            logger.error(f"LLM artifact evaluation failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM evaluation failed: {e}. Please check your API key and try again.")
        
        # Update parent's children
        current_node.children_ids.append(new_node.id)
        
        self.nodes.append(new_node)
        self.current_node_id = new_node.id
        
        return new_node
    
    # _evaluate_artifacts() method removed - LLM evaluation is now required
    
    def prune_hypotheses(self, node_id: Optional[str] = None):
        """Prune low-confidence hypotheses from a node.
        
        Keeps at least the top 2 highest-scored hypotheses unless their confidence
        is less than 5% (0.05).
        """
        node = self._get_node(node_id or self.current_node_id)
        
        # Get all active hypotheses
        active_hypotheses = [h for h in node.hypotheses if h.status == "active"]
        
        if not active_hypotheses:
            return
        
        # Sort by confidence (highest first)
        sorted_hypotheses = sorted(active_hypotheses, key=lambda x: x.confidence, reverse=True)
        
        # Keep at least the top 2 hypotheses
        min_keep_count = min(2, len(sorted_hypotheses))
        top_hypotheses = sorted_hypotheses[:min_keep_count]
        
        # Prune hypotheses that are below threshold, but protect top 2 unless they're < 5%
        MIN_PROTECTED_CONFIDENCE = 0.05  # 5%
        
        for hypothesis in sorted_hypotheses:
            # If it's in the top 2, only prune if confidence < 5%
            if hypothesis in top_hypotheses:
                if hypothesis.confidence < MIN_PROTECTED_CONFIDENCE:
                    hypothesis.status = "pruned"
            # Otherwise, prune if below normal threshold
            else:
                if hypothesis.confidence < self.PRUNE_THRESHOLD:
                    hypothesis.status = "pruned"
    
    def backtrack(self, node_id: str) -> ReasoningNode:
        """Backtrack to a previous node to explore alternate branches."""
        node = self._get_node(node_id)
        self.current_node_id = node.id
        return node
    
    def should_auto_backtrack(self) -> Optional[Dict]:
        """
        Modular auto-backtrack detection logic.
        Returns None if no backtrack needed, or dict with backtrack recommendation.
        Does not modify state - only analyzes and recommends.
        """
        current_node = self.get_current_node()
        if not current_node:
            return None
        
        active_hypotheses = [h for h in current_node.hypotheses if h.status == "active"]
        
        # Check 1: Dead-end detection - all hypotheses pruned or very low confidence
        if not active_hypotheses:
            # Find last node with active hypotheses
            for node in reversed(self.nodes):
                if any(h.status == "active" for h in node.hypotheses):
                    return {
                        'reason': 'dead_end',
                        'message': 'All hypotheses have been pruned. No active hypotheses remaining.',
                        'recommended_node_id': node.id,
                        'recommended_step': node.step_number
                    }
        
        # Check 2: Very low confidence - all active hypotheses below threshold
        if active_hypotheses:
            max_confidence = max(h.confidence for h in active_hypotheses)
            if max_confidence < 0.15:  # Very low confidence threshold
                # Find best previous node (highest max confidence)
                best_node = None
                best_confidence = 0.0
                for node in self.nodes:
                    node_active = [h for h in node.hypotheses if h.status == "active"]
                    if node_active:
                        node_max = max(h.confidence for h in node_active)
                        if node_max > best_confidence and node.step_number < current_node.step_number:
                            best_confidence = node_max
                            best_node = node
                
                if best_node and best_confidence > max_confidence:
                    return {
                        'reason': 'low_confidence',
                        'message': f'All hypotheses have very low confidence ({max_confidence:.1%}). Previous step had better results.',
                        'recommended_node_id': best_node.id,
                        'recommended_step': best_node.step_number,
                        'current_max_confidence': max_confidence,
                        'previous_max_confidence': best_confidence
                    }
        
        # Check 3: Stagnation - no improvement in last few steps
        if len(self.nodes) >= 4:  # Need at least 4 nodes to detect stagnation
            recent_nodes = sorted(self.nodes, key=lambda n: n.step_number, reverse=True)[:4]
            recent_confidences = []
            for node in reversed(recent_nodes):  # Oldest to newest
                node_active = [h for h in node.hypotheses if h.status == "active"]
                if node_active:
                    recent_confidences.append(max(h.confidence for h in node_active))
            
            if len(recent_confidences) >= 3:
                # Check if confidence is declining or stagnant
                if recent_confidences[-1] <= recent_confidences[0] and recent_confidences[-1] < 0.5:
                    # Find node before stagnation started
                    stagnation_start = recent_nodes[0]  # Oldest in recent set
                    return {
                        'reason': 'stagnation',
                        'message': 'No significant improvement in recent steps. Confidence has stagnated or declined.',
                        'recommended_node_id': stagnation_start.id,
                        'recommended_step': stagnation_start.step_number,
                        'confidence_trend': recent_confidences
                    }
        
        return None
    
    def get_next_requests(self, node: Optional[ReasoningNode] = None) -> List[str]:
        """Generate next data requests using LLM based on current state."""
        node = node or self._get_node(self.current_node_id)
        
        # LLM is REQUIRED for generating requests
        if not self.llm_integration or not self.llm_integration.use_llm:
            raise ValueError("LLM is required for generating next requests. Please ensure OPENAI_API_KEY is set.")
        
        try:
            requests = self.llm_integration.generate_next_requests_llm(node, self.problem_summary)
            # Add to requested_data to track what we've asked for
            for req in requests:
                if req not in node.requested_data:
                    node.requested_data.append(req)
            return requests
        except Exception as e:
            logger.error(f"LLM next requests generation failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM request generation failed: {e}. Please check your API key and try again.")
    
    def _get_node(self, node_id: str) -> ReasoningNode:
        """Get a node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise ValueError(f"Node {node_id} not found")
    
    def get_current_node(self) -> Optional[ReasoningNode]:
        """Get the current active node."""
        if not self.current_node_id:
            return None
        return self._get_node(self.current_node_id)
    
    def get_tree_summary(self) -> Dict:
        """Get a summary of the reasoning tree."""
        return {
            'total_nodes': len(self.nodes),
            'current_step': self.step_counter,
            'problem_summary': self.problem_summary,
            'active_hypotheses': sum(
                1 for n in self.nodes 
                for h in n.hypotheses 
                if h.status == "active"
            ),
            'pruned_hypotheses': sum(
                1 for n in self.nodes 
                for h in n.hypotheses 
                if h.status == "pruned"
            ),
            'accepted_hypotheses': sum(
                1 for n in self.nodes 
                for h in n.hypotheses 
                if h.status == "accepted"
            )
        }
    
    def is_complete(self) -> bool:
        """Check if reasoning is complete (sufficient data gathered)."""
        node = self.get_current_node()
        if not node:
            return False
        
        active_hypotheses = [h for h in node.hypotheses if h.status == "active"]
        
        # Check if we have accepted hypotheses with high confidence
        accepted = [h for h in node.hypotheses if h.status == "accepted"]
        if accepted and len(accepted) > 0:
            return True
        
        # Check if we've gathered enough data and narrowed down hypotheses
        if len(active_hypotheses) <= 2 and len(node.artifacts_received) >= 3:
            return True
        
        return False
    
    def get_final_analysis(self) -> Dict:
        """Generate final root cause analysis using LLM."""
        node = self.get_current_node()
        if not node:
            return {}
        
        # LLM is REQUIRED for final analysis
        if not self.llm_integration or not self.llm_integration.use_llm:
            raise ValueError("LLM is required for final analysis. Please ensure OPENAI_API_KEY is set.")
        
        try:
            llm_analysis = self.llm_integration.generate_final_analysis_llm(self)
            
            # Get top hypotheses for category/confidence metadata
            top_hypotheses = sorted(
                [h for h in node.hypotheses if h.status in ["active", "accepted"]],
                key=lambda x: x.confidence,
                reverse=True
            )
            
            # Check if all hypotheses were pruned
            all_pruned = len([h for h in node.hypotheses if h.status == "pruned"]) == len(node.hypotheses)
            
            # Use LLM analysis as primary source
            # LLM will provide recommendations even if all hypotheses are pruned
            result = {
                'root_cause': llm_analysis.get('root_cause', 'Unable to determine root cause with available data'),
                'category': top_hypotheses[0].category if top_hypotheses else 'unknown',
                'confidence': llm_analysis.get('confidence', top_hypotheses[0].confidence if top_hypotheses else 0.0),
                'evidence': llm_analysis.get('evidence', top_hypotheses[0].evidence if top_hypotheses else []),
                'mitigation': llm_analysis.get('mitigation', 'Review system configuration and performance metrics.'),
                'next_steps': llm_analysis.get('next_steps', ['Collect more artifacts', 'Review system logs']),
                'alternative_hypotheses': llm_analysis.get('alternative_hypotheses', [
                    {'description': h.description, 'confidence': h.confidence}
                    for h in top_hypotheses[1:3]
                ]) if top_hypotheses else [],
                'raw_llm_analysis': llm_analysis.get('raw_analysis', ''),
                'all_hypotheses_pruned': all_pruned
            }
            return result
        except Exception as e:
            logger.error(f"LLM final analysis failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM final analysis failed: {e}. Please check your API key and try again.")
    
    # _get_mitigation_strategies() and _get_next_steps() methods removed
    # All mitigation and next steps are now generated by LLM

