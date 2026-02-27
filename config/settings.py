"""
Automated Slot Studio - Configuration & LLM Routing

PHASE 5A: TIER 3 GPT ACCESS + INFRASTRUCTURE UPGRADE
=====================================================
- Tier 3 rate limits: GPT-5 = 800K+ TPM, GPT-5-mini = 2M+ TPM
- All 6 agents now on HEAVY (GPT-5) — Tier 3 headroom allows it
- Token budgets raised 2x — Tier 3 has no practical per-minute ceiling
- 6 concurrent pipeline jobs (vs 3 before) — Redis queue manages burst
- Cost per pipeline run: ~$2.50-5.00 (GPT-5 input is $1.25/M — cheap)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))


# ============================================================
# HYBRID LLM ROUTING
#
# CrewAI uses litellm → model strings MUST be litellm-compatible:
#   "openai/gpt-5"             → GPT-5 (reasoning, $1.25/$10 per 1M)
#   "openai/gpt-5-mini"        → GPT-5-mini (fast, $0.25/$1 per 1M)
#   "openai/gpt-5.2"           → GPT-5.2 (premium reasoning, $1.75/$14)
#
# TIER 3 RATE LIMITS (ChatGPT Pro / API Tier 3):
#   GPT-5:      800,000+ TPM  →  enough for 6 concurrent pipelines
#   GPT-5-mini: 2,000,000+ TPM → unlimited light tasks
#   Images:     DALL-E 3, 50+ img/min
#
# With Tier 3, ALL agents can run on HEAVY without hitting limits.
# This dramatically improves output quality across the board.
# ============================================================

class LLMConfig:

    # --- Model Selection ---
    # Tier 3 lets us put everything on GPT-5 without rate limit risk.
    # Override via env: LLM_HEAVY=openai/gpt-5.2 for premium reasoning
    HEAVY = os.getenv("LLM_HEAVY", "openai/gpt-5")
    LIGHT = os.getenv("LLM_LIGHT", "openai/gpt-5-mini")

    # --- Image Generation ---
    IMAGE_MODEL = "dall-e-3"

    # --- Per-Agent Routing (Tier 3: ALL on HEAVY) ---
    # Pre-Tier 3: lead_producer + art_director were on LIGHT to stay under 300K TPM.
    # Tier 3 at 800K+ TPM: all agents on HEAVY for maximum quality.
    # Art director benefits most — GPT-5 produces far richer mood boards and style guides.
    AGENTS = {
        "lead_producer":      {"model": HEAVY, "temperature": 0.3, "max_tokens": 32768},
        "market_analyst":     {"model": HEAVY, "temperature": 0.4, "max_tokens": 32768},
        "game_designer":      {"model": HEAVY, "temperature": 0.6, "max_tokens": 32768},
        "mathematician":      {"model": HEAVY, "temperature": 0.1, "max_tokens": 32768},
        "art_director":       {"model": HEAVY, "temperature": 0.7, "max_tokens": 32768},
        "compliance_officer": {"model": HEAVY, "temperature": 0.1, "max_tokens": 32768},
    }

    # --- Token Budgets (soft limit per agent per run) ---
    # Tier 3: doubled from Phase 2. At 800K TPM, even 6 concurrent runs
    # with all agents on HEAVY use ~300K TPM average — well within limits.
    TOKEN_BUDGETS = {
        "lead_producer": 300_000,
        "market_analyst": 1_000_000,
        "game_designer": 1_000_000,
        "mathematician": 1_000_000,
        "art_director": 800_000,
        "compliance_officer": 500_000,
    }

    # --- Cost Rates (USD per 1M tokens) — GPT-5 family pricing ---
    COST_INPUT = {
        "openai/gpt-5": 1.25, "openai/gpt-5-mini": 0.25,
        "openai/gpt-5.1": 1.25, "openai/gpt-5.2": 1.75,
        "openai/gpt-4o": 2.50, "openai/gpt-4o-mini": 0.15,
    }
    COST_OUTPUT = {
        "openai/gpt-5": 10.00, "openai/gpt-5-mini": 1.00,
        "openai/gpt-5.1": 10.00, "openai/gpt-5.2": 14.00,
        "openai/gpt-4o": 10.00, "openai/gpt-4o-mini": 0.60,
    }
    COST_IMAGE = {"1024x1024": 0.04, "1792x1024": 0.08}
    COST_AUDIO_SFX = 0.01  # Estimated per ElevenLabs sound effect generation

    @classmethod
    def get_llm(cls, agent_key: str) -> str:
        """Return the litellm model string for CrewAI's `llm` param."""
        return cls.AGENTS.get(agent_key, {}).get("model", cls.LIGHT)

    @classmethod
    def get_config(cls, agent_key: str) -> dict:
        """Return full config dict for an agent."""
        return cls.AGENTS.get(agent_key, {"model": cls.LIGHT, "temperature": 0.5, "max_tokens": 16384})


# ============================================================
# Cost Tracker — one per pipeline run
# ============================================================

