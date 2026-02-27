"""Dice — Uniform distribution with over/under threshold."""
from sim_engine.rmg.base import BaseRMGEngine


class DiceEngine(BaseRMGEngine):
    game_type = "dice"
    display_name = "Dice"
    house_edge_range = (0.01, 0.01)  # Fixed 1% standard

    def generate_config(self, house_edge: float = 0.01, range_max: int = 10000,
                        default_target: float = 50.0, **kw) -> dict:
        return {
            "game_type": "dice",
            "house_edge": max(0.005, min(0.05, house_edge)),
            "range_max": range_max,
            "default_target": default_target,
        }

    def compute_house_edge(self, config: dict) -> float:
        return config.get("house_edge", 0.01)

    def simulate_round(self, config: dict, rng) -> float:
        he = config.get("house_edge", 0.01)
        range_max = config.get("range_max", 10000)

        # Player picks over/under and target
        over = rng.random() < 0.5
        target_pct = rng.uniform(10, 90)  # Random target %
        threshold = target_pct / 100.0 * range_max

        # Roll
        roll = rng.uniform(0, range_max)

        # Win probability
        if over:
            win_prob = 1.0 - (threshold / range_max)
        else:
            win_prob = threshold / range_max

        # Fair multiplier with house edge
        if win_prob <= 0 or win_prob >= 1:
            return 0.0
        multiplier = (1.0 - he) / win_prob

        # Check win
        if over and roll > threshold:
            return multiplier
        elif not over and roll < threshold:
            return multiplier
        return 0.0
