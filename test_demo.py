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
        # add_artifact now returns list of nodes (one per branch)
        nodes1 = engine.add_artifact("db.currentOp() output", artifact1)
        engine.prune_hypotheses()
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        return
    print(f"   Created {len(nodes1)} nodes across branches")
    
    # Get root node to show hypotheses
    root_node = engine.get_current_node()
    if root_node:
        active_count = sum(1 for h in root_node.hypotheses if h.status == 'active')
        print(f"   Active branches: {active_count}")
        
        for h in root_node.hypotheses:
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
        nodes2 = engine.add_artifact("getIndexes() output", artifact2)
        engine.prune_hypotheses()
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        return
    print(f"   Created {len(nodes2)} nodes across branches")
    
    # Get root node to show updated hypotheses
    root_node = engine.get_current_node()
    if root_node:
        for h in root_node.hypotheses:
            if h.status == "active":
                print(f"   - {h.description}: confidence {h.confidence:.2%}")
                if h.evidence:
                    print(f"     Evidence: {', '.join(h.evidence[-2:])}")
    
    # Get next requests
    print("\n5. Next data requests:")
    try:
        next_reqs = engine.get_next_requests()
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
    
    # Test backtrack functionality
    print("\n9. Testing Backtrack Functionality:")
    try:
        # Get current node before backtrack
        current_before = engine.get_current_node()
        if current_before:
            print(f"   Current node before backtrack: {current_before.id} (Step {current_before.step_number})")
            
            # Get root node to backtrack to
            root_node = engine._get_node(engine.root_node_id) if engine.root_node_id else None
            if root_node and root_node.id != current_before.id:
                print(f"   Backtracking to root node: {root_node.id} (Step {root_node.step_number})")
                engine.backtrack(node_id=root_node.id)
                
                # Get current node after backtrack
                current_after = engine.get_current_node()
                if current_after:
                    print(f"   Current node after backtrack: {current_after.id} (Step {current_after.step_number})")
                    if current_after.id == root_node.id:
                        print("   ✓ Backtrack successful!")
                    else:
                        print("   ✗ Backtrack failed - current node doesn't match target")
                else:
                    print("   ✗ Error: Could not get current node after backtrack")
            else:
                print("   (Skipping backtrack test - already at root or root not found)")
        else:
            print("   ✗ Error: Could not get current node")
    except Exception as e:
        print(f"   ✗ Error during backtrack test: {e}")
    
    # Test history/tree structure
    print("\n10. Tree Structure (for UI visualization):")
    try:
        # Get all nodes from engine
        all_nodes = engine.nodes if hasattr(engine, 'nodes') else []
        print(f"   Total nodes in tree: {len(all_nodes)}")
        
        # Show tree structure
        root = engine._get_node(engine.root_node_id) if engine.root_node_id else None
        if root:
            def print_tree(node_id, level=0):
                try:
                    node = engine._get_node(node_id)
                    if not node:
                        return
                    indent = "  " * level
                    node_type = "Root" if level == 0 else f"Node"
                    step_info = f"Step {node.step_number}"
                    if node.hypothesis:
                        hyp_info = f"Hyp: {node.hypothesis.description[:40]}..."
                    else:
                        hyp_count = len(node.hypotheses) if hasattr(node, 'hypotheses') and node.hypotheses else 0
                        hyp_info = f"Hypotheses: {hyp_count}"
                    print(f"   {indent}{node_type} {node_id[:8]}... ({step_info}) - {hyp_info}")
                    if hasattr(node, 'children_ids') and node.children_ids:
                        for child_id in node.children_ids:
                            print_tree(child_id, level + 1)
                except Exception as e:
                    print(f"   {'  ' * level}Error getting node {node_id[:8]}...: {e}")
            
            print("   Tree structure:")
            print_tree(root.id)
    except Exception as e:
        print(f"   ✗ Error getting tree structure: {e}")
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)

if __name__ == "__main__":
    demo()

