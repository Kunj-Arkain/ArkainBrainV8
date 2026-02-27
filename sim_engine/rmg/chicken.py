"""Chicken Crossing — Sequential survival probability across lanes."""
from sim_engine.rmg.base import BaseRMGEngine


class ChickenEngine(BaseRMGEngine):
    game_type = "chicken"
    display_name = "Chicken Cross"
    house_edge_range = (0.02, 0.05)

    def generate_config(self, lanes: int = 5, hazards_per_lane: int = 1,
                        safe_spots: int = 4, house_edge: float = 0.03, **kw) -> dict:
        lanes = max(3, min(10, lanes))
        safe_spots = max(2, min(5, safe_spots))
        hazards_per_lane = max(1, min(safe_spots - 1, hazards_per_lane))
        # Compute multiplier per lane
        survive_prob = (safe_spots - hazards_per_lane) / safe_spots
        multipliers = []
        cumulative_prob = 1.0
        for i in range(lanes):
            cumulative_prob *= survive_prob
            fair_mult = (1.0 - house_edge) / cumulative_prob if cumulative_prob > 0 else 0
            multipliers.append(round(fair_mult, 2))

        return {
            "game_type": "chicken",
            "lanes": lanes,
            "hazards_per_lane": hazards_per_lane,
            "safe_spots": safe_spots,
            "multipliers": multipliers,
            "house_edge": house_edge,
        }

    def compute_house_edge(self, config: dict) -> float:
        return config.get("house_edge", 0.03)

    def simulate_round(self, config: dict, rng) -> float:
        lanes = config.get("lanes", 5)
        hazards = config.get("hazards_per_lane", 1)
        safe = config.get("safe_spots", 4)
        multipliers = config.get("multipliers", [1.5] * lanes)

        # Player picks how many lanes to cross (1 to lanes)
        target = rng.randint(1, lanes)

        for i in range(target):
            # Pick a spot in the lane
            spots = [0] * (safe - hazards) + [1] * hazards
            rng.shuffle(spots)
            chosen = rng.randint(0, safe - 1)
            if spots[chosen] == 1:
                return 0.0  # Hit hazard

        return multipliers[target - 1] if target <= len(multipliers) else 0.0
