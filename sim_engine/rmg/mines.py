"""Mines — Combinatorial probability (n choose k)."""
import math
from sim_engine.rmg.base import BaseRMGEngine


class MinesEngine(BaseRMGEngine):
    game_type = "mines"
    display_name = "Mines"
    house_edge_range = (0.01, 0.05)

    def generate_config(self, grid_size: int = 25, mine_count: int = 5,
                        house_edge: float = 0.03, **kw) -> dict:
        grid_size = max(9, min(36, grid_size))
        mine_count = max(1, min(grid_size - 1, mine_count))
        return {
            "game_type": "mines",
            "grid_size": grid_size,
            "mine_count": mine_count,
            "house_edge": house_edge,
        }

    def compute_house_edge(self, config: dict) -> float:
        return config.get("house_edge", 0.03)

    def _multiplier_at_step(self, config: dict, step: int) -> float:
        """Compute the fair multiplier for revealing step-th safe tile."""
        gs = config["grid_size"]
        mc = config["mine_count"]
        he = config["house_edge"]
        safe = gs - mc
        if step > safe or step < 1:
            return 0.0
        # Fair probability of surviving step tiles
        prob = 1.0
        for i in range(step):
            prob *= (safe - i) / (gs - i)
        if prob <= 0:
            return 0.0
        return (1.0 - he) / prob

    def simulate_round(self, config: dict, rng) -> float:
        gs = config["grid_size"]
        mc = config["mine_count"]
        safe = gs - mc
        # Player picks a random number of tiles to reveal (1-5 on average)
        target_reveals = min(rng.randint(1, 5), safe)

        # Simulate mine placement
        tiles = [0] * safe + [1] * mc
        rng.shuffle(tiles)

        # Reveal tiles one by one
        for step in range(1, target_reveals + 1):
            if tiles[step - 1] == 1:  # Hit a mine
                return 0.0

        # Cashed out successfully
        return self._multiplier_at_step(config, target_reveals)
