"""
Bayesian Evidence Screening Module
Implements Bayesian probability updates using likelihood ratios from LLM evidence evaluation.
"""

import math
import logging

logger = logging.getLogger(__name__)


class BayesianPruner:
    """
    Bayesian pruner for updating hypothesis confidence using evidence likelihood ratios.
    
    Uses log-odds mathematics to update probabilities based on evidence strength,
    avoiding volatility from direct confidence score predictions.
    """
    
    # Evidence weight sensitivity (baseline)
    EVIDENCE_WEIGHT_BASELINE = 1.5
    
    # Evidence weight for extremely strong evidence (±8 to ±10)
    EVIDENCE_WEIGHT_STRONG = 2.0
    
    # Pruning threshold (15% as per Bayesian approach)
    PRUNE_THRESHOLD = 0.15
    
    @staticmethod
    def calculate_posterior(prior_percent: float, evidence_score: int) -> float:
        """
        Updates belief using Log-Odds Math to avoid volatility.
        
        Args:
            prior_percent: Prior confidence as percentage (0-100)
            evidence_score: Likelihood score from -10 (disproves) to +10 (proves)
        
        Returns:
            Updated confidence as percentage (0-100)
        """
        # 1. Clamp Prior (Never 0% or 100% to avoid math errors)
        p_prior = max(min(prior_percent / 100.0, 0.99), 0.01)
        
        # 2. Convert to Log-Odds (The "Belief State")
        log_odds_prior = math.log(p_prior / (1 - p_prior))
        
        # 3. Apply Evidence Weight with adaptive scaling
        # Evidence score is -10 to +10
        # Use stronger weight (2.0) for extremely strong evidence (±8 to ±10)
        # Use baseline weight (1.5) for moderate evidence
        abs_evidence = abs(evidence_score)
        if abs_evidence >= 8:
            # Extremely strong evidence (strongly supports or strongly contradicts)
            evidence_weight = BayesianPruner.EVIDENCE_WEIGHT_STRONG
        else:
            # Moderate evidence
            evidence_weight = BayesianPruner.EVIDENCE_WEIGHT_BASELINE
        
        weight = evidence_score * (evidence_weight / 10.0)
        
        # 4. Update Posterior
        log_odds_posterior = log_odds_prior + weight
        p_posterior = 1 / (1 + math.exp(-log_odds_posterior))
        
        # 5. Convert back to percentage and clamp
        posterior_percent = p_posterior * 100.0
        return round(max(0.0, min(100.0, posterior_percent)), 1)
    
    @staticmethod
    def should_prune(confidence_percent: float) -> bool:
        """
        Determine if a hypothesis should be pruned based on Bayesian threshold.
        
        Args:
            confidence_percent: Current confidence as percentage (0-100)
        
        Returns:
            True if should be pruned (confidence < 15%)
        """
        return confidence_percent < (BayesianPruner.PRUNE_THRESHOLD * 100.0)

