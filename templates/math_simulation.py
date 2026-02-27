"""
Automated Slot Studio - Monte Carlo Simulation Template

This is the BASE template that the Mathematician Agent customizes per game.
The agent fills in reel strips, paytable values, and feature logic, then
executes this script via the MathSimulationTool.

Usage:
    python math_simulation.py [--spins 1000000] [--output results.json]
"""

import json
import logging
import sys
import argparse
from collections import defaultdict

# Logger outputs to stderr — stdout is reserved for JSON results
_sim_logger = logging.getLogger("arkainbrain.simulation")
if not _sim_logger.handlers:
    _sh = logging.StreamHandler(sys.stderr)
    _sh.setFormatter(logging.Formatter("%(message)s"))
    _sim_logger.addHandler(_sh)
    _sim_logger.setLevel(logging.INFO)
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

np.random.seed(42)


# ============================================================
# CONFIGURATION — The Math Agent fills these in per game
# ============================================================

# --- Grid Configuration ---
NUM_REELS = 5
NUM_ROWS = 3
WAYS_TO_WIN = 243  # For ways-to-win games; set to 0 for payline games

# --- Reel Strips ---
# Each reel is a list of symbols. The simulator randomly selects a
# starting position and takes NUM_ROWS consecutive symbols.
# The Math Agent designs these to achieve the target RTP.

REEL_STRIPS = {
    0: [  # Reel 1 (32 stops)
        "H1", "L1", "L2", "H2", "L3", "L4", "L1", "H3",
        "L2", "L3", "L4", "H4", "L1", "L2", "L3", "SC",
        "L4", "H1", "L1", "L2", "WD", "L3", "L4", "H2",
        "L1", "L2", "H5", "L3", "L4", "L1", "L2", "L3",
    ],
    1: [  # Reel 2 (32 stops)
        "L1", "H2", "L2", "L3", "L4", "H1", "L1", "L2",
        "H3", "L3", "L4", "L1", "SC", "L2", "L3", "H4",
        "L4", "L1", "L2", "WD", "L3", "H5", "L4", "L1",
        "L2", "L3", "H2", "L4", "L1", "L2", "L3", "L4",
    ],
    2: [  # Reel 3 (32 stops)
        "H1", "L2", "L3", "L4", "L1", "H3", "L2", "SC",
        "L3", "L4", "H2", "L1", "L2", "L3", "WD", "L4",
        "H4", "L1", "L2", "L3", "L4", "H5", "L1", "L2",
        "L3", "L4", "L1", "H1", "L2", "L3", "L4", "L1",
    ],
    3: [  # Reel 4 (32 stops)
        "L1", "L2", "H2", "L3", "L4", "L1", "H1", "L2",
        "L3", "H4", "L4", "L1", "L2", "SC", "L3", "L4",
        "H3", "L1", "L2", "L3", "WD", "L4", "H5", "L1",
        "L2", "L3", "L4", "L1", "L2", "H2", "L3", "L4",
    ],
    4: [  # Reel 5 (32 stops)
        "L2", "L3", "H1", "L4", "L1", "L2", "H3", "L3",
        "L4", "L1", "H2", "L2", "L3", "L4", "SC", "L1",
        "H4", "L2", "L3", "L4", "H5", "L1", "WD", "L2",
        "L3", "L4", "L1", "L2", "L3", "H1", "L4", "L1",
    ],
}

# --- Paytable ---
# Symbol: {count: payout_multiplier}
# Payout is multiplied by bet per line/way
PAYTABLE = {
    "H1": {3: 2.00, 4: 8.00, 5: 40.00},    # Highest pay symbol
    "H2": {3: 1.50, 4: 5.00, 5: 25.00},
    "H3": {3: 1.00, 4: 4.00, 5: 20.00},
    "H4": {3: 0.80, 4: 3.00, 5: 15.00},
    "H5": {3: 0.60, 4: 2.50, 5: 10.00},
    "L1": {3: 0.40, 4: 1.50, 5: 5.00},
    "L2": {3: 0.30, 4: 1.00, 5: 4.00},
    "L3": {3: 0.25, 4: 0.80, 5: 3.00},
    "L4": {3: 0.20, 4: 0.60, 5: 2.00},
    "WD": {},   # Wild — substitutes for all except Scatter
    "SC": {},   # Scatter — triggers free spins
}

WILD_SYMBOL = "WD"
SCATTER_SYMBOL = "SC"

# --- Feature Configuration ---
FREE_SPIN_TRIGGER = {3: 10, 4: 15, 5: 25}  # Scatter count → free spins awarded
FREE_SPIN_MULTIPLIER = 3  # Win multiplier during free spins
FREE_SPIN_RETRIGGER = True

# --- Targets ---
TARGET_RTP = 96.50
TARGET_VOLATILITY = "high"


# ============================================================
# SIMULATION ENGINE
# ============================================================

@dataclass
class SpinResult:
    """Result of a single spin."""
    grid: list[list[str]]
    base_win: float = 0.0
    scatter_count: int = 0
    free_spins_triggered: int = 0


