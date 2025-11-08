"""
Command-line interface for MongoDB Tree-of-Thought Debugging Tool
Alternative to web interface for terminal-based usage.
"""

from tot_engine import TreeOfThoughtEngine
from llm_integration import LLMIntegration
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

console = Console()


class CLIDebuggingTool:
    """Command-line interface for the debugging tool."""
    
    def __init__(self):
        self.engine: TreeOfThoughtEngine = None
        # LLM is now REQUIRED by default
        self.llm = LLMIntegration(require_llm=True)
        self.console = console
    
    def run(self):
        """Main interactive loop."""
        self.console.print(Panel.fit(
            "[bold cyan]MongoDB Tree-of-Thought Debugging Tool[/bold cyan]\n"
            "Interactive debugging assistant for Consulting Engineers",
            border_style="cyan"
        ))
        
        # Initialize session
        problem_summary = Prompt.ask("\n[bold]Enter problem summary[/bold]")
        
        # Ask if user wants to use fallback mode
        use_fallback = False
        if self.llm.use_llm:
            use_fallback = not Confirm.ask(
                "\n[bold]Use LLM for hypothesis generation?[/bold] (recommended)",
                default=True
            )
        else:
            self.console.print("[yellow]⚠️  LLM not available. Using fallback mode.[/yellow]")
            use_fallback = True
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Initializing with LLM..." if not use_fallback else "Initializing (fallback mode)...", total=None)
            self.engine = TreeOfThoughtEngine(llm_integration=self.llm)
            initial_node = self.engine.initialize(problem_summary, use_hardcoded_fallback=use_fallback)
            progress.update(task, completed=True)
        
        self.console.print("\n[green]✓ Session initialized![/green]\n")
        
        # Main loop
        while True:
            self._display_current_state()
            
            if self.engine.is_complete():
                if Confirm.ask("\n[bold]Sufficient data gathered. Get final analysis?[/bold]"):
                    self._show_final_analysis()
                    break
            
            action = Prompt.ask(
                "\n[bold]What would you like to do?[/bold]",
                choices=["upload", "backtrack", "final", "reset", "quit"],
                default="upload"
            )
            
            if action == "upload":
                self._upload_artifact()
            elif action == "backtrack":
                self._backtrack()
            elif action == "final":
                self._show_final_analysis()
                break
            elif action == "reset":
                if Confirm.ask("Are you sure you want to reset the session? This will clear all tree content."):
                    self.engine = None
                    self.console.print("[green]✓ Session reset. Starting fresh...[/green]\n")
                    # Restart the main loop
                    self.run()
                    break
            elif action == "quit":
                if Confirm.ask("Are you sure you want to quit?"):
                    break
    
    def _display_current_state(self):
        """Display current reasoning state."""
        node = self.engine.get_current_node()
        summary = self.engine.get_tree_summary()
        
        # Summary table
        summary_table = Table(title="Session Summary", show_header=True, header_style="bold cyan")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="magenta")
        
        summary_table.add_row("Step", str(summary.get('current_step', node.step_number if node else 1)))
        summary_table.add_row("Total Nodes", str(summary['total_nodes']))
        summary_table.add_row("Active Branches", str(summary.get('active_branches', summary['active_hypotheses'])))
        summary_table.add_row("Accepted", str(summary['accepted_hypotheses']))
        summary_table.add_row("Pruned", str(summary['pruned_hypotheses']))
        
        self.console.print(summary_table)
        
        # Hypotheses table (from root node)
        hyp_table = Table(title="All Hypotheses (Branches)", show_header=True, header_style="bold cyan")
        hyp_table.add_column("ID", style="cyan")
        hyp_table.add_column("Description", style="white")
        hyp_table.add_column("Category", style="yellow")
        hyp_table.add_column("Confidence", style="green")
        hyp_table.add_column("Status", style="magenta")
        
        if node and node.hypotheses:
            for h in node.hypotheses:
                confidence_color = "green" if h.confidence >= 0.7 else "yellow" if h.confidence >= 0.4 else "red"
                status_color = "green" if h.status == "active" else "blue" if h.status == "accepted" else "red"
                hyp_table.add_row(
                    h.id,
                    h.description,
                    h.category,
                    f"[{confidence_color}]{h.confidence:.2%}[/{confidence_color}]",
                    f"[{status_color}]{h.status}[/{status_color}]"
                )
        
        self.console.print("\n")
        self.console.print(hyp_table)
        
        # Next requests
        next_requests = self.engine.get_next_requests()
        if next_requests:
            requests_text = "\n".join([f"  • {req}" for req in next_requests])
            self.console.print(Panel(
                f"[bold]Next Data Requests:[/bold]\n{requests_text}",
                title="📋",
                border_style="blue"
            ))
    
    def _upload_artifact(self):
        """Handle artifact upload."""
        artifact_name = Prompt.ask("\n[bold]Artifact name[/bold]")
        
        self.console.print("\n[dim]Enter artifact content (end with 'END' on a new line):[/dim]")
        lines = []
        while True:
            line = input()
            if line.strip() == "END":
                break
            lines.append(line)
        
        artifact_content = "\n".join(lines)
        
        if not artifact_content.strip():
            self.console.print("[red]No content provided. Skipping.[/red]")
            return
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Processing artifact across all active branches...", total=None)
            
            try:
                # LLM evaluation is now handled inside add_artifact()
                # Returns list of nodes (one per branch)
                new_nodes = self.engine.add_artifact(artifact_name, artifact_content)
                self.engine.prune_hypotheses()
                progress.update(task, completed=True)
            except ValueError as e:
                progress.update(task, completed=True)
                self.console.print(f"\n[red]Error: {e}[/red]")
                return
        
        self.console.print(f"\n[green]✓ Artifact processed! Created {len(new_nodes)} nodes across branches.[/green]")
        
        # Show evidence found across all branches
        evidence_found = []
        root_node = self.engine.get_current_node()
        if root_node:
            for h in root_node.hypotheses:
                if h.evidence:
                    # Get latest evidence
                    latest_evidence = h.evidence[-1] if h.evidence else None
                    if latest_evidence:
                        evidence_found.append((h.description, latest_evidence))
        
        if evidence_found:
            evidence_text = "\n".join([f"  • {desc}: {ev}" for desc, ev in evidence_found])
            self.console.print(Panel(
                f"[bold]New Evidence Found:[/bold]\n{evidence_text}",
                border_style="green"
            ))
    
    def _backtrack(self):
        """Handle backtracking to previous nodes or focusing on branches."""
        # Show branches
        branches = self.engine.get_all_branches_for_ui()
        
        if not branches:
            self.console.print("[yellow]No branches available.[/yellow]")
            return
        
        # Show branches
        branches_table = Table(title="Available Branches", show_header=True)
        branches_table.add_column("Hypothesis ID", style="cyan")
        branches_table.add_column("Description", style="white")
        branches_table.add_column("Status", style="magenta")
        branches_table.add_column("Depth", style="yellow")
        
        for branch in branches:
            status_color = "green" if branch['status'] == 'active' else "blue" if branch['status'] == 'accepted' else "red"
            branches_table.add_row(
                branch['hypothesis_id'],
                branch['hypothesis']['description'],
                f"[{status_color}]{branch['status']}[/{status_color}]",
                str(branch['depth'])
            )
        
        self.console.print(branches_table)
        
        # Ask user what to do
        action = Prompt.ask(
            "\n[bold]Backtrack to node or focus on branch?[/bold]",
            choices=["node", "branch"],
            default="branch"
        )
        
        if action == "node":
            # Show history
            history_table = Table(title="Reasoning History", show_header=True)
            history_table.add_column("Step", style="cyan")
            history_table.add_column("Node ID", style="yellow")
            history_table.add_column("Branch", style="white")
            history_table.add_column("Artifacts", style="white")
            
            for n in self.engine.nodes:
                branch_id = n.hypothesis_id or "root"
                history_table.add_row(
                    str(n.step_number),
                    n.id,
                    branch_id,
                    str(len(n.artifacts_received))
                )
            
            self.console.print(history_table)
            
            node_id = Prompt.ask("\n[bold]Enter node ID to backtrack to[/bold]")
            
            try:
                self.engine.backtrack(node_id=node_id)
                self.console.print(f"[green]✓ Backtracked to {node_id}[/green]")
            except ValueError as e:
                self.console.print(f"[red]Error: {e}[/red]")
        else:
            # Focus on branch
            hypothesis_id = Prompt.ask("\n[bold]Enter hypothesis ID to focus on[/bold]")
            
            try:
                self.engine.backtrack(hypothesis_id=hypothesis_id)
                self.console.print(f"[green]✓ Focused on branch {hypothesis_id}[/green]")
            except ValueError as e:
                self.console.print(f"[red]Error: {e}[/red]")
    
    def _show_final_analysis(self):
        """Display final root cause analysis."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Generating final analysis...", total=None)
            
            try:
                # get_final_analysis() now uses LLM internally
                engine_analysis = self.engine.get_final_analysis()
                progress.update(task, completed=True)
            except ValueError as e:
                progress.update(task, completed=True)
                self.console.print(f"\n[red]Error: {e}[/red]")
                return
        
        # Check if all hypotheses were pruned
        all_pruned = engine_analysis.get('all_hypotheses_pruned', False)
        warning_msg = ""
        if all_pruned:
            warning_msg = "\n[yellow]⚠️  Note: All initial hypotheses were pruned based on available artifacts.[/yellow]\n[yellow]Recommendations below are based on the problem description and collected artifacts.[/yellow]\n"
        
        # Display analysis
        analysis_text = f"""{warning_msg}
