"""
LLM Integration for MongoDB Debugging Tool
Handles prompts and LLM-based scoring for hypotheses.
"""

import logging
from typing import List, Dict, Optional
from tot_engine import Hypothesis, ReasoningNode, TreeOfThoughtEngine
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)


class LLMIntegration:
    """Handles LLM interactions for hypothesis evaluation."""
    
    def __init__(self, api_key: Optional[str] = None, require_llm: bool = True):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.use_llm = bool(self.api_key)
        self.require_llm = require_llm
        
        if not self.use_llm:
            if self.require_llm:
                raise ValueError(
                    "OPENAI_API_KEY is required but not set. "
                    "Please set OPENAI_API_KEY environment variable or pass api_key parameter. "
                    "The tool requires LLM for hypothesis generation."
                )
            else:
                print("⚠️  OPENAI_API_KEY not set. LLM scoring will be disabled. Using fallback mode.")
    
    def _get_initial_prompt(self, problem_summary: str) -> str:
        """Generate initial prompt for LLM."""
        return f"""You are an expert MongoDB consultant helping to debug a performance issue.

Problem Summary:
{problem_summary}

You do NOT have direct database access. You must request specific data artifacts from the consulting engineer.

Based on this problem, provide:
1. HYPOTHESES: List potential root causes (indexing, query shape, schema, cache, storage, replication, networking)
2. NEXT_REQUESTS: Specific MongoDB commands/outputs you need to see
3. CONFIDENCE_RANGE: Initial confidence assessment for each hypothesis

Format your response clearly with these sections."""

    def _get_followup_prompt(self, node: ReasoningNode, artifact_content: str) -> str:
        """Generate follow-up prompt for artifact evaluation."""
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

    def _get_final_prompt(self, engine: TreeOfThoughtEngine) -> str:
        """Generate final prompt for root cause analysis."""
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
            for art in all_artifacts[-5:]  # Last 5 artifacts
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

    def evaluate_hypotheses_with_llm(self, node: ReasoningNode, artifact_content: str, problem_summary: str) -> Dict:
        """Use LLM to evaluate hypotheses based on new artifact. Returns scores and evidence."""
        if not self.use_llm:
            raise ValueError("LLM is required for artifact evaluation but not available.")
        
        try:
            from openai import OpenAI
            import re
            client = OpenAI(api_key=self.api_key)
            
            hypotheses_text = "\n".join([
                f"- {h.description} (Category: {h.category}, Current Confidence: {h.confidence:.2f})"
                for h in node.hypotheses if h.status == "active"
            ])
            
            prompt = f"""You are an expert MongoDB consultant evaluating diagnostic data.

Problem Summary:
{problem_summary}

Current Active Hypotheses:
{hypotheses_text}

New Artifact Received:
{artifact_content[:3000]}...

Based on this new evidence, evaluate each hypothesis:

1. For each hypothesis, provide:
   - Updated confidence score (0.0-1.0)
   - Specific evidence found in the artifact (if any)
   - Whether this evidence supports or contradicts the hypothesis

2. Format your response as:
HYPOTHESIS_EVALUATIONS:
1. [Hypothesis Description] | Confidence: [0.0-1.0] | Evidence: [specific evidence found] | Status: [supported/contradicted/neutral]
2. [Next hypothesis] | ...

EVIDENCE_SUMMARY:
[Summary of key findings from the artifact]

Be specific about what evidence you found in the artifact that relates to each hypothesis."""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are an expert MongoDB consultant. Provide detailed, structured analysis of diagnostic data."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=10000  # Significantly increased to allow for reasoning tokens + actual content
            )
            
            llm_output = response.choices[0].message.content
            
            # Check if content is empty (GPT-5 may use all tokens for reasoning)
            if not llm_output or llm_output.strip() == '':
                logger.warning(f"Empty content from GPT-5. Finish reason: {response.choices[0].finish_reason}, "
                             f"Usage: {response.usage}")
                # Try to get reasoning content if available
                if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                    llm_output = response.choices[0].message.reasoning
                    logger.info("Using reasoning content as fallback")
                else:
                    raise ValueError("GPT-5 returned empty content. All tokens may have been used for reasoning. "
                                   "Try increasing max_completion_tokens or simplifying the prompt.")
            
            # Parse evaluation results
            scores = {}
            evidence_map = {}
            
            lines = llm_output.split('\n')
            in_evaluations = False
            
            for line in lines:
                line = line.strip()
                if 'HYPOTHESIS_EVALUATIONS:' in line.upper() or 'EVALUATION:' in line.upper():
                    in_evaluations = True
                    continue
                if 'EVIDENCE_SUMMARY:' in line.upper() or 'SUMMARY:' in line.upper():
                    in_evaluations = False
                    continue
                
                if in_evaluations and line and (line[0].isdigit() or line.startswith('-')):
                    # Parse: "1. Description | Confidence: 0.7 | Evidence: ... | Status: ..."
                    confidence_match = re.search(r'Confidence:\s*([\d.]+)', line, re.IGNORECASE)
                    evidence_match = re.search(r'Evidence:\s*(.+?)(?:\s*\||$)', line, re.IGNORECASE)
                    
                    if confidence_match:
                        score = float(confidence_match.group(1))
                        score = min(1.0, max(0.0, score / 10.0 if score > 1 else score))
                        
                        # Match to hypothesis by description
                        for hypothesis in node.hypotheses:
                            if hypothesis.status == "active":
                                # Check if this line mentions the hypothesis
                                if hypothesis.description.lower()[:30] in line.lower() or hypothesis.category in line.lower():
                                    scores[hypothesis.category] = score
                                    if evidence_match:
                                        evidence_map[hypothesis.category] = evidence_match.group(1).strip()
                                    break
            
            # If parsing failed, try to extract scores from text
            if not scores:
                for hypothesis in node.hypotheses:
                    if hypothesis.status == "active":
                        category = hypothesis.category
                        if category in llm_output.lower():
                            pattern = rf"{category}.*?(\d+\.?\d*)"
                            match = re.search(pattern, llm_output.lower())
                            if match:
                                score = float(match.group(1))
                                scores[category] = min(1.0, max(0.0, score / 10.0 if score > 1 else score))
            
            return {
                'scores': scores,
                'evidence': evidence_map,
                'raw_analysis': llm_output
            }
            
        except Exception as e:
            logger.error(f"LLM artifact evaluation failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM evaluation failed: {e}. Please check your API key and try again.")
    
    def evaluate_branches_with_llm(self, branch_nodes: List[ReasoningNode], artifact_content: str, problem_summary: str) -> Dict[str, Dict]:
        """
        Evaluate multiple hypothesis branches in one LLM call (hybrid approach).
        
        Args:
            branch_nodes: List of nodes, one per active branch
            artifact_content: The artifact content to evaluate
            problem_summary: The original problem summary
        
        Returns:
            Dict mapping hypothesis_id to evaluation results (scores, evidence)
        """
        if not self.use_llm:
            raise ValueError("LLM is required for artifact evaluation but not available.")
        
        try:
            from openai import OpenAI
            import re
            client = OpenAI(api_key=self.api_key)
            
            # Build context for all branches
            branches_text = []
            for node in branch_nodes:
                if node.hypothesis and node.hypothesis_id:
                    branches_text.append(
                        f"BRANCH {node.hypothesis_id}:\n"
                        f"  Hypothesis: {node.hypothesis.description}\n"
                        f"  Category: {node.hypothesis.category}\n"
                        f"  Current Confidence: {node.hypothesis.confidence:.2f}\n"
                        f"  Evidence So Far: {', '.join(node.hypothesis.evidence[-3:]) if node.hypothesis.evidence else 'None'}\n"
                    )
            
            branches_context = "\n".join(branches_text)
            
            prompt = f"""You are an expert MongoDB consultant evaluating diagnostic data across multiple hypothesis branches.

Problem Summary:
{problem_summary}

Active Hypothesis Branches:
{branches_context}

New Artifact Received:
{artifact_content[:3000]}

Based on this new evidence, evaluate EACH branch independently:

For EACH branch, provide:
1. Updated confidence score (0.0-1.0) for that specific hypothesis
2. Specific evidence found in the artifact that relates to that hypothesis
3. Whether this evidence supports, contradicts, or is neutral for that hypothesis

Format your response as:
BRANCH_EVALUATIONS:
BRANCH [hypothesis_id]:
  Confidence: [0.0-1.0]
  Evidence: [specific evidence found]
  Status: [supported/contradicted/neutral]

BRANCH [next_hypothesis_id]:
  ...

EVIDENCE_SUMMARY:
[Summary of key findings from the artifact across all branches]

Be specific about what evidence you found in the artifact that relates to each hypothesis branch."""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are an expert MongoDB consultant. Provide detailed, structured analysis of diagnostic data across multiple hypothesis branches."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=10000
            )
            
            llm_output = response.choices[0].message.content
            
            # Check if content is empty
            if not llm_output or llm_output.strip() == '':
                logger.warning(f"Empty content from GPT-5. Finish reason: {response.choices[0].finish_reason}")
                if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                    llm_output = response.choices[0].message.reasoning
                    logger.info("Using reasoning content as fallback")
                else:
                    raise ValueError("GPT-5 returned empty content.")
            
            # Parse evaluation results for each branch
            results = {}
            current_branch_id = None
            evidence_summary = ""
            
            lines = llm_output.split('\n')
            in_evaluations = False
            in_summary = False
            
            for line in lines:
                line = line.strip()
                if 'BRANCH_EVALUATIONS:' in line.upper():
                    in_evaluations = True
                    in_summary = False
                    continue
                if 'EVIDENCE_SUMMARY:' in line.upper():
                    in_evaluations = False
                    in_summary = True
                    continue
                
                if in_summary:
                    evidence_summary += line + " "
                    continue
                
                if in_evaluations:
                    # Check if this is a new branch header
                    branch_match = re.search(r'BRANCH\s+([^\s:]+)', line, re.IGNORECASE)
                    if branch_match:
                        current_branch_id = branch_match.group(1).strip()
                        results[current_branch_id] = {'scores': {}, 'evidence': {}, 'status': 'neutral'}
                        continue
                    
                    # Parse confidence, evidence, and status for current branch
                    if current_branch_id:
                        confidence_match = re.search(r'Confidence:\s*([\d.]+)', line, re.IGNORECASE)
                        evidence_match = re.search(r'Evidence:\s*(.+?)(?:\s*Status:|$)', line, re.IGNORECASE)
                        status_match = re.search(r'Status:\s*(\w+)', line, re.IGNORECASE)
                        
                        if confidence_match:
                            score = float(confidence_match.group(1))
                            score = min(1.0, max(0.0, score / 10.0 if score > 1 else score))
                            
                            # Find the node for this branch to get category
                            for node in branch_nodes:
                                if node.hypothesis_id == current_branch_id and node.hypothesis:
                                    category = node.hypothesis.category
                                    results[current_branch_id]['scores'][category] = score
                                    if evidence_match:
                                        results[current_branch_id]['evidence'][category] = evidence_match.group(1).strip()
                                    if status_match:
                                        results[current_branch_id]['status'] = status_match.group(1).lower()
                                    break
            
            # Fallback: if parsing failed, try to extract from text
            if not results:
                for node in branch_nodes:
                    if node.hypothesis:
                        hyp_id = node.hypothesis_id
                        category = node.hypothesis.category
                        results[hyp_id] = {'scores': {}, 'evidence': {}, 'status': 'neutral', 'llm_reasoning': llm_output, 'evidence_summary': evidence_summary.strip()}
                        
                        # Try to find confidence for this category
                        pattern = rf"{category}.*?(\d+\.?\d*)"
                        match = re.search(pattern, llm_output.lower())
                        if match:
                            score = float(match.group(1))
                            results[hyp_id]['scores'][category] = min(1.0, max(0.0, score / 10.0 if score > 1 else score))
            
            # Add full LLM reasoning and evidence summary to results (if not already added in fallback)
            for hyp_id in results:
                if 'llm_reasoning' not in results[hyp_id]:
                    results[hyp_id]['llm_reasoning'] = llm_output
                if 'evidence_summary' not in results[hyp_id]:
                    results[hyp_id]['evidence_summary'] = evidence_summary.strip()
            
            return results
            
        except Exception as e:
            logger.error(f"LLM branch evaluation failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM branch evaluation failed: {e}. Please check your API key and try again.")

    def generate_hypotheses_from_llm(self, problem_summary: str) -> List[Dict]:
        """Generate initial hypotheses from LLM. This is the PRIMARY method."""
        if not self.use_llm:
            raise ValueError("LLM is required for hypothesis generation but not available.")
        
        try:
            from openai import OpenAI
            import re
            client = OpenAI(api_key=self.api_key)
            
            prompt = f"""You are an expert MongoDB consultant helping to debug a performance issue.

Problem Summary:
{problem_summary}

You do NOT have direct database access. You must request specific data artifacts from the consulting engineer.

Based on this problem, generate 3-7 potential root cause mutually exclusive and collectively exhaustive hypotheses analyzing the problem statement. For each hypothesis, provide:
1. A clear description of the potential issue
2. A category name that best describes the type of issue (you can use any relevant category name such as indexing, query_shape, schema, wt_cache, storage, replication, networking, or any other category that is relevant to this specific problem)
3. An initial confidence score (0.0-1.0) based on how relevant and likely this hypothesis is given the problem statement

Format your response as:
HYPOTHESES:
1. [Description] | Category: [category] | Confidence: [0.0-1.0]
2. [Description] | Category: [category] | Confidence: [0.0-1.0]
...

NEXT_REQUESTS:
- [Specific MongoDB command/output needed]
- [Another specific request]
..."""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are an expert MongoDB consultant. Provide structured, actionable analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=10000  # Significantly increased to allow for reasoning tokens + actual content
            )

            #logger.info(f"LLM hypothesis generation response: {response}")
            llm_output = response.choices[0].message.content
            
            # Check if content is empty (GPT-5 may use all tokens for reasoning)
            if not llm_output or llm_output.strip() == '':
                logger.warning(f"Empty content from GPT-5. Finish reason: {response.choices[0].finish_reason}, "
                             f"Usage: {response.usage}")
                # Try to get reasoning content if available
                if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                    llm_output = response.choices[0].message.reasoning
                    logger.info("Using reasoning content as fallback")
                else:
                    raise ValueError("GPT-5 returned empty content. All tokens may have been used for reasoning. "
                                   "Try increasing max_completion_tokens or simplifying the prompt.")
            
            # Parse hypotheses from LLM response
            hypotheses = []
            hypotheses_section = False
            next_requests = []
            
            lines = llm_output.split('\n')
            for line in lines:
                line = line.strip()
                if 'HYPOTHESES:' in line.upper() or 'HYPOTHESIS:' in line.upper():
                    hypotheses_section = True
                    continue
                if 'NEXT_REQUESTS:' in line.upper() or 'NEXT REQUEST:' in line.upper():
                    hypotheses_section = False
                    continue
                
                if hypotheses_section and line and (line[0].isdigit() or line.startswith('-')):
                    # Parse hypothesis line
                    # Format: "1. Description | Category: category | Confidence: 0.5"
                    # Updated regex to handle categories with spaces and special characters
                    match = re.search(r'(.+?)\s*\|\s*Category:\s*([^|]+?)\s*\|\s*Confidence:\s*([\d.]+)', line, re.IGNORECASE)
                    if match:
                        desc = match.group(1).strip().lstrip('0123456789.-) ').strip()
                        category = match.group(2).strip().lower()
                        confidence = float(match.group(3))
                        
                        # Use confidence as prior_score (automatic scoring based on LLM's confidence)
                        # No fixed category map - scoring is based on relevance to the problem
                        prior = min(1.0, max(0.0, confidence))
                        
                        hypotheses.append({
                            'description': desc,
                            'category': category,
                            'prior_score': prior,
                            'confidence': min(1.0, max(0.0, confidence))
                        })
                elif not hypotheses_section and line.startswith('-'):
                    # Parse next request
                    request = line.lstrip('- ').strip()
                    if request:
                        next_requests.append(request)
            
            # If parsing failed, try alternative parsing
            if not hypotheses:
                # Fallback: try to extract any hypotheses mentioned
                # Use a default confidence based on problem relevance (not category)
                logger.warning("Failed to parse hypotheses from LLM response, attempting fallback parsing")
                # This fallback is minimal - ideally the LLM should provide properly formatted output
            
            return {
                'hypotheses': hypotheses,
                'next_requests': next_requests if next_requests else self._get_default_requests(),
                'raw_analysis': llm_output
            }
            
        except Exception as e:
            logger.error(f"LLM hypothesis generation failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM hypothesis generation failed: {e}. Please check your API key and try again.")
    
    def _get_default_requests(self) -> List[str]:
        """Default data requests if LLM doesn't provide them."""
        return [
            "db.currentOp() output showing running operations",
            "Sample slow query profiles (db.system.profile.find())",
            "db.serverStatus() output",
            "db.stats() for affected collections"
        ]
    
    def get_initial_analysis(self, problem_summary: str) -> Dict:
        """Get initial analysis from LLM (legacy method, kept for compatibility)."""
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
            logger.error(f"LLM hypothesis generation (fallback) failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            return {
                'analysis': f'Error: {e}',
                'hypotheses': [],
                'next_requests': [],
                'confidence_range': {}
            }

    def generate_next_requests_llm(self, node: ReasoningNode, problem_summary: str) -> List[str]:
        """Generate next data requests using LLM based on current state."""
        if not self.use_llm:
            raise ValueError("LLM is required for generating next requests but not available.")
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            active_hypotheses = [h for h in node.hypotheses if h.status == "active"]
            hypotheses_text = "\n".join([
                f"- {h.description} (Category: {h.category}, Confidence: {h.confidence:.2f})"
                for h in active_hypotheses
            ])
            
            artifacts_collected = [art['name'] for art in node.artifacts_received]
            artifacts_text = "\n".join([f"- {name}" for name in artifacts_collected]) if artifacts_collected else "None yet"
            
            prompt = f"""You are an expert MongoDB consultant determining what diagnostic data to request next.

Problem Summary:
{problem_summary}

Current Active Hypotheses:
{hypotheses_text}

Artifacts Already Collected:
{artifacts_text}

Previously Requested (to avoid duplicates):
{chr(10).join([f"- {req}" for req in node.requested_data[-5:]]) if node.requested_data else "None"}

Based on the current hypotheses and what we've already collected, what specific MongoDB commands, outputs, or diagnostic data should we request next to:
1. Confirm or rule out the active hypotheses
2. Narrow down the root cause
3. Gather missing critical information

Provide 3-5 specific, actionable requests. Format as:
NEXT_REQUESTS:
- [Specific MongoDB command or diagnostic output needed]
- [Another specific request]
...

Be specific about what commands to run or what outputs to collect."""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are an expert MongoDB consultant. Provide specific, actionable data requests."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=10000  # Significantly increased to allow for reasoning tokens + actual content
            )
            
            llm_output = response.choices[0].message.content
            
            # Check if content is empty (GPT-5 may use all tokens for reasoning)
            if not llm_output or llm_output.strip() == '':
                logger.warning(f"Empty content from GPT-5. Finish reason: {response.choices[0].finish_reason}, "
                             f"Usage: {response.usage}")
                # Try to get reasoning content if available
                if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                    llm_output = response.choices[0].message.reasoning
                    logger.info("Using reasoning content as fallback")
                else:
                    # If still empty, try a simpler fallback - return default requests
                    logger.error("GPT-5 returned empty content even with 8000 tokens. Using default requests.")
                    return self._get_default_requests()
            
            # Parse requests
            requests = []
            in_requests = False
            
            for line in llm_output.split('\n'):
                line = line.strip()
                if 'NEXT_REQUESTS:' in line.upper() or 'REQUESTS:' in line.upper():
                    in_requests = True
                    continue
                if in_requests and line.startswith('-'):
                    request = line.lstrip('- ').strip()
                    if request and len(request) > 10:  # Filter out very short lines
                        requests.append(request)
            
            # Fallback: extract any lines that look like requests
            if not requests:
                for line in llm_output.split('\n'):
                    line = line.strip()
                    if ('db.' in line.lower() or 'mongodb' in line.lower() or 
                        'output' in line.lower() or 'command' in line.lower()):
                        if line and not line.startswith('#') and len(line) > 10:
                            requests.append(line.lstrip('- ').strip())
            
            return requests[:5] if requests else self._get_default_requests()
            
        except Exception as e:
            logger.error(f"LLM next requests generation failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM request generation failed: {e}. Please check your API key and try again.")
    
    def generate_final_analysis_llm(self, engine: TreeOfThoughtEngine) -> Dict:
        """Generate complete final root cause analysis from LLM.
        
        Performs tree traversal to get ALL active hypotheses from the entire tree,
        prioritized by confidence score.
        """
        if not self.use_llm:
            raise ValueError("LLM is required for final analysis but not available.")
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            # Tree traversal: Get ALL active hypotheses from entire tree (not just current node)
            all_active_hypotheses = engine.get_all_active_hypotheses_from_tree()
            
            # Sort all active hypotheses by confidence (descending) - prioritize by confidence
            sorted_hypotheses = sorted(
                all_active_hypotheses,
                key=lambda x: x.confidence,
                reverse=True
            )
            
            # Get top hypotheses for display (all of them, prioritized by confidence)
            top_hypotheses = sorted_hypotheses  # Use all active hypotheses, not just top 3
            
            # Collect all artifacts from ALL active nodes in the tree (not just current node)
            all_artifacts = []
            all_artifact_content = []
            for n in engine.nodes:
                # Only include artifacts from active nodes (not pruned branches)
                if n.branch_status == "active" or n.hypothesis_id is None:  # Include root node
                    for art in n.artifacts_received:
                        all_artifacts.append(art['name'])
                        all_artifact_content.append(f"{art['name']}:\n{art['content'][:500]}...")  # First 500 chars
            
            artifacts_summary = "\n".join([f"- {art}" for art in all_artifacts[-8:]])  # Last 8 artifacts
            
            # Check if all hypotheses were pruned (from entire tree)
            all_pruned = len(sorted_hypotheses) == 0
            
            if all_pruned or not top_hypotheses:
                # All hypotheses pruned - provide recommendations based on available artifacts
                hypotheses_text = "All initial hypotheses were pruned based on the available artifacts."
                artifacts_content_summary = "\n\n".join(all_artifact_content[:5])  # First 5 artifacts with content
                
                prompt = f"""You are an expert MongoDB consultant. The debugging session has collected some artifacts, but all initial hypotheses were pruned (ruled out) based on the available data.

Problem Summary:
{engine.problem_summary}

Status: All initial hypotheses were pruned based on available artifacts.

Artifacts Collected:
{artifacts_summary}

Artifact Content (sample):
{artifacts_content_summary}

Even though the initial hypotheses were ruled out, please provide:

1. ROOT_CAUSE: Based on the problem description and available artifacts, what could be the root cause? (If insufficient data, state that clearly)
2. EVIDENCE: What evidence from the artifacts supports or contradicts potential causes?
3. MITIGATION: What steps should be taken next? (e.g., collect different artifacts, check other areas)
4. NEXT_STEPS: Specific recommendations for what diagnostic data to collect next (3-5 specific requests)
5. ALTERNATIVE_HYPOTHESES: Other potential issues to investigate

Be helpful and actionable even with limited data. If more data is needed, clearly specify what to collect."""
            else:
                # Normal case with active hypotheses from entire tree
                # Format hypotheses with confidence priority (sorted by confidence, highest first)
                hypotheses_text = "\n".join([
                    f"{i+1}. {h.description} (Category: {h.category}, Confidence: {h.confidence:.2f})"
                    + (f" - Evidence: {', '.join(h.evidence[:2])}" if h.evidence else "")
                    for i, h in enumerate(top_hypotheses)
                ])
                
                prompt = f"""You are an expert MongoDB consultant providing the final root cause analysis.

Problem Summary:
{engine.problem_summary}

All Active Hypotheses (from entire reasoning tree, prioritized by confidence - highest first):
{hypotheses_text}

Note: These hypotheses were collected from the entire reasoning tree, including all active nodes, child nodes, and expanded hypotheses. They are sorted by confidence score, with the highest confidence hypotheses listed first.

Artifacts Collected:
{artifacts_summary}

Provide a comprehensive root cause analysis:

1. ROOT_CAUSE: The most likely root cause with confidence level (0.0-1.0)
2. EVIDENCE: Key evidence supporting this conclusion (be specific)
3. MITIGATION: Detailed, actionable steps to resolve the issue
4. NEXT_STEPS: Specific next steps for the consulting engineer (3-5 steps)
5. ALTERNATIVE_HYPOTHESES: Other possibilities if the primary root cause is incorrect

Format your response clearly with these sections. Be specific and actionable."""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are an expert MongoDB consultant providing comprehensive root cause analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=10000  # Significantly increased to allow for reasoning tokens + actual content
            )
            
            llm_output = response.choices[0].message.content
            
            # Check if content is empty (GPT-5 may use all tokens for reasoning)
            if not llm_output or llm_output.strip() == '':
                logger.warning(f"Empty content from GPT-5. Finish reason: {response.choices[0].finish_reason}, "
                             f"Usage: {response.usage}")
                # Try to get reasoning content if available
                if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                    llm_output = response.choices[0].message.reasoning
                    logger.info("Using reasoning content as fallback")
                else:
                    raise ValueError("GPT-5 returned empty content. All tokens may have been used for reasoning. "
                                   "Try increasing max_completion_tokens or simplifying the prompt.")
            
            # Parse the structured response
            import re
            analysis = {
                'raw_analysis': llm_output,
                'root_cause': '',
                'confidence': 0.0,
                'evidence': [],
                'mitigation': '',
                'next_steps': [],
                'alternative_hypotheses': []
            }
            
            # Extract sections
            sections = {
                'ROOT_CAUSE': 'root_cause',
                'EVIDENCE': 'evidence',
                'MITIGATION': 'mitigation',
                'NEXT_STEPS': 'next_steps',
                'ALTERNATIVE': 'alternative_hypotheses'
            }
            
            current_section = None
            lines = llm_output.split('\n')
            
            for line in lines:
                line = line.strip()
                # Check for section headers
                for section_key, section_name in sections.items():
                    if section_key in line.upper() and ':' in line:
                        current_section = section_name
                        # Extract content after colon
                        content = line.split(':', 1)[1].strip() if ':' in line else ''
                        if content and section_name in ['root_cause', 'mitigation']:
                            analysis[section_name] = content
                        continue
                
                # Collect content for current section
                if current_section and line:
                    if current_section == 'evidence':
                        if line.startswith('-') or line[0].isdigit():
                            analysis['evidence'].append(line.lstrip('- ').lstrip('0123456789. ').strip())
                    elif current_section == 'next_steps':
                        if line.startswith('-') or line[0].isdigit():
                            analysis['next_steps'].append(line.lstrip('- ').lstrip('0123456789. ').strip())
                    elif current_section == 'alternative_hypotheses':
                        if line.startswith('-') or line[0].isdigit():
                            analysis['alternative_hypotheses'].append(line.lstrip('- ').lstrip('0123456789. ').strip())
                    elif current_section in ['root_cause', 'mitigation']:
                        if not analysis[current_section]:
                            analysis[current_section] = line
                        else:
                            analysis[current_section] += " " + line
            
            # Extract confidence from root cause
            confidence_match = re.search(r'confidence[:\s]+([\d.]+)', llm_output, re.IGNORECASE)
            if confidence_match:
                analysis['confidence'] = min(1.0, max(0.0, float(confidence_match.group(1)) / 10.0 if float(confidence_match.group(1)) > 1 else float(confidence_match.group(1))))
            
            # Fallback: if parsing failed, use raw analysis
            if not analysis['root_cause']:
                analysis['root_cause'] = llm_output.split('\n')[0] if llm_output else "Analysis generated"
            
            return analysis
            
        except Exception as e:
            logger.error(f"LLM final analysis generation failed: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise ValueError(f"LLM final analysis failed: {e}. Please check your API key and try again.")
    
    def generate_sub_hypotheses_from_node(self, node: ReasoningNode, engine: TreeOfThoughtEngine) -> List[Dict]:
        """
        Generate new sub-hypotheses or exploration directions from a specific node.
        This allows expanding the tree from any point by generating new ideas to explore.
        
        Args:
            node: The node to expand from
            engine: The engine instance to get context (problem summary, path, etc.)
        
        Returns:
            List of dictionaries with new hypotheses and next requests
        """
        if not self.use_llm:
            raise ValueError("LLM is required for node expansion but not available.")
        
        try:
            from openai import OpenAI
            import re
            client = OpenAI(api_key=self.api_key)
            
            # Build context about the current node
            node_hypothesis = ""
            if node.hypothesis:
                node_hypothesis = f"""
Current Hypothesis at This Node:
- Description: {node.hypothesis.description}
- Category: {node.hypothesis.category}
- Current Confidence: {node.hypothesis.confidence:.2f}
- Evidence Collected: {', '.join(node.hypothesis.evidence[-3:]) if node.hypothesis.evidence else 'None'}
"""
            
            # Get path from root to this node
            path_to_node = []
            current = node
            while current:
                path_to_node.insert(0, {
                    'step': current.step_number,
                    'hypothesis': current.hypothesis.description if current.hypothesis else 'Root',
                    'artifacts': [a['name'] for a in current.artifacts_received]
                })
                if current.parent_id:
                    try:
                        current = engine._get_node(current.parent_id)
                    except:
                        break
                else:
                    break
            
            path_text = "\n".join([
                f"  Step {p['step']}: {p['hypothesis']} (Artifacts: {', '.join(p['artifacts']) if p['artifacts'] else 'None'})"
                for p in path_to_node
            ])
            
            # Collect all artifacts from the path
            all_artifacts = []
            for n in engine.nodes:
                if n.step_number <= node.step_number:  # Only artifacts up to this node
                    for art in n.artifacts_received:
                        all_artifacts.append(f"- {art['name']}: {art['content'][:200]}...")
            
            artifacts_text = "\n".join(all_artifacts[-5:]) if all_artifacts else "No artifacts collected yet"
            
            prompt = f"""You are an expert MongoDB consultant exploring a debugging scenario from a specific point in the reasoning tree.

ORIGINAL PROBLEM:
{engine.problem_summary}

CURRENT POSITION IN REASONING TREE:
{path_text}

{node_hypothesis}

ARTIFACTS COLLECTED SO FAR:
{artifacts_text}

Based on this context, generate 2-5 NEW exploration directions or sub-hypotheses to investigate from this point. These should be:
1. More specific variations or deeper investigations of the current hypothesis
2. Alternative explanations that haven't been fully explored
3. Related issues that might be connected
4. New angles to investigate based on what we've learned
5. The hypotheses should be mutually exclusive and collectively exhaustive.

For each new direction, provide:
1. A clear description of what to explore
2. A category name that best describes the type of issue (you can use any relevant category name such as indexing, query_shape, schema, wt_cache, storage, replication, networking, or any other category that is relevant to this specific problem)
3. An initial confidence score (0.0-1.0) based on how relevant this direction is given the current evidence and problem statement
4. Why this direction is worth exploring from this point

Format your response as:
NEW_DIRECTIONS:
1. [Description] | Category: [category] | Confidence: [0.0-1.0] | Rationale: [why explore this]
2. [Description] | Category: [category] | Confidence: [0.0-1.0] | Rationale: [why explore this]
...

NEXT_REQUESTS:
- [Specific MongoDB command/output needed for these new directions]
- [Another specific request]
..."""
            
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role": "system", "content": "You are an expert MongoDB consultant. Generate focused, actionable exploration directions from specific points in a reasoning tree."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=10000
            )
            
            llm_output = response.choices[0].message.content
            
            # Check if content is empty
            if not llm_output or llm_output.strip() == '':
                if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                    llm_output = response.choices[0].message.reasoning
                else:
                    raise ValueError("GPT-5 returned empty content for node expansion.")
            
            # Parse new directions/hypotheses
            new_hypotheses = []
            next_requests = []
            in_directions = False
            in_requests = False
            
            lines = llm_output.split('\n')
            for line in lines:
                line = line.strip()
                if 'NEW_DIRECTIONS:' in line.upper() or 'DIRECTIONS:' in line.upper():
                    in_directions = True
                    in_requests = False
                    continue
                if 'NEXT_REQUESTS:' in line.upper() or 'NEXT REQUEST:' in line.upper():
                    in_directions = False
                    in_requests = True
                    continue
                
                if in_directions and line and (line[0].isdigit() or line.startswith('-')):
                    # Parse: "1. Description | Category: cat | Confidence: 0.5 | Rationale: ..."
                    # Updated regex to handle categories with spaces and special characters
                    match = re.search(r'(.+?)\s*\|\s*Category:\s*([^|]+?)\s*\|\s*Confidence:\s*([\d.]+)', line, re.IGNORECASE)
                    if match:
                        desc = match.group(1).strip().lstrip('0123456789.-) ').strip()
                        category = match.group(2).strip().lower()
                        confidence = float(match.group(3))
                        # Extract rationale if present
                        rationale_match = re.search(r'Rationale:\s*(.+)', line, re.IGNORECASE)
                        rationale = rationale_match.group(1).strip() if rationale_match else ""
                        
                        # Use confidence as prior_score (automatic scoring based on LLM's confidence)
                        # No fixed category map - scoring is based on relevance to the problem
                        prior = min(1.0, max(0.0, confidence))
                        
                        new_hypotheses.append({
                            'description': desc,
                            'category': category,
                            'prior_score': prior,
                            'confidence': min(1.0, max(0.0, confidence)),
                            'rationale': rationale
                        })
                
                if in_requests and line and (line.startswith('-') or line[0].isdigit()):
                    req = line.lstrip('- ').lstrip('0123456789. ').strip()
                    if req:
                        next_requests.append(req)
            
            return {
                'hypotheses': new_hypotheses,
                'next_requests': next_requests
            }
            
        except Exception as e:
            logger.error(f"LLM node expansion failed: {e}", exc_info=True)
            raise ValueError(f"LLM node expansion failed: {e}. Please check your API key and try again.")

