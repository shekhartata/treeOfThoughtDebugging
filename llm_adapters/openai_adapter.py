"""
OpenAI/GPT-5 Adapter - Implementation for OpenAI API.
This is the original implementation extracted from llm_integration.py
"""

import logging
import re
import os
from typing import List, Dict, TYPE_CHECKING
from dotenv import load_dotenv

from .base_adapter import BaseLLMAdapter

if TYPE_CHECKING:
    from tot_engine import ReasoningNode, TreeOfThoughtEngine

load_dotenv()
logger = logging.getLogger(__name__)


class OpenAIAdapter(BaseLLMAdapter):
    """
    OpenAI GPT-5 adapter.
    Uses system prompts and standard OpenAI API.
    """
    
    def __init__(self, api_key: str = None, model: str = "gpt-5"):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.model = model
        self._client = None
        
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is required. "
                "Please set OPENAI_API_KEY environment variable or pass api_key parameter."
            )
    
    @property
    def provider_name(self) -> str:
        return "OpenAI"
    
    @property
    def model_name(self) -> str:
        return self.model
    
    @property
    def client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client
    
    def _call_llm(self, system_prompt: str, user_prompt: str, max_tokens: int = 10000) -> str:
        """Make a call to the OpenAI API with system and user prompts."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=max_tokens
        )
        
        llm_output = response.choices[0].message.content
        
        # Handle empty content (GPT-5 may use all tokens for reasoning)
        if not llm_output or llm_output.strip() == '':
            logger.warning(f"Empty content from {self.model}. Finish reason: {response.choices[0].finish_reason}")
            if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                llm_output = response.choices[0].message.reasoning
                logger.info("Using reasoning content as fallback")
            else:
                raise ValueError(f"{self.model} returned empty content.")
        
        return llm_output
    
    def generate_hypotheses(self, problem_summary: str) -> Dict:
        """Generate initial hypotheses using GPT-5."""
        try:
            system_prompt = "You are an expert MongoDB consultant. Provide structured, actionable analysis."
            
            user_prompt = f"""You are an expert MongoDB consultant helping to debug a performance issue.

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
            
            llm_output = self._call_llm(system_prompt, user_prompt)
            
            # Parse hypotheses from LLM response
            hypotheses = []
            next_requests = []
            hypotheses_section = False
            
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
                    match = re.search(r'(.+?)\s*\|\s*Category:\s*([^|]+?)\s*\|\s*Confidence:\s*([\d.]+)', line, re.IGNORECASE)
                    if match:
                        desc = match.group(1).strip().lstrip('0123456789.-) ').strip()
                        category = match.group(2).strip().lower()
                        confidence = float(match.group(3))
                        prior = min(1.0, max(0.0, confidence))
                        
                        hypotheses.append({
                            'description': desc,
                            'category': category,
                            'prior_score': prior,
                            'confidence': min(1.0, max(0.0, confidence))
                        })
                elif not hypotheses_section and line.startswith('-'):
                    request = line.lstrip('- ').strip()
                    if request:
                        next_requests.append(request)
            
            return {
                'hypotheses': hypotheses,
                'next_requests': next_requests if next_requests else self.get_default_requests(),
                'raw_analysis': llm_output
            }
            
        except Exception as e:
            logger.error(f"OpenAI hypothesis generation failed: {e}", exc_info=True)
            raise ValueError(f"LLM hypothesis generation failed: {e}")
    
    def evaluate_branches(
        self, 
        branch_nodes: List['ReasoningNode'], 
        artifact_content: str, 
        problem_summary: str
    ) -> Dict[str, Dict]:
        """Evaluate multiple hypothesis branches using GPT-5."""
        try:
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
            
            system_prompt = "You are an expert MongoDB consultant. Provide detailed, structured analysis of diagnostic data across multiple hypothesis branches."
            
            user_prompt = f"""You are an expert MongoDB consultant evaluating diagnostic data across multiple hypothesis branches.

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
            
            llm_output = self._call_llm(system_prompt, user_prompt)
            
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
                    branch_match = re.search(r'BRANCH\s+([^\s:]+)', line, re.IGNORECASE)
                    if branch_match:
                        current_branch_id = branch_match.group(1).strip()
                        results[current_branch_id] = {'scores': {}, 'evidence': {}, 'status': 'neutral'}
                        continue
                    
                    if current_branch_id:
                        confidence_match = re.search(r'Confidence:\s*([\d.]+)', line, re.IGNORECASE)
                        evidence_match = re.search(r'Evidence:\s*(.+?)(?:\s*Status:|$)', line, re.IGNORECASE)
                        status_match = re.search(r'Status:\s*(\w+)', line, re.IGNORECASE)
                        
                        if confidence_match:
                            score = float(confidence_match.group(1))
                            score = min(1.0, max(0.0, score / 10.0 if score > 1 else score))
                            
                            for node in branch_nodes:
                                if node.hypothesis_id == current_branch_id and node.hypothesis:
                                    category = node.hypothesis.category
                                    results[current_branch_id]['scores'][category] = score
                                    if evidence_match:
                                        results[current_branch_id]['evidence'][category] = evidence_match.group(1).strip()
                                    if status_match:
                                        results[current_branch_id]['status'] = status_match.group(1).lower()
                                    break
            
            # Fallback if parsing failed
            if not results:
                for node in branch_nodes:
                    if node.hypothesis:
                        hyp_id = node.hypothesis_id
                        category = node.hypothesis.category
                        results[hyp_id] = {
                            'scores': {}, 
                            'evidence': {}, 
                            'status': 'neutral', 
                            'llm_reasoning': llm_output, 
                            'evidence_summary': evidence_summary.strip()
                        }
                        
                        pattern = rf"{category}.*?(\d+\.?\d*)"
                        match = re.search(pattern, llm_output.lower())
                        if match:
                            score = float(match.group(1))
                            results[hyp_id]['scores'][category] = min(1.0, max(0.0, score / 10.0 if score > 1 else score))
            
            # Add LLM reasoning to all results
            for hyp_id in results:
                if 'llm_reasoning' not in results[hyp_id]:
                    results[hyp_id]['llm_reasoning'] = llm_output
                if 'evidence_summary' not in results[hyp_id]:
                    results[hyp_id]['evidence_summary'] = evidence_summary.strip()
            
            return results
            
        except Exception as e:
            logger.error(f"OpenAI branch evaluation failed: {e}", exc_info=True)
            raise ValueError(f"LLM branch evaluation failed: {e}")
    
    def generate_next_requests(
        self, 
        node: 'ReasoningNode', 
        problem_summary: str
    ) -> List[str]:
        """Generate next data requests using GPT-5."""
        try:
            active_hypotheses = [h for h in node.hypotheses if h.status == "active"]
            hypotheses_text = "\n".join([
                f"- {h.description} (Category: {h.category}, Confidence: {h.confidence:.2f})"
                for h in active_hypotheses
            ])
            
            artifacts_collected = [art['name'] for art in node.artifacts_received]
            artifacts_text = "\n".join([f"- {name}" for name in artifacts_collected]) if artifacts_collected else "None yet"
            
            system_prompt = "You are an expert MongoDB consultant. Provide specific, actionable data requests."
            
            user_prompt = f"""You are an expert MongoDB consultant determining what diagnostic data to request next.

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
            
            llm_output = self._call_llm(system_prompt, user_prompt)
            
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
                    if request and len(request) > 10:
                        requests.append(request)
            
            # Fallback
            if not requests:
                for line in llm_output.split('\n'):
                    line = line.strip()
                    if ('db.' in line.lower() or 'mongodb' in line.lower() or 
                        'output' in line.lower() or 'command' in line.lower()):
                        if line and not line.startswith('#') and len(line) > 10:
                            requests.append(line.lstrip('- ').strip())
            
            return requests[:5] if requests else self.get_default_requests()
            
        except Exception as e:
            logger.error(f"OpenAI next requests generation failed: {e}", exc_info=True)
            raise ValueError(f"LLM request generation failed: {e}")
    
    def generate_final_analysis(self, engine: 'TreeOfThoughtEngine') -> Dict:
        """Generate final root cause analysis using GPT-5."""
        try:
            # Get all active hypotheses from tree
            all_active_hypotheses = engine.get_all_active_hypotheses_from_tree()
            sorted_hypotheses = sorted(all_active_hypotheses, key=lambda x: x.confidence, reverse=True)
            top_hypotheses = sorted_hypotheses
            
            # Collect artifacts
            all_artifacts = []
            all_artifact_content = []
            for n in engine.nodes:
                if n.branch_status == "active" or n.hypothesis_id is None:
                    for art in n.artifacts_received:
                        all_artifacts.append(art['name'])
                        all_artifact_content.append(f"{art['name']}:\n{art['content'][:500]}...")
            
            artifacts_summary = "\n".join([f"- {art}" for art in all_artifacts[-8:]])
            all_pruned = len(sorted_hypotheses) == 0
            
            system_prompt = "You are an expert MongoDB consultant providing comprehensive root cause analysis."
            
            if all_pruned or not top_hypotheses:
                artifacts_content_summary = "\n\n".join(all_artifact_content[:5])
                user_prompt = f"""You are an expert MongoDB consultant. The debugging session has collected some artifacts, but all initial hypotheses were pruned (ruled out) based on the available data.

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
                hypotheses_text = "\n".join([
                    f"{i+1}. {h.description} (Category: {h.category}, Confidence: {h.confidence:.2f})"
                    + (f" - Evidence: {', '.join(h.evidence[:2])}" if h.evidence else "")
                    for i, h in enumerate(top_hypotheses)
                ])
                
                user_prompt = f"""You are an expert MongoDB consultant providing the final root cause analysis.

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
            
            llm_output = self._call_llm(system_prompt, user_prompt)
            
            # Parse the structured response
            analysis = {
                'raw_analysis': llm_output,
                'root_cause': '',
                'confidence': 0.0,
                'evidence': [],
                'mitigation': '',
                'next_steps': [],
                'alternative_hypotheses': []
            }
            
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
                for section_key, section_name in sections.items():
                    if section_key in line.upper() and ':' in line:
                        current_section = section_name
                        content = line.split(':', 1)[1].strip() if ':' in line else ''
                        if content and section_name in ['root_cause', 'mitigation']:
                            analysis[section_name] = content
                        continue
                
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
            
            # Extract confidence
            confidence_match = re.search(r'confidence[:\s]+([\d.]+)', llm_output, re.IGNORECASE)
            if confidence_match:
                conf = float(confidence_match.group(1))
                analysis['confidence'] = min(1.0, max(0.0, conf / 10.0 if conf > 1 else conf))
            
            if not analysis['root_cause']:
                analysis['root_cause'] = llm_output.split('\n')[0] if llm_output else "Analysis generated"
            
            return analysis
            
        except Exception as e:
            logger.error(f"OpenAI final analysis failed: {e}", exc_info=True)
            raise ValueError(f"LLM final analysis failed: {e}")
    
    def generate_sub_hypotheses(
        self, 
        node: 'ReasoningNode', 
        engine: 'TreeOfThoughtEngine'
    ) -> Dict:
        """Generate sub-hypotheses from a node using GPT-5."""
        try:
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
            
            # Collect artifacts
            all_artifacts = []
            for n in engine.nodes:
                if n.step_number <= node.step_number:
                    for art in n.artifacts_received:
                        all_artifacts.append(f"- {art['name']}: {art['content'][:200]}...")
            
            artifacts_text = "\n".join(all_artifacts[-5:]) if all_artifacts else "No artifacts collected yet"
            
            system_prompt = "You are an expert MongoDB consultant. Generate focused, actionable exploration directions from specific points in a reasoning tree."
            
            user_prompt = f"""You are an expert MongoDB consultant exploring a debugging scenario from a specific point in the reasoning tree.

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
            
            llm_output = self._call_llm(system_prompt, user_prompt)
            
            # Parse new directions
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
                    match = re.search(r'(.+?)\s*\|\s*Category:\s*([^|]+?)\s*\|\s*Confidence:\s*([\d.]+)', line, re.IGNORECASE)
                    if match:
                        desc = match.group(1).strip().lstrip('0123456789.-) ').strip()
                        category = match.group(2).strip().lower()
                        confidence = float(match.group(3))
                        rationale_match = re.search(r'Rationale:\s*(.+)', line, re.IGNORECASE)
                        rationale = rationale_match.group(1).strip() if rationale_match else ""
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
            logger.error(f"OpenAI node expansion failed: {e}", exc_info=True)
            raise ValueError(f"LLM node expansion failed: {e}")