[bold]Root Cause:[/bold] {engine_analysis['root_cause']}
[bold]Category:[/bold] {engine_analysis.get('category', 'N/A')}
[bold]Confidence:[/bold] {engine_analysis['confidence']:.2%}
"""
        
        if engine_analysis.get('evidence'):
            analysis_text += "\n[bold]Evidence:[/bold]\n"
            for ev in engine_analysis['evidence']:
                analysis_text += f"  • {ev}\n"
        
        analysis_text += f"\n[bold]Mitigation:[/bold]\n{engine_analysis['mitigation']}\n"
        
        analysis_text += "\n[bold]Next Steps:[/bold]\n"
        for step in engine_analysis['next_steps']:
            analysis_text += f"  • {step}\n"
        
        if engine_analysis.get('alternative_hypotheses'):
            analysis_text += "\n[bold]Alternative Hypotheses:[/bold]\n"
            for alt in engine_analysis['alternative_hypotheses']:
                analysis_text += f"  • {alt['description']} ({alt['confidence']:.2%})\n"
        
        self.console.print(Panel(
            analysis_text,
            title="🔍 Root Cause Analysis",
            border_style="green"
        ))
        
        # Show raw LLM analysis if available
        if engine_analysis.get('raw_llm_analysis'):
            self.console.print(Panel(
                engine_analysis['raw_llm_analysis'],
                title="🤖 LLM Analysis",
                border_style="blue"
            ))


def main():
    """Main entry point."""
    try:
        tool = CLIDebuggingTool()
        tool.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user. Exiting...[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()