class CostTracker:
    def __init__(self):
        self.usage = {}
        self.images = 0
        self.image_cost = 0.0

    def log(self, agent_key: str, input_tokens: int = 0, output_tokens: int = 0):
        if agent_key not in self.usage:
            self.usage[agent_key] = {"input": 0, "output": 0, "calls": 0}
        self.usage[agent_key]["input"] += input_tokens
        self.usage[agent_key]["output"] += output_tokens
        self.usage[agent_key]["calls"] += 1
        total = self.usage[agent_key]["input"] + self.usage[agent_key]["output"]
        budget = LLMConfig.TOKEN_BUDGETS.get(agent_key, float("inf"))
        if total > budget:
            print(f"⚠️  {agent_key} token budget exceeded: {total:,}/{budget:,}")

    def log_image(self, size="1024x1024"):
        self.images += 1
        self.image_cost += LLMConfig.COST_IMAGE.get(size, 0.04)

    def total_tokens(self) -> int:
        return sum(v["input"] + v["output"] for v in self.usage.values())

    def total_cost(self) -> float:
        cost = 0.0
        for key, data in self.usage.items():
            model = LLMConfig.get_llm(key)
            cost += (data["input"] / 1e6) * LLMConfig.COST_INPUT.get(model, 5.0)
            cost += (data["output"] / 1e6) * LLMConfig.COST_OUTPUT.get(model, 15.0)
        return round(cost + self.image_cost, 4)

    def summary(self) -> dict:
        return {
            "per_agent": {
                k: {"model": LLMConfig.get_llm(k), **v, "budget": LLMConfig.TOKEN_BUDGETS.get(k)}
                for k, v in self.usage.items()
            },
            "total_tokens": self.total_tokens(),
            "total_images": self.images,
            "estimated_cost_usd": self.total_cost(),
        }


# ============================================================
# Pipeline Configuration
# ============================================================

class PipelineConfig:
    HITL_ENABLED = os.getenv("HITL_ENABLED", "true").lower() == "true"
    HITL_CHECKPOINTS = {"post_research": True, "post_design_math": True, "post_art_review": True}
    SIMULATION_SPINS = int(os.getenv("SIMULATION_SPINS", "1000000"))
    COMPETITOR_BROAD_SWEEP_LIMIT = 30
    COMPETITOR_DEEP_DIVE_LIMIT = 10
    MOOD_BOARD_VARIANTS = 4
    IMAGE_SIZES = {"mood_board": "1024x1024", "symbol": "1024x1024", "background": "1792x1024"}

    # Phase 5A: Tier 3 concurrency settings
    MAX_CONCURRENT_PIPELINES = int(os.getenv("MAX_CONCURRENT_JOBS", "6"))
    # With Tier 3 at 800K TPM, 6 concurrent pipelines each averaging ~50K TPM
    # stays well under limits. Redis queue handles burst beyond this.


# ============================================================
# RAG Configuration
# ============================================================

class RAGConfig:
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
    COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "slot_regulations")
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIM = 1536
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200
    TOP_K = 10
    DOCUMENT_SOURCES = {
        "gli_standards": "data/regulations/gli/",
        "ukgc_rules": "data/regulations/ukgc/",
        "mga_rules": "data/regulations/mga/",
        "ontario_rules": "data/regulations/ontario/",
        "company_games": "data/internal/past_games/",
    }


# ============================================================
# Jurisdiction Database (Static — RAG fallback)
#
# INTERNATIONAL markets + US STATE LOOPHOLE ANALYSIS
# Each US state entry includes:
#   - gambling_definition: How the state defines illegal gambling
#   - legal_avenues: Known legal pathways for game placement
#   - loophole_strategy: Specific game design tweaks to exploit
#   - risk_level: LOW / MEDIUM / HIGH / EXTREME
#   - key_statutes: Primary laws to watch
#   - enforcement_notes: How aggressively the state enforces
# ============================================================

JURISDICTION_REQUIREMENTS = {

    # ========== INTERNATIONAL ==========

    "UK": {
        "regulator": "UKGC", "min_rtp": 80.0, "max_win_cap": None,
        "certifiers": ["GLI", "BMM", "eCOGRA", "NMi"],
        "content_restrictions": [
            "No content appealing primarily to children",
            "Responsible gambling messaging required",
            "Reality check at 60-minute intervals",
            "Session time and loss limits mandatory",
        ],
        "data_privacy": "GDPR",
    },
    "Malta": {
        "regulator": "MGA", "min_rtp": 85.0, "max_win_cap": None,
        "certifiers": ["GLI", "BMM", "iTech Labs"],
        "content_restrictions": ["No offensive or discriminatory content", "RNG certification required"],
        "data_privacy": "GDPR",
    },
    "Ontario": {
        "regulator": "AGCO/iGO", "min_rtp": 85.0, "max_win_cap": None,
        "certifiers": ["GLI", "BMM", "iTech Labs", "Gaming Associates"],
        "content_restrictions": [
            "Responsible gambling tools mandatory",
            "Self-exclusion integration required",
            "No inducements to problem gambling",
        ],
        "data_privacy": "PIPEDA",
    },
    "New Jersey": {
        "regulator": "NJ DGE", "min_rtp": 83.0, "max_win_cap": None,
        "certifiers": ["GLI", "BMM"],
        "content_restrictions": [
            "Geolocation verification required",
            "Age verification mandatory",
            "Responsible gambling features required",
        ],
        "data_privacy": "State privacy laws",
    },
    "Curacao": {
        "regulator": "Curacao eGaming", "min_rtp": 75.0, "max_win_cap": None,
        "certifiers": ["GLI", "iTech Labs"],
        "content_restrictions": ["Basic responsible gambling messaging"],
        "data_privacy": "Minimal requirements",
    },

    # ========== US STATES ==========
    # NO STATIC DATA — All US state jurisdiction data lives in Qdrant.
    # Run the State Recon Pipeline to research any state:
    #   python -m flows.state_recon --state "North Carolina"
    # Results are auto-ingested into Qdrant and stay current.
}


# ============================================================
# DEPRECATED — Static loophole data removed.
# All US jurisdiction intelligence now lives in Qdrant,
# populated and refreshed by the State Recon Pipeline.
# Query via: RegulatoryRAGTool → search_regulations
# Research via: StateReconFlow → python -m flows.state_recon --state "X"
# ============================================================
