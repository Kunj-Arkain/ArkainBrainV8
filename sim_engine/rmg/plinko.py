"""Plinko/Pachinko — Binomial distribution across pegs."""
import math
from sim_engine.rmg.base import BaseRMGEngine

# Standard multiplier maps by risk level and row count
PLINKO_MULTIPLIERS = {
    8: {
        "low":    [5.6, 2.1, 1.1, 1.0, 0.5, 1.0, 1.1, 2.1, 5.6],
        "medium": [13, 3, 1.3, 0.7, 0.4, 0.7, 1.3, 3, 13],
        "high":   [29, 4, 1.5, 0.3, 0.2, 0.3, 1.5, 4, 29],
    },
    12: {
        "low":    [10, 3, 1.6, 1.4, 1.1, 1.0, 0.5, 1.0, 1.1, 1.4, 1.6, 3, 10],
        "medium": [33, 11, 4, 2, 1.1, 0.6, 0.3, 0.6, 1.1, 2, 4, 11, 33],
        "high":   [170, 24, 8.1, 2, 0.7, 0.2, 0.2, 0.2, 0.7, 2, 8.1, 24, 170],
    },
    16: {
        "low":    [16, 9, 2, 1.4, 1.4, 1.2, 1.1, 1.0, 0.5, 1.0, 1.1, 1.2, 1.4, 1.4, 2, 9, 16],
        "medium": [110, 41, 10, 5, 3, 1.5, 1, 0.5, 0.3, 0.5, 1, 1.5, 3, 5, 10, 41, 110],
        "high":   [1000, 130, 26, 9, 4, 2, 0.2, 0.2, 0.2, 0.2, 0.2, 2, 4, 9, 26, 130, 1000],
    },
}


class PlinkoEngine(BaseRMGEngine):
    game_type = "plinko"
    display_name = "Plinko"
    house_edge_range = (0.01, 0.04)

    def generate_config(self, rows: int = 12, risk: str = "medium",
                        house_edge: float = 0.02, **kw) -> dict:
        rows = max(8, min(16, rows))
        if rows not in PLINKO_MULTIPLIERS:
            rows = 12
        risk = risk.lower() if risk.lower() in ("low", "medium", "high") else "medium"
        multipliers = PLINKO_MULTIPLIERS[rows][risk]

        # Adjust multipliers for target house edge
        theoretical_rtp = self._compute_rtp(rows, multipliers)
        target_rtp = 1.0 - house_edge
        if theoretical_rtp > 0:
            scale = target_rtp / theoretical_rtp
            multipliers = [round(m * scale, 2) for m in multipliers]

        return {
            "game_type": "plinko",
            "rows": rows,
            "risk": risk,
            "multipliers": multipliers,
            "house_edge": house_edge,
        }

    def compute_house_edge(self, config: dict) -> float:
        rows = config.get("rows", 12)
        mults = config.get("multipliers", [])
        if not mults:
            return config.get("house_edge", 0.02)
        rtp = self._compute_rtp(rows, mults)
        return max(0, 1.0 - rtp)

    def _compute_rtp(self, rows: int, multipliers: list) -> float:
        """Compute exact RTP from binomial probabilities."""
        n = rows
        slots = n + 1
        if len(multipliers) != slots:
            return 0.97
        total = 0.0
        for k in range(slots):
            prob = math.comb(n, k) / (2 ** n)
            total += prob * multipliers[k]
        return total

    def simulate_round(self, config: dict, rng) -> float:
        rows = config.get("rows", 12)
        multipliers = config.get("multipliers", PLINKO_MULTIPLIERS[12]["medium"])
        # Ball falls through rows, going left or right each time
        position = 0
        for _ in range(rows):
            position += rng.randint(0, 1)
        idx = min(position, len(multipliers) - 1)
        return multipliers[idx]
