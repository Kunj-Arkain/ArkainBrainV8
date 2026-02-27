"""
ARKAINBRAIN — Mini RMG Math Engine (Phase 7)

Provably fair math models for Real Money Gaming mini-games.
Each game type exposes: compute_house_edge(), simulate(), and generate_config().

Usage:
    from sim_engine.rmg import get_game_engine
    engine = get_game_engine("crash")
    config = engine.generate_config(house_edge=0.03, max_multiplier=1000)
    results = engine.simulate(config, rounds=100_000)
"""

from sim_engine.rmg.crash import CrashEngine
from sim_engine.rmg.plinko import PlinkoEngine
from sim_engine.rmg.mines import MinesEngine
from sim_engine.rmg.dice import DiceEngine
from sim_engine.rmg.wheel import WheelEngine
from sim_engine.rmg.hilo import HiLoEngine
from sim_engine.rmg.chicken import ChickenEngine
from sim_engine.rmg.scratch import ScratchEngine

GAME_ENGINES = {
    "crash": CrashEngine,
    "plinko": PlinkoEngine,
    "mines": MinesEngine,
    "dice": DiceEngine,
    "wheel": WheelEngine,
    "hilo": HiLoEngine,
    "chicken": ChickenEngine,
    "scratch": ScratchEngine,
}

GAME_TYPES = list(GAME_ENGINES.keys())


def get_game_engine(game_type: str):
    """Get the math engine for a game type."""
    cls = GAME_ENGINES.get(game_type.lower())
    if cls is None:
        raise ValueError(f"Unknown game type: {game_type}. Available: {GAME_TYPES}")
    return cls()