@dataclass
class SimulationStats:
    """Accumulated statistics across all spins."""
    total_spins: int = 0
    total_wagered: float = 0.0
    total_won: float = 0.0
    base_game_won: float = 0.0
    feature_won: float = 0.0
    wins: int = 0
    free_spin_triggers: int = 0
    free_spins_played: int = 0
    max_win: float = 0.0
    win_distribution: dict = field(default_factory=lambda: defaultdict(int))


def spin_reels() -> list[list[str]]:
    """Generate a random grid by spinning all reels."""
    grid = []
    for reel_idx in range(NUM_REELS):
        strip = REEL_STRIPS[reel_idx]
        num_stops = len(strip)
        start_pos = np.random.randint(0, num_stops)
        column = []
        for row in range(NUM_ROWS):
            pos = (start_pos + row) % num_stops
            column.append(strip[pos])
        grid.append(column)
    return grid


def evaluate_ways_win(grid: list[list[str]]) -> float:
    """
    Evaluate wins using ways-to-win (left to right).
    For each paying symbol, count how many appear on each reel
    (including wilds), then multiply the ways together.
    """
    total_win = 0.0

    # Get unique paying symbols (exclude wild and scatter)
    paying_symbols = [s for s in PAYTABLE if s not in (WILD_SYMBOL, SCATTER_SYMBOL) and PAYTABLE[s]]

    for symbol in paying_symbols:
        # Count symbol + wild appearances per reel
        counts_per_reel = []
        consecutive_reels = 0

        for reel_idx in range(NUM_REELS):
            count = sum(
                1 for row in range(NUM_ROWS)
                if grid[reel_idx][row] == symbol or grid[reel_idx][row] == WILD_SYMBOL
            )
            if count > 0:
                counts_per_reel.append(count)
                consecutive_reels += 1
            else:
                break  # Must be consecutive from left

        if consecutive_reels < 3:
            continue

        # Check paytable for each valid length
        for length in range(consecutive_reels, 2, -1):  # Check longest first
            if length in PAYTABLE[symbol]:
                ways = 1
                for i in range(length):
                    ways *= counts_per_reel[i]
                win = PAYTABLE[symbol][length] * ways
                total_win += win
                break  # Only pay highest for each symbol

    return total_win


def count_scatters(grid: list[list[str]]) -> int:
    """Count scatter symbols anywhere on the grid."""
    count = 0
    for reel in grid:
        for symbol in reel:
            if symbol == SCATTER_SYMBOL:
                count += 1
    return count


def run_free_spins(num_spins: int) -> float:
    """
    Execute free spin rounds with multiplier.
    Returns total win from all free spins.
    """
    total_win = 0.0
    remaining = num_spins

    while remaining > 0:
        grid = spin_reels()
        win = evaluate_ways_win(grid) * FREE_SPIN_MULTIPLIER
        total_win += win
        remaining -= 1

        # Check for retrigger
        if FREE_SPIN_RETRIGGER:
            sc_count = count_scatters(grid)
            if sc_count >= 3 and sc_count in FREE_SPIN_TRIGGER:
                remaining += FREE_SPIN_TRIGGER[sc_count]

    return total_win


def categorize_win(win_amount: float) -> str:
    """Categorize a win into a distribution bucket."""
    if win_amount == 0:
        return "0x"
    elif win_amount < 1:
        return "0-1x"
    elif win_amount < 2:
        return "1-2x"
    elif win_amount < 5:
        return "2-5x"
    elif win_amount < 20:
        return "5-20x"
    elif win_amount < 100:
        return "20-100x"
    elif win_amount < 1000:
        return "100-1000x"
    else:
        return "1000x+"


# ============================================================
# MAIN SIMULATION
# ============================================================

