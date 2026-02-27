#!/usr/bin/env python3
"""
Automated Slot Studio - Main Entry Point

Usage:
    python main.py --theme "Ancient Egypt" --volatility high --target-rtp 96.5

    python main.py --interactive    # Guided parameter input

    python main.py --theme "..." --auto    # Skip HITL checkpoints
"""

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from config.settings import PipelineConfig
from models.schemas import GameIdeaInput, Volatility, FeatureType
from flows.pipeline import SlotStudioFlow, PipelineState

console = Console()

# ============================================================
# CLI Argument Parser
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="🎰 Automated Slot Studio — AI-Powered Slot Game Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic run with HITL checkpoints
  python main.py --theme "Ancient Egypt - Tomb of the Pharaoh" \\
                 --volatility high --target-rtp 96.5 --markets UK Malta Ontario

  # Full auto mode (no HITL pauses)
  python main.py --theme "Norse Mythology" --volatility medium --auto

  # Interactive guided mode
  python main.py --interactive

  # Load parameters from JSON file
  python main.py --from-json game_idea.json
        """
    )

    # Input modes
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--interactive", "-i", action="store_true",
                             help="Interactive guided parameter input")
    input_group.add_argument("--from-json", type=str,
                             help="Load parameters from a JSON file")

    # Game parameters
    parser.add_argument("--theme", type=str,
                        help="Core theme/concept for the slot game")
    parser.add_argument("--volatility", type=str,
                        choices=["low", "medium_low", "medium", "medium_high", "high"],
                        default="medium_high",
                        help="Target volatility tier")
    parser.add_argument("--target-rtp", type=float, default=96.0,
                        help="Target RTP percentage (default: 96.0)")
    parser.add_argument("--grid", type=str, default="5x3",
                        help="Grid configuration, e.g. '5x3' or '6x4'")
    parser.add_argument("--ways", type=str, default="243 ways",
                        help="Payline structure: '243 ways', '25 lines', 'megaways'")
    parser.add_argument("--max-win", type=int, default=5000,
                        help="Maximum win multiplier (default: 5000)")
    parser.add_argument("--markets", nargs="+", default=["Georgia", "Texas"],
                        help="Target jurisdictions (default: UK Malta)")
    parser.add_argument("--art-style", type=str, default="Cinematic, high-quality",
                        help="Art style direction")
    parser.add_argument("--features", type=str, nargs="+",
                        default=["free_spins", "multipliers"],
                        help="Game features (free_spins, multipliers, expanding_wilds, etc.)")
    parser.add_argument("--competitors", type=str, nargs="*", default=[],
                        help="Reference competitor games")
    parser.add_argument("--special", type=str, default=None,
                        help="Special requirements or constraints")

    # Pipeline options
    parser.add_argument("--auto", action="store_true",
                        help="Auto mode: skip all HITL checkpoints")
    parser.add_argument("--output-dir", type=str, default="./output",
                        help="Output directory (default: ./output)")

    return parser


# ============================================================
# Interactive Mode
# ============================================================

def interactive_input() -> GameIdeaInput:
    """Guided interactive parameter collection."""

    console.print(Panel(
        "[bold]🎰 Automated Slot Studio — Interactive Setup[/bold]\n\n"
        "Let's configure your new slot game.",
        border_style="cyan",
    ))

    # Theme
    theme = Prompt.ask(
        "\n[cyan]Game theme/concept[/cyan]",
        default="Ancient Egypt - Tomb of the Pharaoh"
    )

    # Markets
    markets_str = Prompt.ask(
        "[cyan]Target markets[/cyan] (comma-separated, any jurisdiction)",
        default="Georgia, Texas"
    )
    markets = [m.strip() for m in markets_str.split(",")]

    # Volatility
    vol = Prompt.ask(
        "[cyan]Volatility[/cyan]",
        choices=["low", "medium_low", "medium", "medium_high", "high", "very_high"],
        default="high"
    )

    # RTP
    rtp = float(Prompt.ask("[cyan]Target RTP %[/cyan]", default="96.5"))

    # Grid
    grid = Prompt.ask("[cyan]Grid config[/cyan] (e.g. 5x3)", default="5x3")
    cols, rows = grid.lower().split("x")

    # Ways
    ways = Prompt.ask(
        "[cyan]Payline structure[/cyan]",
        default="243 ways"
    )

    # Max win
    max_win = int(Prompt.ask("[cyan]Max win multiplier[/cyan]", default="5000"))

    # Art style
    art_style = Prompt.ask(
        "[cyan]Art style direction[/cyan]",
        default="Dark, cinematic, AAA quality"
    )

    # Features
    console.print("\n[cyan]Available features:[/cyan]")
    feature_options = [f.value for f in FeatureType]
    for i, f in enumerate(feature_options):
        console.print(f"  {i}: {f}")
    feat_input = Prompt.ask(
        "[cyan]Select features[/cyan] (comma-separated numbers or names)",
        default="0,1,2"
    )
    features = []
    for item in feat_input.split(","):
        item = item.strip()
        try:
            idx = int(item)
            features.append(FeatureType(feature_options[idx]))
        except (ValueError, IndexError):
            try:
                features.append(FeatureType(item))
            except ValueError:
                console.print(f"[yellow]⚠ Unknown feature: {item}, skipping[/yellow]")

    # Competitors
    comp_str = Prompt.ask(
        "[cyan]Reference competitors[/cyan] (comma-separated, or Enter to skip)",
        default=""
    )
    competitors = [c.strip() for c in comp_str.split(",") if c.strip()]

    # Special requirements
    special = Prompt.ask(
        "[cyan]Special requirements[/cyan] (or Enter to skip)",
        default=""
    ) or None

    return GameIdeaInput(
        theme=theme,
        target_markets=markets,
        volatility=Volatility(vol),
        target_rtp=rtp,
        grid_cols=int(cols),
        grid_rows=int(rows),
        ways_or_lines=ways,
        max_win_multiplier=max_win,
        art_style=art_style,
        requested_features=features,
        competitor_references=competitors,
        special_requirements=special,
    )


# ============================================================
# Main
# ============================================================

def main():
    parser = build_parser()
    args = parser.parse_args()

    console.print(Panel(
        "[bold]🎰 Automated Slot Studio[/bold]\n"
        "[dim]AI-Powered Slot Game Development Pipeline[/dim]",
        border_style="bright_blue",
    ))

    # --- Collect Input ---
    if args.interactive:
        game_idea = interactive_input()
    elif args.from_json:
        json_path = Path(args.from_json)
        if not json_path.exists():
            console.print(f"[red]Error: File not found: {args.from_json}[/red]")
            sys.exit(1)
        data = json.loads(json_path.read_text())
        game_idea = GameIdeaInput(**data)
    elif args.theme:
        # Parse grid
        try:
            cols, rows = args.grid.lower().split("x")
        except ValueError:
            cols, rows = "5", "3"

        # Parse features
        features = []
        for f in args.features:
            try:
                features.append(FeatureType(f))
            except ValueError:
                console.print(f"[yellow]⚠ Unknown feature '{f}', skipping[/yellow]")

        game_idea = GameIdeaInput(
            theme=args.theme,
            target_markets=args.markets,
            volatility=Volatility(args.volatility),
            target_rtp=args.target_rtp,
            grid_cols=int(cols),
            grid_rows=int(rows),
            ways_or_lines=args.ways,
            max_win_multiplier=args.max_win,
            art_style=args.art_style,
            requested_features=features,
            competitor_references=args.competitors or [],
            special_requirements=args.special,
        )
    else:
        parser.print_help()
        console.print("\n[yellow]Provide --theme, --interactive, or --from-json[/yellow]")
        sys.exit(1)

    # --- Set output directory ---
    import os
    os.environ["OUTPUT_DIR"] = args.output_dir

    # --- Print config summary ---
    console.print(Panel(
        f"[bold]Configuration:[/bold]\n\n"
        f"  Theme:      {game_idea.theme}\n"
        f"  Markets:    {', '.join(game_idea.target_markets)}\n"
        f"  Volatility: {game_idea.volatility.value}\n"
        f"  RTP:        {game_idea.target_rtp}%\n"
        f"  Grid:       {game_idea.grid_cols}x{game_idea.grid_rows}\n"
        f"  Ways:       {game_idea.ways_or_lines}\n"
        f"  Max Win:    {game_idea.max_win_multiplier}x\n"
        f"  Features:   {[f.value for f in game_idea.requested_features]}\n"
        f"  Art Style:  {game_idea.art_style}\n"
        f"  Competitors:{game_idea.competitor_references}\n"
        f"  Auto Mode:  {args.auto}\n"
        f"  Output Dir: {args.output_dir}",
        border_style="cyan",
    ))

    if not args.auto:
        if not Confirm.ask("\n[bold]Proceed with pipeline?[/bold]", default=True):
            console.print("[yellow]Aborted.[/yellow]")
            sys.exit(0)

    # --- Initialize and Run Flow ---
    initial_state = PipelineState(game_idea=game_idea)

    flow = SlotStudioFlow(auto_mode=args.auto)
    flow.state = initial_state

    try:
        final_state = flow.kickoff()
        console.print("\n[bold green]🎉 Pipeline completed successfully![/bold green]")

        if hasattr(final_state, "output_dir"):
            console.print(f"\n📁 Your game package is at: {final_state.output_dir}")

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Pipeline interrupted by user.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]❌ Pipeline failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
