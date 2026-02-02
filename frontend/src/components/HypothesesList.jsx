import React from 'react';
import HypothesisCard from './HypothesisCard';
import '../styles/HypothesesList.css';

function HypothesesList({ hypotheses, onStateUpdate, onRefresh, sessionId }) {
  if (!hypotheses || hypotheses.length === 0) {
    return <div className="hypotheses-empty">No hypotheses available.</div>;
  }

  // Extract number from hypothesis ID (hyp_1 -> 1, hyp_2 -> 2, etc.)
  // Sort by this number to maintain consistent order
  const getHypothesisNumber = (hypId) => {
    const match = hypId.match(/hyp_(\d+)/);
    return match ? parseInt(match[1], 10) : 999; // Put non-numbered hypotheses at end
  };

  // Sort hypotheses by their number to maintain consistent order
  const sortedHypotheses = [...hypotheses].sort((a, b) => {
    return getHypothesisNumber(a.id) - getHypothesisNumber(b.id);
  });

  return (
    <div className="hypotheses-list">
      {sortedHypotheses.map((hypothesis, index) => {
        const hypNumber = getHypothesisNumber(hypothesis.id);
        const displayNumber = hypNumber !== 999 ? hypNumber : index + 1;
        
        return (
          <HypothesisCard
            key={hypothesis.id}
            hypothesis={hypothesis}
            hypothesisNumber={displayNumber}
            onStateUpdate={onStateUpdate}
            onRefresh={onRefresh}
            sessionId={sessionId}
          />
        );
      })}
    </div>
  );
}

export default HypothesesList;