def run_simulation(num_spins: int = 1_000_000) -> dict:
    """
    Execute the full Monte Carlo simulation.
    Returns a structured results dictionary.
    """
    stats = SimulationStats()
    bet_per_spin = 1.0  # Normalize to 1 unit bet

    _sim_logger.info(f"🎰 Running {num_spins:,} spin simulation...")

    for i in range(num_spins):
        if i > 0 and i % 250_000 == 0:
            current_rtp = (stats.total_won / stats.total_wagered * 100) if stats.total_wagered > 0 else 0
            _sim_logger.info(f"  [{i:>10,} / {num_spins:,}] Running RTP: {current_rtp:.4f}%")

        stats.total_spins += 1
        stats.total_wagered += bet_per_spin

        # Spin
        grid = spin_reels()
        base_win = evaluate_ways_win(grid)
        total_spin_win = base_win

        stats.base_game_won += base_win

        # Check for free spins
        scatter_count = count_scatters(grid)
        if scatter_count >= 3 and scatter_count in FREE_SPIN_TRIGGER:
            stats.free_spin_triggers += 1
            num_free_spins = FREE_SPIN_TRIGGER[scatter_count]
            stats.free_spins_played += num_free_spins
            feature_win = run_free_spins(num_free_spins)
            stats.feature_won += feature_win
            total_spin_win += feature_win

        # Track stats
        if total_spin_win > 0:
            stats.wins += 1
        stats.total_won += total_spin_win
        stats.max_win = max(stats.max_win, total_spin_win)
        stats.win_distribution[categorize_win(total_spin_win)] += 1

    # === Calculate Final Metrics ===
    measured_rtp = (stats.total_won / stats.total_wagered) * 100
    hit_frequency = (stats.wins / stats.total_spins) * 100
    base_rtp = (stats.base_game_won / stats.total_wagered) * 100
    feature_rtp = (stats.feature_won / stats.total_wagered) * 100

    # Standard deviation (volatility index)
    # Simplified: use coefficient of variation of wins
    avg_win = stats.total_won / stats.total_spins
    variance_approx = (stats.max_win - avg_win) ** 2 / stats.total_spins
    volatility_index = np.sqrt(variance_approx) if variance_approx > 0 else 0

    # Win distribution as percentages
    win_dist_pct = {
        bucket: (count / stats.total_spins * 100)
        for bucket, count in sorted(stats.win_distribution.items())
    }

    # Feature trigger frequency
    trigger_freq = (
        stats.total_spins / stats.free_spin_triggers
        if stats.free_spin_triggers > 0
        else float("inf")
    )

    # RTP confidence interval (normal approximation)
    rtp_std = np.sqrt(measured_rtp * (100 - measured_rtp) / stats.total_spins)
    ci_margin = 2.576 * rtp_std  # 99% CI
    rtp_ci = (measured_rtp - ci_margin, measured_rtp + ci_margin)

    # Jurisdiction compliance
    from config.settings import JURISDICTION_REQUIREMENTS
    jurisdiction_compliance = {}
    for jurisdiction, reqs in JURISDICTION_REQUIREMENTS.items():
        min_rtp = reqs.get("min_rtp", 0)
        jurisdiction_compliance[jurisdiction] = measured_rtp >= min_rtp

    results = {
        "simulation_config": {
            "total_spins": num_spins,
            "num_reels": NUM_REELS,
            "num_rows": NUM_ROWS,
            "ways_to_win": WAYS_TO_WIN,
            "target_rtp": TARGET_RTP,
            "target_volatility": TARGET_VOLATILITY,
        },
        "results": {
            "measured_rtp": round(measured_rtp, 4),
            "rtp_confidence_interval_99": [round(rtp_ci[0], 4), round(rtp_ci[1], 4)],
            "rtp_deviation_from_target": round(measured_rtp - TARGET_RTP, 4),
            "rtp_within_tolerance": abs(measured_rtp - TARGET_RTP) <= 0.5,
            "hit_frequency_pct": round(hit_frequency, 4),
            "base_game_rtp": round(base_rtp, 4),
            "feature_rtp": round(feature_rtp, 4),
            "volatility_index": round(volatility_index, 4),
            "max_win_achieved": round(stats.max_win, 2),
            "max_win_as_multiplier": f"{stats.max_win:.0f}x",
            "rtp_breakdown": {
                "base_game_lines": round(base_rtp, 4),
                "scatter_pays": 0,
                "free_games": round(feature_rtp, 4),
                "bonus_features": 0,
                "jackpots": 0,
            },
        },
        "feature_stats": {
            "free_spin_triggers": stats.free_spin_triggers,
            "free_spins_played": stats.free_spins_played,
            "avg_spins_between_triggers": round(trigger_freq, 1),
            "feature_rtp_contribution": round(feature_rtp, 4),
        },
        "win_distribution": win_dist_pct,
        "jurisdiction_compliance": jurisdiction_compliance,
        "summary": {
            "total_wagered": round(stats.total_wagered, 2),
            "total_won": round(stats.total_won, 2),
            "total_wins": stats.wins,
            "total_losses": stats.total_spins - stats.wins,
        },
    }

    # Print validation
    _sim_logger.info(f"\n{'='*60}")
    _sim_logger.info(f"  SIMULATION COMPLETE: {num_spins:,} spins")
    _sim_logger.info(f"  Measured RTP: {measured_rtp:.4f}% (target: {TARGET_RTP}%)")
    _sim_logger.info(f"  Deviation:    {measured_rtp - TARGET_RTP:+.4f}%")
    _sim_logger.info(f"  Within ±0.5%: {'✅ YES' if abs(measured_rtp - TARGET_RTP) <= 0.5 else '❌ NO'}")
    _sim_logger.info(f"  Hit Frequency: {hit_frequency:.2f}%")
    _sim_logger.info(f"  Max Win:      {stats.max_win:.0f}x")
    _sim_logger.info(f"  Base RTP:     {base_rtp:.4f}%")
    _sim_logger.info(f"  Feature RTP:  {feature_rtp:.4f}%")
    _sim_logger.info(f"{'='*60}")

    return results


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Slot Game Monte Carlo Simulation")
    parser.add_argument("--spins", type=int, default=1_000_000, help="Number of spins")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file path")
    args = parser.parse_args()

    results = run_simulation(args.spins)

    # Output as JSON to stdout (for the MathSimulationTool to capture)
    print(json.dumps(results, indent=2))

    # Optionally save to file
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(json.dumps(results, indent=2))
        _sim_logger.info(f"\n📄 Results saved to: {args.output}")
