"""
ARKAINBRAIN — Base RMG Engine (Phase 7)

Abstract base for all mini RMG game math models.
"""

import hashlib
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SimResult:
    """Simulation results for an RMG mini-game."""
    game_type: str
    rounds: int
    house_edge_theoretical: float
    house_edge_measured: float
    avg_multiplier: float
    max_multiplier_hit: float
    hit_rate: float  # % of rounds that returned > 0
    total_wagered: float
    total_returned: float
    rtp: float  # 1 - house_edge_measured
    confidence_95: tuple = (0.0, 0.0)
    distribution: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "game_type": self.game_type,
            "rounds": self.rounds,
            "house_edge_theoretical": round(self.house_edge_theoretical, 6),
            "house_edge_measured": round(self.house_edge_measured, 6),
            "rtp": round(self.rtp, 4),
            "avg_multiplier": round(self.avg_multiplier, 4),
            "max_multiplier_hit": round(self.max_multiplier_hit, 2),
            "hit_rate": round(self.hit_rate, 4),
            "total_wagered": round(self.total_wagered, 2),
            "total_returned": round(self.total_returned, 2),
            "confidence_95": [round(x, 6) for x in self.confidence_95],
            "distribution": self.distribution,
        }


class BaseRMGEngine(ABC):
    """Abstract base for all RMG mini-game math models."""

    game_type: str = "base"
    display_name: str = "Base Game"
    house_edge_range: tuple = (0.01, 0.10)

    @abstractmethod
    def generate_config(self, **kwargs) -> dict:
        """Generate a game configuration dict from parameters."""
        ...

    @abstractmethod
    def compute_house_edge(self, config: dict) -> float:
        """Compute the theoretical house edge for a config."""
        ...

    @abstractmethod
    def simulate_round(self, config: dict, rng) -> float:
        """Simulate one round. Returns multiplier (0 = loss)."""
        ...

    def simulate(self, config: dict, rounds: int = 100_000, seed: int = 42) -> SimResult:
        """Run a Monte Carlo simulation."""
        import random
        rng = random.Random(seed)

        total_wagered = 0.0
        total_returned = 0.0
        wins = 0
        max_mult = 0.0
        buckets = {}  # multiplier range → count

        for _ in range(rounds):
            total_wagered += 1.0
            mult = self.simulate_round(config, rng)
            total_returned += mult
            if mult > 0:
                wins += 1
            if mult > max_mult:
                max_mult = mult

            # Bucket distribution
            if mult == 0:
                bucket = "0x"
            elif mult < 2:
                bucket = "1-2x"
            elif mult < 5:
                bucket = "2-5x"
            elif mult < 10:
                bucket = "5-10x"
            elif mult < 50:
                bucket = "10-50x"
            elif mult < 100:
                bucket = "50-100x"
            else:
                bucket = "100x+"
            buckets[bucket] = buckets.get(bucket, 0) + 1

        rtp = total_returned / total_wagered if total_wagered > 0 else 0
        he_measured = 1 - rtp
        avg_mult = total_returned / rounds
        hit_rate = wins / rounds

        # 95% confidence interval for house edge
        import math as m
        variance = sum((self.simulate_round(config, random.Random(seed + i)) - avg_mult) ** 2
                       for i in range(min(1000, rounds))) / min(1000, rounds)
        std_err = m.sqrt(variance / rounds) if rounds > 0 else 0
        ci = (he_measured - 1.96 * std_err, he_measured + 1.96 * std_err)

        return SimResult(
            game_type=self.game_type,
            rounds=rounds,
            house_edge_theoretical=self.compute_house_edge(config),
            house_edge_measured=he_measured,
            avg_multiplier=avg_mult,
            max_multiplier_hit=max_mult,
            hit_rate=hit_rate,
            total_wagered=total_wagered,
            total_returned=total_returned,
            rtp=rtp,
            confidence_95=ci,
            distribution={k: round(v / rounds, 4) for k, v in sorted(buckets.items())},
        )

    @staticmethod
    def provably_fair_hash(server_seed: str, client_seed: str, nonce: int) -> str:
        """Generate a provably fair hash for a round."""
        combined = f"{server_seed}:{client_seed}:{nonce}"
        return hashlib.sha256(combined.encode()).hexdigest()

    @staticmethod
    def hash_to_float(hash_hex: str) -> float:
        """Convert first 8 hex chars to float in [0, 1)."""
        return int(hash_hex[:8], 16) / 0xFFFFFFFF

    def get_metadata(self) -> dict:
        """Return game type metadata for the UI/API."""
        return {
            "game_type": self.game_type,
            "display_name": self.display_name,
            "house_edge_range": list(self.house_edge_range),
        }
