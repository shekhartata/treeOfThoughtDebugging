"""
Simple test/demo script to demonstrate the Tree-of-Thought engine functionality.
Run this to see how the engine works without needing the full web interface.

NOTE: This demo requires OPENAI_API_KEY to be set in environment.
"""

from tot_engine import TreeOfThoughtEngine
from llm_integration import LLMIntegration
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def demo():
    """Run a simple demonstration of the ToT engine."""
    print("=" * 60)
    print("MongoDB Tree-of-Thought Debugging Tool - Demo")
    print("=" * 60)
    
    # Initialize LLM integration (required)
    print("\n0. Initializing LLM integration...")
    try:
        llm = LLMIntegration(require_llm=True)
        print("   ✓ LLM integration ready")
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        print("   Please set OPENAI_API_KEY environment variable")
        return
    
    # Initialize engine
    print("\n1. Initializing engine with problem statement...")
    engine = TreeOfThoughtEngine(llm_integration=llm)
    problem = "Writes slow on primary after deploy. Users reporting timeouts."
    
    try:
        initial_node = engine.initialize(problem)
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        return
    
    print(f"   Problem: {problem}")
    print(f"   Initial hypotheses: {len(initial_node.hypotheses)}")
    print(f"   Initial requests: {len(initial_node.requested_data)}")
    
    # Show initial hypotheses
    print("\n2. Initial Hypotheses:")
    for h in initial_node.hypotheses:
        print(f"   - {h.description} ({h.category}): {h.confidence:.2%}")
    
    # Simulate artifact upload 1
    print("\n3. Uploading artifact: db.currentOp() output")
    artifact1 = """
    {
      "inprog": [
        {
          "opid": 12345,
          "op": "query",
          "ns": "mydb.users",
          "command": {
            "find": "users",
            "filter": {"status": "active"},
            "planSummary": "COLLSCAN"
          },
          "millisRunning": 5000
        }
      ]
    }
    """
    try:
        node1 = engine.add_artifact("db.currentOp() output", artifact1)
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        return
    print(f"   Step: {node1.step_number}")
    print(f"   Active hypotheses: {sum(1 for h in node1.hypotheses if h.status == 'active')}")
    
    for h in node1.hypotheses:
        if h.status == "active" and h.evidence:
            print(f"   - {h.description}: confidence {h.confidence:.2%}, evidence: {h.evidence[-1]}")
    
    # Simulate artifact upload 2
    print("\n4. Uploading artifact: getIndexes() output")
    artifact2 = """
    {
      "indexes": [
        {
          "v": 2,
          "key": {"_id": 1},
          "name": "_id_"
        }
      ]
    }
    """
    try:
        node2 = engine.add_artifact("getIndexes() output", artifact2)
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        return
    print(f"   Step: {node2.step_number}")
    
    for h in node2.hypotheses:
        if h.status == "active":
            print(f"   - {h.description}: confidence {h.confidence:.2%}")
            if h.evidence:
                print(f"     Evidence: {', '.join(h.evidence)}")
    
    # Get next requests
    print("\n5. Next data requests:")
    try:
        next_reqs = engine.get_next_requests(node2)
        for req in next_reqs[:3]:
            print(f"   - {req}")
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        return
    
    # Check if complete
    print(f"\n6. Is complete? {engine.is_complete()}")
    
    # Get final analysis
    print("\n7. Final Analysis:")
    try:
        analysis = engine.get_final_analysis()
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        return
    print(f"   Root Cause: {analysis['root_cause']}")
    if analysis.get('confidence', 0) > 0:
        print(f"   Confidence: {analysis['confidence']:.2%}")
    if analysis.get('evidence'):
        print(f"   Evidence: {', '.join(analysis['evidence'][:2])}")
    print(f"   Mitigation: {analysis['mitigation'][:100]}...")
    
    # Tree summary
    print("\n8. Tree Summary:")
    summary = engine.get_tree_summary()
    print(f"   Total nodes: {summary['total_nodes']}")
    print(f"   Active hypotheses: {summary['active_hypotheses']}")
    print(f"   Accepted hypotheses: {summary['accepted_hypotheses']}")
    print(f"   Pruned hypotheses: {summary['pruned_hypotheses']}")
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)

if __name__ == "__main__":
    demo()

