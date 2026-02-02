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
from bayesian_pruner import BayesianPruner

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
    
    def to_dict(self) -> Dict:
        """Convert Hypothesis to dictionary for MongoDB storage."""
        return {
            "id": self.id,
            "description": self.description,
            "category": self.category,
            "prior_score": self.prior_score,
            "evidence": self.evidence.copy() if self.evidence else [],
            "rule_score": self.rule_score,
            "llm_score": self.llm_score,
            "user_feedback": self.user_feedback,
            "confidence": self.confidence,
            "status": self.status
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Hypothesis':
        """Create Hypothesis from dictionary."""
        return cls(
            id=data["id"],
            description=data["description"],
            category=data["category"],
            prior_score=data["prior_score"],
            evidence=data.get("evidence", []),
            rule_score=data.get("rule_score", 0.0),
            llm_score=data.get("llm_score", 0.0),
            user_feedback=data.get("user_feedback", 0.0),
            confidence=data.get("confidence", 0.0),
            status=data.get("status", "active")
        )


@dataclass
class ReasoningNode:
    """A node in the Tree-of-Thought representing a reasoning step.
    
    Each node belongs to a specific hypothesis branch (identified by hypothesis_id).
    The root node (step 1) has hypothesis_id=None and contains all initial hypotheses.
    Subsequent nodes belong to specific hypothesis branches.
    """
    id: str
    step_number: int
    hypothesis_id: Optional[str] = None  # Which hypothesis branch this node belongs to (None for root)
    hypothesis: Optional[Hypothesis] = None  # The hypothesis for this branch (None for root)
    requested_data: List[str] = field(default_factory=list)
    artifacts_received: List[Dict] = field(default_factory=list)
    evaluation_summary: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    branch_status: str = "active"  # active, pruned - status of this branch node
    
    # Evaluation and pruning details for transparency
    evaluation_details: Optional[Dict] = None  # Stores detailed LLM evaluation reasoning
    pruning_details: Optional[Dict] = None  # Stores pruning logic if pruned
    
    # Legacy field for backward compatibility (root node only)
    hypotheses: List[Hypothesis] = field(default_factory=list)
    
    # Child hypotheses created via node expansion (not in root)
    child_hypotheses: List[Hypothesis] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert ReasoningNode to dictionary for MongoDB storage."""
        result = {
            "node_id": self.id,
            "step_number": self.step_number,
            "hypothesis_id": self.hypothesis_id,
            "parent_node_id": self.parent_id,
            "children_node_ids": self.children_ids.copy() if self.children_ids else [],
            "branch_status": self.branch_status,
            "requested_data": self.requested_data.copy() if self.requested_data else [],
            "evaluation_summary": self.evaluation_summary,
            "timestamp": self.timestamp,
            "evaluation_details": self.evaluation_details,
            "pruning_details": self.pruning_details
        }
        
        # Add hypothesis if present
        if self.hypothesis:
            result["hypothesis"] = self.hypothesis.to_dict()
        
        # Add initial hypotheses (for root node)
        if self.hypotheses:
            result["initial_hypotheses"] = [h.to_dict() for h in self.hypotheses]
        
        # Add child hypotheses (for expanded nodes)
        if self.child_hypotheses:
            result["child_hypotheses"] = [h.to_dict() for h in self.child_hypotheses]
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ReasoningNode':
        """Create ReasoningNode from dictionary."""
        # Reconstruct hypothesis if present
        hypothesis = None
        if "hypothesis" in data and data["hypothesis"]:
            hypothesis = Hypothesis.from_dict(data["hypothesis"])
        
        # Reconstruct initial hypotheses if present
        hypotheses = []
        if "initial_hypotheses" in data and data["initial_hypotheses"]:
            hypotheses = [Hypothesis.from_dict(h) for h in data["initial_hypotheses"]]
        
        # Reconstruct child hypotheses if present
        child_hypotheses = []
        if "child_hypotheses" in data and data["child_hypotheses"]:
            child_hypotheses = [Hypothesis.from_dict(h) for h in data["child_hypotheses"]]
        
        # Handle timestamp (can be datetime or ISO string)
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now()
        elif timestamp is None:
            timestamp = datetime.now()
        
        return cls(
            id=data["node_id"],
            step_number=data["step_number"],
            hypothesis_id=data.get("hypothesis_id"),
            hypothesis=hypothesis,
            parent_id=data.get("parent_node_id"),
            children_ids=data.get("children_node_ids", []),
            branch_status=data.get("branch_status", "active"),
            requested_data=data.get("requested_data", []),
            evaluation_summary=data.get("evaluation_summary", ""),
            timestamp=timestamp,
            evaluation_details=data.get("evaluation_details"),
            pruning_details=data.get("pruning_details"),
            hypotheses=hypotheses,
            child_hypotheses=child_hypotheses
        )


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
    PRUNE_THRESHOLD = 0.15  # Bayesian approach uses 15% threshold
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
        self.root_node_id: Optional[str] = None  # Root node (contains all initial hypotheses)
        self.current_node_id: Optional[str] = None  # Current active node (latest leaf node after artifact processing)
        self.current_branch_ids: List[str] = []  # Currently selected branches for focused evaluation
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.problem_summary: str = ""
        self.step_counter: int = 0
        self.llm_integration = llm_integration  # LLM integration instance
        self.all_hypotheses: Dict[str, Hypothesis] = {}  # Track all hypotheses by ID
    
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
                logger.info("Calling LLM to generate hypotheses...")
                llm_result = self.llm_integration.generate_hypotheses_from_llm(problem_summary)
                llm_hypotheses = llm_result.get('hypotheses', [])
                requested_data = llm_result.get('next_requests', [])
                
                logger.info(f"LLM returned {len(llm_hypotheses)} hypotheses")
                if llm_hypotheses:
                    logger.info(f"Using LLM-generated hypotheses")
                else:
                    logger.warning("LLM returned empty hypotheses list, will fall back to hardcoded")
                
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
        
        # Store all hypotheses for branch tracking
        for hyp in initial_hypotheses:
            self.all_hypotheses[hyp.id] = hyp
        
        # Create root node with all hypotheses
        initial_node = ReasoningNode(
            id="node_1",
            step_number=1,
            hypothesis_id=None,  # Root node
            hypotheses=initial_hypotheses,  # All hypotheses in root
            requested_data=requested_data
        )
        
        self.nodes.append(initial_node)
        self.root_node_id = initial_node.id
        self.current_node_id = initial_node.id  # Set root as initial current node
        
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
    
    def get_active_branches(self) -> List[Tuple[str, ReasoningNode]]:
        """
        Get all active branches using tree traversal.
        Returns list of (hypothesis_id, leaf_node) tuples for each active branch.
        """
        if not self.root_node_id:
            return []
        
        active_branches = []
        
        # Get all active hypotheses by traversing the tree (includes child_hypotheses)
        active_hypotheses = self.get_all_active_hypotheses_from_tree()
        
        for hyp in active_hypotheses:
            # Find the leaf node for this hypothesis branch
            leaf_node = self._get_branch_leaf(hyp.id)
            if leaf_node and leaf_node.branch_status == "active":
                active_branches.append((hyp.id, leaf_node))
        
        return active_branches
    
    def _get_branch_leaf(self, hypothesis_id: str) -> Optional[ReasoningNode]:
        """Get the leaf node (most recent node) for a given hypothesis branch."""
        # Find all nodes for this branch, sorted by step_number
        branch_nodes = [
            node for node in self.nodes
            if node.hypothesis_id == hypothesis_id and node.branch_status == "active"
        ]
        
        if not branch_nodes:
            return None
        
        # Return the node with highest step_number (leaf)
        return max(branch_nodes, key=lambda n: n.step_number)
    
    def get_branch_path(self, hypothesis_id: str) -> List[ReasoningNode]:
        """Get the full path from root to leaf for a given hypothesis branch."""
        path = []
        leaf = self._get_branch_leaf(hypothesis_id)
        
        if not leaf:
            # Branch hasn't started yet, just return root
            if self.root_node_id:
                return [self._get_node(self.root_node_id)]
            return []
        
        # Build path from leaf to root
        current = leaf
        while current:
            path.insert(0, current)
            if current.parent_id:
                current = self._get_node(current.parent_id)
            else:
                break
        
        return path
    
    def get_all_branches_for_ui(self) -> List[Dict]:
        """
        Get all branches (active and pruned) for UI display using tree traversal.
        Returns list of branch dictionaries with full path information.
        Now includes ALL hypotheses from the tree (root + expanded child_hypotheses).
        """
        if not self.root_node_id:
            return []
        
        branches = []
        
        # Get ALL hypotheses from the tree (not just root) - includes expanded ones
        all_hypotheses = self.get_all_hypotheses_from_tree()
        
        for hyp in all_hypotheses:
            branch_path = self.get_branch_path(hyp.id)
            
            # Build branch info
            branch_info = {
                'hypothesis_id': hyp.id,
                'hypothesis': {
                    'id': hyp.id,
                    'description': hyp.description,
                    'category': hyp.category,
                    'confidence': hyp.confidence,
                    'status': hyp.status
                },
                'status': hyp.status,  # active, pruned, accepted
                'path': [
                    {
                        'node_id': node.id,
                        'step_number': node.step_number,
                        'artifacts': [art['name'] for art in node.artifacts_received],
                        'timestamp': node.timestamp.isoformat() if isinstance(node.timestamp, datetime) else node.timestamp
                    }
                    for node in branch_path
                ],
                'leaf_node_id': branch_path[-1].id if branch_path else None,
                'depth': len(branch_path)
            }
            
            branches.append(branch_info)
        
        return branches
    
    def add_artifact(self, artifact_name: str, artifact_content: str, branch_ids: Optional[List[str]] = None) -> List[ReasoningNode]:
        """
        Add an artifact and create new nodes in all active branches (or specified branches).
        
        Args:
            artifact_name: Name of the artifact
            artifact_content: Content of the artifact
            branch_ids: Optional list of specific hypothesis IDs to evaluate. 
                       If None, uses current_branch_ids if set (from backtrack), 
                       otherwise evaluates all active branches.
        
        Returns:
            List of newly created nodes (one per branch)
        """
        if not self.root_node_id:
            raise ValueError("Engine not initialized. Call initialize() first.")
        
        # Get active branches to evaluate - use tree traversal to get ALL active hypotheses
        # (including expanded ones from child_hypotheses, not just root node hypotheses)
        root_node = self._get_node(self.root_node_id)
        active_hypotheses = self.get_all_active_hypotheses_from_tree()
        
        # If branch_ids not explicitly provided, check if we're in focused mode (from backtrack)
        if branch_ids is None and self.current_branch_ids:
            # Use focused branches from backtrack
            branch_ids = self.current_branch_ids.copy()
            # Filter to only include active hypotheses
            branch_ids = [bid for bid in branch_ids if any(h.id == bid and h.status == "active" for h in active_hypotheses)]
            if not branch_ids:
                # All focused branches are pruned, clear focus and fall back to all active
                self.current_branch_ids = []
                branch_ids = None
                # If there are no active hypotheses at all, we'll raise an error below
                if not active_hypotheses:
                    raise ValueError(
                        "The focused branch has been pruned and there are no active branches remaining. "
                        "Please unfocus or restore a branch to continue."
                    )
        
        if branch_ids is not None:
            active_hypotheses = [h for h in active_hypotheses if h.id in branch_ids]
        
        if not active_hypotheses:
            # Provide more helpful error message
            if self.current_branch_ids:
                raise ValueError(
                    f"The focused branch(s) {self.current_branch_ids} have been pruned. "
                    "Please unfocus to evaluate all active branches, or restore a branch to continue."
                )
            else:
                raise ValueError(
                    "No active branches to evaluate. All hypotheses have been pruned. "
                    "Please restore a branch or initialize a new session."
                )
        
        # Determine parent nodes for each branch
        # If this is the first artifact (no branch nodes exist yet), use root as parent
        # Otherwise, use leaf nodes from existing branches
        active_branches = []
        for hyp in active_hypotheses:
            leaf_node = self._get_branch_leaf(hyp.id)
            if leaf_node:
                # Branch already exists, use leaf as parent
                active_branches.append((hyp.id, leaf_node))
            else:
                # First node in this branch, use root as parent
                active_branches.append((hyp.id, root_node))
        
        self.step_counter += 1
        new_nodes = []
        
        # Create new nodes for each active branch
        for hypothesis_id, parent_node in active_branches:
            # Get the hypothesis for this branch
            hypothesis = self.all_hypotheses.get(hypothesis_id)
            if not hypothesis or hypothesis.status != "active":
                continue
            
            # Create a copy of the hypothesis with current state
            branch_hypothesis = Hypothesis(
                id=hypothesis.id,
                description=hypothesis.description,
                category=hypothesis.category,
                prior_score=hypothesis.prior_score,
                evidence=hypothesis.evidence.copy(),
                rule_score=hypothesis.rule_score,
                llm_score=hypothesis.llm_score,
                user_feedback=hypothesis.user_feedback,
                confidence=hypothesis.confidence,
                status=hypothesis.status
            )
            
            # Create new node for this branch
            new_node = ReasoningNode(
                id=f"node_{self.step_counter}_{hypothesis_id}",
                step_number=self.step_counter,
                hypothesis_id=hypothesis_id,
                hypothesis=branch_hypothesis,
                parent_id=parent_node.id,
                artifacts_received=[{
                    'name': artifact_name,
                    'content': artifact_content,
                    'timestamp': datetime.now().isoformat()
                }]
            )
            
            new_nodes.append(new_node)
            parent_node.children_ids.append(new_node.id)
            self.nodes.append(new_node)
        
        # Batch evaluate all branches with LLM in one call
        if not self.llm_integration or not self.llm_integration.use_llm:
            raise ValueError("LLM is required for artifact evaluation. Please ensure OPENAI_API_KEY is set.")
        
        try:
            # Evaluate all active branches together
            logger.info(f"Calling LLM to evaluate {len(new_nodes)} branches with artifact: {artifact_name}")
            logger.info(f"Using LLM provider: {self.llm_integration.provider_name} ({self.llm_integration.model_name})")
            evaluation_results = self.llm_integration.evaluate_branches_with_llm(
                new_nodes, artifact_content, self.problem_summary
            )
            logger.info(f"LLM evaluation completed. Results for {len(evaluation_results)} branches")
            
            # Check if using Bayesian approach (Groq adapter returns likelihood_score)
            use_bayesian = any(
                'likelihood_score' in evaluation_results.get(hyp_id, {})
                for hyp_id in evaluation_results.keys()
            )
            
            # Update each branch's hypothesis with evaluation results
            for new_node in new_nodes:
                hyp_id = new_node.hypothesis_id
                if hyp_id not in evaluation_results:
                    continue
                
                result = evaluation_results[hyp_id]
                
                # Store previous confidence for evaluation details (from master hypothesis before update)
                master_hyp = self.all_hypotheses.get(hyp_id)
                previous_confidence = master_hyp.confidence if master_hyp else (new_node.hypothesis.confidence if new_node.hypothesis else 0.0)
                
                # Update the hypothesis in the node
                if new_node.hypothesis:
                    category = new_node.hypothesis.category
                    
                    if use_bayesian and 'likelihood_score' in result:
                        # Bayesian Evidence Screening approach
                        likelihood_score = result.get('likelihood_score', 0)  # -10 to +10
                        reasoning = result.get('llm_reasoning', '')
                        evidence_map = result.get('evidence', {})
                        
                        # Convert previous confidence from 0-1 to 0-100 for Bayesian calculation
                        previous_confidence_percent = previous_confidence * 100.0
                        
                        # Calculate posterior using Bayesian update
                        new_confidence_percent = BayesianPruner.calculate_posterior(
                            previous_confidence_percent, 
                            likelihood_score
                        )
                        
                        # Convert back to 0-1 scale
                        new_confidence = new_confidence_percent / 100.0
                        
                        # Update hypothesis confidence
                        new_node.hypothesis.confidence = new_confidence
                        
                        # Store likelihood score as llm_score for reference
                        new_node.hypothesis.llm_score = likelihood_score / 10.0  # Normalize to -1 to 1
                        
                        # Add evidence
                        if category in evidence_map:
                            new_node.hypothesis.evidence.append(evidence_map[category])
                        elif reasoning:
                            new_node.hypothesis.evidence.append(reasoning)
                        
                        # Note: Hypotheses are NOT automatically accepted - only confidence is updated
                        # Acceptance should be done manually after final analysis
                        
                        # Store evaluation details
                        new_node.evaluation_details = {
                            'llm_reasoning': reasoning,
                            'evidence_found': evidence_map.get(category, reasoning),
                            'evidence_summary': result.get('evidence_summary', ''),
                            'confidence_before': previous_confidence,
                            'confidence_after': new_node.hypothesis.confidence,
                            'confidence_change': new_node.hypothesis.confidence - previous_confidence,
                            'likelihood_score': likelihood_score,  # Store likelihood score
                            'status': result.get('status', 'neutral'),
                            'artifact_name': artifact_name,
                            'evaluated_at': datetime.now().isoformat(),
                            'update_method': 'bayesian'
                        }
                        
                    else:
                        # Traditional approach (OpenAI adapter)
                        scores = result.get('scores', {})
                        evidence_map = result.get('evidence', {})
                        
                        if category in scores:
                            new_node.hypothesis.llm_score = scores[category]
                        if category in evidence_map:
                            new_node.hypothesis.evidence.append(evidence_map[category])
                        
                        # Update confidence using traditional method
                        new_node.hypothesis.update_confidence(self.weights)
                        
                        # Note: Hypotheses are NOT automatically accepted - only confidence is updated
                        # Acceptance should be done manually after final analysis
                        
                        # Store evaluation details
                        new_node.evaluation_details = {
                            'llm_reasoning': result.get('llm_reasoning', ''),
                            'evidence_found': evidence_map.get(category, ''),
                            'evidence_summary': result.get('evidence_summary', ''),
                            'confidence_before': previous_confidence,
                            'confidence_after': new_node.hypothesis.confidence,
                            'confidence_change': new_node.hypothesis.confidence - previous_confidence,
                            'status': result.get('status', 'neutral'),
                            'artifact_name': artifact_name,
                            'evaluated_at': datetime.now().isoformat(),
                            'update_method': 'traditional'
                        }
                    
                    # Update the master hypothesis tracking
                    self.all_hypotheses[hyp_id].llm_score = new_node.hypothesis.llm_score
                    self.all_hypotheses[hyp_id].evidence = new_node.hypothesis.evidence.copy()
                    self.all_hypotheses[hyp_id].confidence = new_node.hypothesis.confidence
                    self.all_hypotheses[hyp_id].status = new_node.hypothesis.status
                    
        except Exception as e:
            logger.error(f"LLM artifact evaluation failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM evaluation failed: {e}. Please check your API key and try again.")
        
        # Update current_node_id to the latest created nodes (leaf nodes)
        # If multiple branches, use the one with highest confidence, or first one
        if new_nodes:
            # Sort by confidence (highest first) and use the best one as current
            sorted_nodes = sorted(new_nodes, key=lambda n: n.hypothesis.confidence if n.hypothesis else 0, reverse=True)
            self.current_node_id = sorted_nodes[0].id
        
        return new_nodes
    
    # _evaluate_artifacts() method removed - LLM evaluation is now required
    
    def prune_hypotheses(self, evaluated_branch_ids: Optional[List[str]] = None):
        """
        Prune low-confidence hypotheses (branches).
        
        Keeps at least the top 2 highest-scored hypotheses unless their confidence
        is less than 5% (0.05). Prunes entire branches, not just individual nodes.
        Now checks ALL hypotheses from the tree (including child_hypotheses from expansion).
        
        Args:
            evaluated_branch_ids: Optional list of hypothesis IDs that were just evaluated.
                                If provided, only these branches will be considered for pruning.
                                If None, all active hypotheses are considered (default behavior).
        """
        # Get ALL active hypotheses from the tree (not just root)
        active_hypotheses = self.get_all_active_hypotheses_from_tree()
        
        # If specific branches were evaluated, only consider those for pruning
        if evaluated_branch_ids is not None:
            active_hypotheses = [h for h in active_hypotheses if h.id in evaluated_branch_ids]
        
        if not active_hypotheses:
            return
        
        # Ensure all hypotheses are in master tracking (safety check)
        for hyp in active_hypotheses:
            if hyp.id not in self.all_hypotheses:
                logger.warning(f"Active hypothesis {hyp.id} not in all_hypotheses, adding it")
                self.all_hypotheses[hyp.id] = hyp
        
        # Sort by confidence (highest first) - use current confidence from master tracking
        # Refresh confidence from master to ensure we have latest values
        for hyp in active_hypotheses:
            master_hyp = self.all_hypotheses.get(hyp.id)
            if master_hyp:
                # Use master's confidence (source of truth)
                hyp.confidence = master_hyp.confidence
        
        sorted_hypotheses = sorted(active_hypotheses, key=lambda x: x.confidence, reverse=True)
        
        # Keep at least the top 2 hypotheses
        min_keep_count = min(2, len(sorted_hypotheses))
        top_hypotheses = sorted_hypotheses[:min_keep_count]
        
        # Prune hypotheses that are below threshold, but protect top 2 unless they're < 5%
        MIN_PROTECTED_CONFIDENCE = 0.05  # 5%
        
        for hypothesis in sorted_hypotheses:
            # Get latest confidence from master tracking
            master_hyp = self.all_hypotheses.get(hypothesis.id)
            current_confidence = master_hyp.confidence if master_hyp else hypothesis.confidence
            
            # Determine pruning reason and threshold
            pruning_reason = None
            threshold_used = None
            was_top_hypothesis = hypothesis in top_hypotheses
            
            # If it's in the top 2, only prune if confidence < 5%
            if hypothesis in top_hypotheses:
                if current_confidence < MIN_PROTECTED_CONFIDENCE:
                    pruning_reason = f"Top hypothesis but confidence {current_confidence:.2%} below minimum protected threshold ({MIN_PROTECTED_CONFIDENCE:.0%})"
                    threshold_used = MIN_PROTECTED_CONFIDENCE
                    logger.info(f"Pruning top hypothesis {hypothesis.id} with confidence {current_confidence:.2%} (< 5%)")
                    self.prune_branch(hypothesis.id, pruning_reason, threshold_used, current_confidence, was_top_hypothesis)
            # Otherwise, prune if below normal threshold (15% for Bayesian, 30% for traditional)
            else:
                if current_confidence < self.PRUNE_THRESHOLD:
                    pruning_reason = f"Confidence {current_confidence:.2%} below pruning threshold ({self.PRUNE_THRESHOLD:.0%})"
                    threshold_used = self.PRUNE_THRESHOLD
                    logger.info(f"Pruning hypothesis {hypothesis.id} with confidence {current_confidence:.2%} (< {self.PRUNE_THRESHOLD:.0%})")
                    self.prune_branch(hypothesis.id, pruning_reason, threshold_used, current_confidence, was_top_hypothesis)
    
    def prune_branch(self, hypothesis_id: str, pruning_reason: Optional[str] = None, 
                     threshold_used: Optional[float] = None, confidence_at_pruning: Optional[float] = None,
                     was_top_hypothesis: bool = False):
        """
        Prune an entire branch by marking all nodes in that branch as pruned.
        The branch is kept in memory but excluded from active traversal.
        Also updates child_hypotheses in parent nodes.
        
        Args:
            hypothesis_id: The hypothesis ID to prune
            pruning_reason: Optional reason why this branch was pruned
            threshold_used: Optional threshold value that triggered pruning
            confidence_at_pruning: Optional confidence value at time of pruning
            was_top_hypothesis: Whether this was in the top 2 hypotheses
        """
        # Always update master hypothesis tracking first (source of truth)
        hypothesis = self.all_hypotheses.get(hypothesis_id)
        if not hypothesis:
            # Hypothesis not in master tracking - this shouldn't happen, but handle gracefully
            logger.warning(f"Hypothesis {hypothesis_id} not found in all_hypotheses during pruning")
            # Still try to update other references
        else:
            hypothesis.status = "pruned"
        
        # Store pruning details in the leaf node (most recent node in the branch)
        leaf_node = self._get_branch_leaf(hypothesis_id)
        if leaf_node and (pruning_reason or threshold_used is not None):
            leaf_node.pruning_details = {
                'pruned_at': datetime.now().isoformat(),
                'reason': pruning_reason or 'Branch pruned due to low confidence',
                'threshold_used': threshold_used,
                'confidence_at_pruning': confidence_at_pruning or (hypothesis.confidence if hypothesis else 0.0),
                'was_top_hypothesis': was_top_hypothesis
            }
        
        # Mark all nodes in this branch as pruned
        for node in self.nodes:
            if node.hypothesis_id == hypothesis_id:
                node.branch_status = "pruned"
                # Also update the hypothesis object in the node if it exists
                if node.hypothesis and node.hypothesis.id == hypothesis_id:
                    node.hypothesis.status = "pruned"
        
        # Also update root node's hypothesis list
        root_node = self._get_node(self.root_node_id)
        for hyp in root_node.hypotheses:
            if hyp.id == hypothesis_id:
                hyp.status = "pruned"
                # Ensure master tracking is also updated
                if hypothesis:
                    hyp.status = "pruned"
                break
        
        # Update child_hypotheses in any parent nodes that have this hypothesis
        for node in self.nodes:
            if hasattr(node, 'child_hypotheses') and node.child_hypotheses:
                for hyp in node.child_hypotheses:
                    if hyp.id == hypothesis_id:
                        hyp.status = "pruned"
                        # Ensure master tracking is also updated
                        master_hyp = self.all_hypotheses.get(hyp.id)
                        if master_hyp:
                            master_hyp.status = "pruned"
                        elif not hypothesis:
                            # If master wasn't found earlier, try to add it now
                            self.all_hypotheses[hyp.id] = hyp
                            hyp.status = "pruned"
                        break
    
    def unprune_branch(self, hypothesis_id: str):
        """Unprune a branch, making it active again."""
        hypothesis = self.all_hypotheses.get(hypothesis_id)
        if hypothesis:
            hypothesis.status = "active"
        
        # Mark all nodes in this branch as active
        for node in self.nodes:
            if node.hypothesis_id == hypothesis_id:
                node.branch_status = "active"
                # Also update the hypothesis object in the node if it exists
                if node.hypothesis and node.hypothesis.id == hypothesis_id:
                    node.hypothesis.status = "active"
        
        # Also update root node's hypothesis list
        root_node = self._get_node(self.root_node_id)
        if root_node:
            for hyp in root_node.hypotheses:
                if hyp.id == hypothesis_id:
                    hyp.status = "active"
                    # Ensure master tracking is also updated
                    if hypothesis:
                        hyp.status = "active"
                    break
        
        # Update child_hypotheses in any parent nodes that have this hypothesis
        for node in self.nodes:
            if hasattr(node, 'child_hypotheses') and node.child_hypotheses:
                for hyp in node.child_hypotheses:
                    if hyp.id == hypothesis_id:
                        hyp.status = "active"
                        # Also update in master tracking
                        master_hyp = self.all_hypotheses.get(hyp.id)
                        if master_hyp:
                            master_hyp.status = "active"
                        break
    
    def backtrack(self, node_id: Optional[str] = None, hypothesis_id: Optional[str] = None, auto_restore: bool = True) -> Tuple[ReasoningNode, bool]:
        """
        Backtrack to a previous node or set focus on a specific branch.
        When backtracking, future artifact evaluations will focus on the backtracked branch.
        If the branch is pruned, it will be auto-restored (if auto_restore=True).
        Use unfocus() to return to evaluating all active branches.
        
        Args:
            node_id: Specific node to backtrack to (will focus on that node's branch)
            hypothesis_id: Focus on a specific hypothesis branch (sets current_branch_ids)
            auto_restore: If True, automatically restore pruned branches when backtracking
        
        Returns:
            Tuple of (the node that was backtracked to, whether branch was restored)
        """
        restored = False
        if node_id:
            node = self._get_node(node_id)
            # Set current node to the backtracked node
            self.current_node_id = node_id
            # Set current branch focus to this node's branch (if it has one)
            if node.hypothesis_id:
                # Check if the hypothesis is still active
                root_node = self._get_node(self.root_node_id)
                hyp = next((h for h in root_node.hypotheses if h.id == node.hypothesis_id), None)
                if hyp:
                    if hyp.status != "active":
                        # Hypothesis is pruned - auto-restore if requested
                        if auto_restore:
                            self.unprune_branch(node.hypothesis_id)
                            restored = True
                        else:
                            # Don't restore, just clear focus
                            self.current_branch_ids = []
                            return (node, False)
                    # Set focus on this branch (now active)
                    self.current_branch_ids = [node.hypothesis_id]
                else:
                    # Hypothesis not found in root - clear focus
                    self.current_branch_ids = []
            else:
                # Root node or node without hypothesis - evaluate all branches
                self.current_branch_ids = []
            return (node, restored)
        elif hypothesis_id:
            # Focus on specific branch
            # Check if hypothesis is still active
            root_node = self._get_node(self.root_node_id)
            hyp = next((h for h in root_node.hypotheses if h.id == hypothesis_id), None)
            if not hyp:
                raise ValueError(f"Hypothesis {hypothesis_id} does not exist")
            
            if hyp.status != "active":
                # Hypothesis is pruned - auto-restore if requested
                if auto_restore:
                    self.unprune_branch(hypothesis_id)
                    restored = True
                else:
                    raise ValueError(f"Hypothesis {hypothesis_id} is pruned. Set auto_restore=True to restore it.")
            
            self.current_branch_ids = [hypothesis_id]
            leaf = self._get_branch_leaf(hypothesis_id)
            target_node = leaf if leaf else self._get_node(self.root_node_id)
            # Set current node to the target node
            self.current_node_id = target_node.id
            return (target_node, restored)
        else:
            raise ValueError("Either node_id or hypothesis_id must be provided")
    
    def unfocus(self):
        """
        Clear branch focus and return to evaluating all active branches.
        This undoes the focus set by backtrack().
        """
        self.current_branch_ids = []
    
    def expand_node(self, node_id: str) -> List[ReasoningNode]:
        """
        Expand a node by generating new sub-hypotheses or exploration directions from it.
        Creates new child nodes with new hypotheses to explore.
        
        Args:
            node_id: The node to expand from
        
        Returns:
            List of newly created child nodes
        """
        if not self.root_node_id:
            raise ValueError("Engine not initialized. Call initialize() first.")
        
        if not self.llm_integration or not self.llm_integration.use_llm:
            raise ValueError("LLM is required for node expansion. Please ensure OPENAI_API_KEY is set.")
        
        # Get the node to expand
        parent_node = self._get_node(node_id)
        
        # Generate new sub-hypotheses from this node
        try:
            expansion_result = self.llm_integration.generate_sub_hypotheses_from_node(parent_node, self)
            new_hypotheses_data = expansion_result.get('hypotheses', [])
            new_requests = expansion_result.get('next_requests', [])
        except Exception as e:
            logger.error(f"Failed to generate sub-hypotheses: {e}", exc_info=True)
            raise ValueError(f"Failed to generate new ideas from node: {e}")
        
        if not new_hypotheses_data:
            raise ValueError("No new exploration directions were generated. The LLM may need more context.")
        
        # Create new hypotheses
        new_hypotheses = []
        for hyp_data in new_hypotheses_data:
            hyp = Hypothesis(
                id=f"hyp_{len(self.all_hypotheses) + 1}",
                description=hyp_data['description'],
                category=hyp_data['category'],
                prior_score=hyp_data.get('prior_score', hyp_data.get('confidence', 0.5)),
                confidence=hyp_data['confidence']
            )
            if 'rationale' in hyp_data and hyp_data['rationale']:
                hyp.evidence.append(f"Exploration rationale: {hyp_data['rationale']}")
            new_hypotheses.append(hyp)
            self.all_hypotheses[hyp.id] = hyp
        
        # Add new hypotheses to the parent node's child_hypotheses (not root)
        # Find the parent node in the nodes list and update it
        for n in self.nodes:
            if n.id == parent_node.id:
                n.child_hypotheses.extend(new_hypotheses)
                break
        
        # Create new child nodes (one per new hypothesis)
        self.step_counter += 1
        new_nodes = []
        
        for hypothesis in new_hypotheses:
            new_node = ReasoningNode(
                id=f"node_{len(self.nodes) + 1}",
                step_number=self.step_counter,
                hypothesis_id=hypothesis.id,
                hypothesis=hypothesis,
                parent_id=parent_node.id,
                requested_data=new_requests.copy() if new_requests else [],
                evaluation_summary=f"New exploration direction generated from step {parent_node.step_number}"
            )
            
            # Add to parent's children
            for n in self.nodes:
                if n.id == parent_node.id:
                    n.children_ids.append(new_node.id)
                    break
            
            self.nodes.append(new_node)
            new_nodes.append(new_node)
        
        # Update current_node_id to the first new node (or keep it at parent if preferred)
        if new_nodes:
            # Optionally set current to first new node, or keep at parent
            # For now, keep at parent so user can see the expansion
            pass
        
        return new_nodes
    
    def should_auto_backtrack(self) -> Optional[Dict]:
        """
        Modular auto-backtrack detection logic for branch-based structure.
        Returns None if no backtrack needed, or dict with backtrack recommendation.
        Does not modify state - only analyzes and recommends.
        """
        root_node = self.get_current_node()
        if not root_node:
            return None
        
        active_hypotheses = [h for h in root_node.hypotheses if h.status == "active"]
        
        # Check 1: Dead-end detection - all hypotheses pruned
        if not active_hypotheses:
            return {
                'reason': 'dead_end',
                'message': 'All hypotheses have been pruned. No active hypotheses remaining.',
                'recommended_hypothesis_id': None
            }
        
        # Check 2: Very low confidence - all active hypotheses below threshold
        if active_hypotheses:
            max_confidence = max(h.confidence for h in active_hypotheses)
            if max_confidence < 0.15:  # Very low confidence threshold
                # Find best previous step by looking at branch histories
                best_hyp_id = None
                best_confidence = 0.0
                for hyp in active_hypotheses:
                    branch_path = self.get_branch_path(hyp.id)
                    # Look for earlier nodes with higher confidence
                    for node in reversed(branch_path):
                        if node.hypothesis and node.hypothesis.confidence > best_confidence:
                            best_confidence = node.hypothesis.confidence
                            best_hyp_id = hyp.id
                
                if best_hyp_id and best_confidence > max_confidence:
                    return {
                        'reason': 'low_confidence',
                        'message': f'All hypotheses have very low confidence ({max_confidence:.1%}). Previous steps had better results.',
                        'recommended_hypothesis_id': best_hyp_id,
                        'current_max_confidence': max_confidence,
                        'previous_max_confidence': best_confidence
                    }
        
        # Check 3: Stagnation - no improvement in recent steps
        if len(self.nodes) >= 4:
            # Get recent step numbers
            recent_steps = sorted(set(n.step_number for n in self.nodes), reverse=True)[:4]
            recent_confidences = []
            for step in reversed(recent_steps):
                # Get max confidence across all active branches at this step
                step_nodes = [n for n in self.nodes if n.step_number == step and n.hypothesis and n.branch_status == "active"]
                if step_nodes:
                    step_max = max(n.hypothesis.confidence for n in step_nodes)
                    recent_confidences.append(step_max)
            
            if len(recent_confidences) >= 3:
                # Check if confidence is declining or stagnant
                if recent_confidences[-1] <= recent_confidences[0] and recent_confidences[-1] < 0.5:
                    return {
                        'reason': 'stagnation',
                        'message': 'No significant improvement in recent steps. Confidence has stagnated or declined.',
                        'confidence_trend': recent_confidences
                    }
        
        return None
    
    def get_next_requests(self) -> List[str]:
        """Generate next data requests using LLM based on current state of all active branches."""
        root_node = self.get_current_node()
        if not root_node:
            raise ValueError("Engine not initialized")
        
        # LLM is REQUIRED for generating requests
        if not self.llm_integration or not self.llm_integration.use_llm:
            raise ValueError("LLM is required for generating next requests. Please ensure OPENAI_API_KEY is set.")
        
        try:
            # Get all active branch leaf nodes for context
            active_branches = self.get_active_branches()
            # Use root node for request generation (contains all hypotheses)
            requests = self.llm_integration.generate_next_requests_llm(root_node, self.problem_summary)
            # Add to requested_data to track what we've asked for
            for req in requests:
                if req not in root_node.requested_data:
                    root_node.requested_data.append(req)
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
        """Get the current active node (latest leaf node after artifact processing, or root if not set)."""
        if not self.root_node_id:
            return None
        
        # If no nodes exist, return None (session might be corrupted)
        if not self.nodes:
            logger.warning(f"No nodes found in engine. Root node ID: {self.root_node_id}")
            return None
        
        # If current_node_id is set, return that node; otherwise return root
        if self.current_node_id:
            try:
                return self._get_node(self.current_node_id)
            except ValueError:
                # If current_node_id is invalid, fall back to root
                try:
                    return self._get_node(self.root_node_id)
                except ValueError:
                    # If root node also not found, return first node or None
                    logger.warning(f"Neither current_node_id ({self.current_node_id}) nor root_node_id ({self.root_node_id}) found in nodes")
                    return self.nodes[0] if self.nodes else None
        try:
            return self._get_node(self.root_node_id)
        except ValueError:
            # If root node not found, return first node or None
            logger.warning(f"Root node {self.root_node_id} not found in nodes")
            return self.nodes[0] if self.nodes else None
    
    def get_all_active_hypotheses_from_tree(self) -> List[Hypothesis]:
        """
        Traverse the entire tree and collect all active hypotheses from all nodes.
        This includes hypotheses from root node and all child nodes created via expansion.
        Uses master hypothesis status from self.all_hypotheses to ensure pruning is respected.
        
        Returns:
            List of all active hypotheses found in the tree
        """
        active_hypotheses = []
        seen_hypothesis_ids = set()
        
        # If no nodes, return empty list
        if not self.nodes:
            return []
        
        # Traverse all nodes in the tree
        for node in self.nodes:
            # Check if node has a hypothesis
            if node.hypothesis and node.hypothesis.id not in seen_hypothesis_ids:
                # Check master hypothesis status (pruning updates this)
                master_hyp = self.all_hypotheses.get(node.hypothesis.id)
                if master_hyp and master_hyp.status == "active" and node.branch_status == "active":
                    active_hypotheses.append(master_hyp)
                    seen_hypothesis_ids.add(node.hypothesis.id)
            
            # Check if node has child_hypotheses (from expansion)
            if hasattr(node, 'child_hypotheses') and node.child_hypotheses:
                for hyp in node.child_hypotheses:
                    if hyp.id not in seen_hypothesis_ids:
                        # Check master hypothesis status
                        master_hyp = self.all_hypotheses.get(hyp.id)
                        if master_hyp and master_hyp.status == "active":
                            active_hypotheses.append(master_hyp)
                            seen_hypothesis_ids.add(hyp.id)
        
        # Also check root node's hypotheses (initial hypotheses)
        if self.root_node_id:
            root_node = self._get_node(self.root_node_id)
            for hyp in root_node.hypotheses:
                if hyp.id not in seen_hypothesis_ids:
                    # Check master hypothesis status
                    master_hyp = self.all_hypotheses.get(hyp.id)
                    if master_hyp and master_hyp.status == "active":
                        active_hypotheses.append(master_hyp)
                        seen_hypothesis_ids.add(hyp.id)
        
        return active_hypotheses
    
    def get_all_hypotheses_from_tree(self) -> List[Hypothesis]:
        """
        Traverse the entire tree and collect ALL hypotheses (active, pruned, accepted) from all nodes.
        Uses master tracking (self.all_hypotheses) as the source of truth for confidence scores.
        
        Returns:
            List of all hypotheses found in the tree with updated confidence scores from master tracking
        """
        all_hypotheses = []
        seen_hypothesis_ids = set()
        
        # If no nodes, return empty list
        if not self.nodes:
            return []
        
        # First, collect all hypothesis IDs from nodes (to ensure we don't miss any)
        hypothesis_ids_from_nodes = set()
        
        # Traverse all nodes in the tree to find all hypothesis IDs
        for node in self.nodes:
            # Check if node has a hypothesis
            if node.hypothesis and node.hypothesis.id:
                hypothesis_ids_from_nodes.add(node.hypothesis.id)
            
            # Check if node has child_hypotheses (from expansion)
            if hasattr(node, 'child_hypotheses') and node.child_hypotheses:
                for hyp in node.child_hypotheses:
                    if hyp.id:
                        hypothesis_ids_from_nodes.add(hyp.id)
        
        # Also check root node's hypotheses (initial hypotheses)
        if self.root_node_id:
            root_node = self._get_node(self.root_node_id)
            for hyp in root_node.hypotheses:
                if hyp.id:
                    hypothesis_ids_from_nodes.add(hyp.id)
        
        # Now, use master tracking (self.all_hypotheses) as the primary source
        # This ensures we get the latest confidence scores and status
        for hyp_id in hypothesis_ids_from_nodes:
            if hyp_id not in seen_hypothesis_ids:
                # Prefer master tracking (source of truth with updated confidence)
                master_hyp = self.all_hypotheses.get(hyp_id)
                if master_hyp:
                    all_hypotheses.append(master_hyp)
                else:
                    # Fallback: if not in master tracking, find it from nodes
                    # This handles edge cases where a hypothesis exists but isn't tracked yet
                    for node in self.nodes:
                        if node.hypothesis and node.hypothesis.id == hyp_id:
                            all_hypotheses.append(node.hypothesis)
                            break
                        if hasattr(node, 'child_hypotheses') and node.child_hypotheses:
                            for hyp in node.child_hypotheses:
                                if hyp.id == hyp_id:
                                    all_hypotheses.append(hyp)
                                    break
                    else:
                        # Check root node as last resort
                        if self.root_node_id:
                            root_node = self._get_node(self.root_node_id)
                            for hyp in root_node.hypotheses:
                                if hyp.id == hyp_id:
                                    all_hypotheses.append(hyp)
                                    break
                
                seen_hypothesis_ids.add(hyp_id)
        
        # Final sync: ensure any hypotheses from nodes are synced with master tracking
        # This handles cases where we had to use node hypotheses as fallback
        for hyp in all_hypotheses:
            master_hyp = self.all_hypotheses.get(hyp.id)
            if master_hyp:
                # Sync confidence, status, and evidence from master (source of truth)
                hyp.confidence = master_hyp.confidence
                hyp.status = master_hyp.status
                hyp.evidence = master_hyp.evidence.copy() if master_hyp.evidence else []
                hyp.llm_score = master_hyp.llm_score
        
        return all_hypotheses
    
    def get_tree_summary(self) -> Dict:
        """Get a summary of the reasoning tree."""
        try:
            # Use tree traversal to get all hypotheses (not just root)
            all_hypotheses = self.get_all_hypotheses_from_tree()
            active_hypotheses = [h for h in all_hypotheses if h.status == "active"]
            pruned_hypotheses = [h for h in all_hypotheses if h.status == "pruned"]
            accepted_hypotheses = [h for h in all_hypotheses if h.status == "accepted"]
        except Exception as e:
            logger.warning(f"Error getting hypotheses from tree: {e}. Using fallback summary.")
            # Fallback if tree traversal fails
            active_hypotheses = []
            pruned_hypotheses = []
            accepted_hypotheses = []
        
        return {
            'total_nodes': len(self.nodes),
            'current_step': self.step_counter,
            'problem_summary': self.problem_summary,
            'active_hypotheses': len(active_hypotheses),
            'pruned_hypotheses': len(pruned_hypotheses),
            'accepted_hypotheses': len(accepted_hypotheses),
            'active_branches': len(active_hypotheses)
        }
    
    def is_complete(self) -> bool:
        """Check if reasoning is complete (sufficient data gathered)."""
        root_node = self.get_current_node()
        if not root_node:
            return False
        
        active_hypotheses = [h for h in root_node.hypotheses if h.status == "active"]
        accepted_hypotheses = [h for h in root_node.hypotheses if h.status == "accepted"]
        
        # Check if we have accepted hypotheses with high confidence
        if accepted_hypotheses:
            return True
        
        # Check if we've gathered enough data and narrowed down hypotheses
        # Count total artifacts across all active branches
        total_artifacts = sum(
            len(node.artifacts_received) 
            for node in self.nodes 
            if node.hypothesis_id and node.branch_status == "active"
        )
        
        if len(active_hypotheses) <= 2 and total_artifacts >= 3:
            return True
        
        return False
    
    def get_final_analysis(self) -> Dict:
        """Generate final root cause analysis using LLM.
        
        Performs tree traversal to consider ALL active hypotheses from the entire tree,
        prioritized by confidence score.
        """
        if not self.root_node_id:
            return {}
        
        # LLM is REQUIRED for final analysis
        if not self.llm_integration or not self.llm_integration.use_llm:
            raise ValueError("LLM is required for final analysis. Please ensure OPENAI_API_KEY is set.")
        
        try:
            llm_analysis = self.llm_integration.generate_final_analysis_llm(self)
            
            # Tree traversal: Get ALL active hypotheses from entire tree (not just current node)
            all_active_hypotheses = self.get_all_active_hypotheses_from_tree()
            
            # Sort all active hypotheses by confidence (descending) - prioritize by confidence
            top_hypotheses = sorted(
                all_active_hypotheses,
                key=lambda x: x.confidence,
                reverse=True
            )
            
            # Check if all hypotheses were pruned (from entire tree)
            all_pruned = len(top_hypotheses) == 0
            
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
    
    def to_dict_for_db(self, session_id: str, llm_provider: str = None, llm_model: str = None) -> Tuple[Dict, List[Dict]]:
        """
        Convert engine state to dictionaries for MongoDB storage.
        
        Returns:
            Tuple of (session_data, nodes_data)
        """
        # Prepare session document
        session_data = {
            "created_at": datetime.utcnow(),  # Will be set on first save
            "problem_summary": self.problem_summary,
            "session_status": "active",
            "root_node_id": self.root_node_id,
            "current_node_id": self.current_node_id,
            "current_branch_ids": self.current_branch_ids.copy() if self.current_branch_ids else [],
            "step_counter": self.step_counter,
            "weights": self.weights.copy(),
            "metadata": {
                "llm_provider": llm_provider or (self.llm_integration.provider_name if self.llm_integration else "unknown"),
                "llm_model": llm_model or (self.llm_integration.model_name if self.llm_integration else "unknown"),
                "total_nodes": len(self.nodes),
                "total_hypotheses": len(self.all_hypotheses)
            }
        }
        
        # Prepare nodes documents
        nodes_data = [node.to_dict() for node in self.nodes]
        
        return session_data, nodes_data
    
    @classmethod
    def from_normalized(cls, session_data: Dict, nodes_data: List[Dict], llm_integration=None) -> 'TreeOfThoughtEngine':
        """
        Reconstruct engine from normalized MongoDB data.
        
        Args:
            session_data: Session document from MongoDB
            nodes_data: List of node documents from MongoDB
            llm_integration: LLM integration instance (optional)
        
        Returns:
            Reconstructed TreeOfThoughtEngine instance
        """
        # Create engine instance
        engine = cls(weights=session_data.get("weights"), llm_integration=llm_integration)
        
        # Restore engine state
        engine.problem_summary = session_data.get("problem_summary", "")
        engine.root_node_id = session_data.get("root_node_id")
        engine.current_node_id = session_data.get("current_node_id")
        engine.current_branch_ids = session_data.get("current_branch_ids", [])
        engine.step_counter = session_data.get("step_counter", 0)
        
        # Reconstruct nodes
        if not nodes_data:
            logger.warning(f"No nodes found in MongoDB for session. Session data: {session_data.get('_id', 'unknown')}")
            engine.nodes = []
        else:
            engine.nodes = [ReasoningNode.from_dict(node) for node in nodes_data]
            logger.info(f"Reconstructed {len(engine.nodes)} nodes from MongoDB")
        
        # Reconstruct all_hypotheses master tracking
        engine.all_hypotheses = {}
        for node in engine.nodes:
            # Add hypothesis from node
            if node.hypothesis:
                engine.all_hypotheses[node.hypothesis.id] = node.hypothesis
            
            # Add initial hypotheses from root node
            if node.hypotheses:
                for hyp in node.hypotheses:
                    engine.all_hypotheses[hyp.id] = hyp
            
            # Add child hypotheses from expanded nodes
            if node.child_hypotheses:
                for hyp in node.child_hypotheses:
                    engine.all_hypotheses[hyp.id] = hyp
        
        return engine

