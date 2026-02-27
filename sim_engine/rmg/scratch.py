"""Scratch Card — Prize distribution table."""
from sim_engine.rmg.base import BaseRMGEngine


class ScratchEngine(BaseRMGEngine):
    game_type = "scratch"
    display_name = "Scratch Card"
    house_edge_range = (0.05, 0.40)

    DEFAULT_PRIZES = [
        {"label": "Nothing", "multiplier": 0, "probability": 0.55},
        {"label": "Free Card", "multiplier": 1, "probability": 0.20},
        {"label": "2x", "multiplier": 2, "probability": 0.12},
        {"label": "5x", "multiplier": 5, "probability": 0.06},
        {"label": "10x", "multiplier": 10, "probability": 0.04},
        {"label": "25x", "multiplier": 25, "probability": 0.02},
        {"label": "100x", "multiplier": 100, "probability": 0.008},
        {"label": "500x", "multiplier": 500, "probability": 0.002},
    ]

    def generate_config(self, prizes: list = None, house_edge: float = 0.15, **kw) -> dict:
        pz = prizes or [dict(p) for p in self.DEFAULT_PRIZES]
        # Normalize probabilities
        total_prob = sum(p["probability"] for p in pz)
        if total_prob > 0:
            for p in pz:
                p["probability"] = p["probability"] / total_prob

        # Scale multipliers for target house edge
        rtp = sum(p["multiplier"] * p["probability"] for p in pz)
        target_rtp = 1.0 - house_edge
        if rtp > 0:
            scale = target_rtp / rtp
            for p in pz:
                if p["multiplier"] > 0:
                    p["multiplier"] = round(p["multiplier"] * scale, 2)

        return {"game_type": "scratch", "prizes": pz, "house_edge": house_edge}

    def compute_house_edge(self, config: dict) -> float:
        pz = config.get("prizes", self.DEFAULT_PRIZES)
        rtp = sum(p["multiplier"] * p["probability"] for p in pz)
        return max(0, 1.0 - rtp)

    def simulate_round(self, config: dict, rng) -> float:
        pz = config.get("prizes", self.DEFAULT_PRIZES)
        r = rng.random()
        cumulative = 0.0
        for p in pz:
            cumulative += p["probability"]
            if r <= cumulative:
                return p["multiplier"]
        return 0.0
