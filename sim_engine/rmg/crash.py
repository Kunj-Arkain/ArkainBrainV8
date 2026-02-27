"""Crash Game — Exponential distribution with crash point."""
import math
from sim_engine.rmg.base import BaseRMGEngine


class CrashEngine(BaseRMGEngine):
    game_type = "crash"
    display_name = "Crash"
    house_edge_range = (0.01, 0.05)

    def generate_config(self, house_edge: float = 0.03, max_multiplier: float = 1000,
                        auto_cashout_options: list = None, **kw) -> dict:
        house_edge = max(0.005, min(0.10, house_edge))
        return {
            "game_type": "crash",
            "house_edge": house_edge,
            "max_multiplier": max_multiplier,
            "auto_cashout_options": auto_cashout_options or [1.5, 2.0, 5.0, 10.0, 50.0],
        }

    def compute_house_edge(self, config: dict) -> float:
        return config.get("house_edge", 0.03)

    def simulate_round(self, config: dict, rng) -> float:
        """Simulate a crash round. Returns the crash point multiplier.
        For RTP measurement, assumes optimal player cashing out at 2x.
        True game RTP = 1 - house_edge regardless of cashout target."""
        he = config.get("house_edge", 0.03)
        max_mult = config.get("max_multiplier", 1000)

        # Generate crash point from inverse CDF
        r = rng.random()
        if r == 0:
            r = 0.0001

        # Crash point follows: P(crash < x) = 1 - (1-he)/x for x >= 1
        # Inverse: crash_point = (1-he) / (1-r)
        crash_point = (1.0 - he) / (1.0 - r)
        crash_point = min(crash_point, max_mult)

        # For simulation: assume player auto-cashouts at 2x (standard benchmark)
        target = 2.0
        if crash_point >= target:
            return target
        return 0.0
