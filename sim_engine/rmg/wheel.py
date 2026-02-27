"""Wheel Spin — Weighted segments with multipliers."""
from sim_engine.rmg.base import BaseRMGEngine


class WheelEngine(BaseRMGEngine):
    game_type = "wheel"
    display_name = "Wheel Spin"
    house_edge_range = (0.02, 0.08)

    DEFAULT_SEGMENTS = [
        {"label": "0x", "multiplier": 0, "weight": 10},
        {"label": "1x", "multiplier": 1, "weight": 25},
        {"label": "1.5x", "multiplier": 1.5, "weight": 20},
        {"label": "2x", "multiplier": 2, "weight": 15},
        {"label": "3x", "multiplier": 3, "weight": 10},
        {"label": "5x", "multiplier": 5, "weight": 8},
        {"label": "10x", "multiplier": 10, "weight": 5},
        {"label": "25x", "multiplier": 25, "weight": 4},
        {"label": "50x", "multiplier": 50, "weight": 2},
        {"label": "100x", "multiplier": 100, "weight": 1},
    ]

    def generate_config(self, segments: list = None, house_edge: float = 0.05, **kw) -> dict:
        segs = segments or list(self.DEFAULT_SEGMENTS)
        # Adjust weights to hit target house edge
        rtp = self._compute_rtp(segs)
        target_rtp = 1.0 - house_edge
        if rtp > 0:
            scale = target_rtp / rtp
            for s in segs:
                s["multiplier"] = round(s["multiplier"] * scale, 2)
        return {"game_type": "wheel", "segments": segs, "house_edge": house_edge}

    def compute_house_edge(self, config: dict) -> float:
        segs = config.get("segments", self.DEFAULT_SEGMENTS)
        return max(0, 1.0 - self._compute_rtp(segs))

    def _compute_rtp(self, segments: list) -> float:
        total_weight = sum(s["weight"] for s in segments)
        if total_weight == 0:
            return 0
        return sum(s["multiplier"] * s["weight"] / total_weight for s in segments)

    def simulate_round(self, config: dict, rng) -> float:
        segs = config.get("segments", self.DEFAULT_SEGMENTS)
        total_weight = sum(s["weight"] for s in segs)
        r = rng.uniform(0, total_weight)
        cumulative = 0
        for s in segs:
            cumulative += s["weight"]
            if r <= cumulative:
                return s["multiplier"]
        return segs[-1]["multiplier"]
