"""
ARKAINBRAIN — Few-Shot Examples Library (Phase 2D)

Gold-standard examples of excellent agent output, injected into agent
prompts to dramatically improve output quality. Each example represents
the quality floor — agents should match or exceed these.

Usage:
  from examples.fewshot import get_gdd_example, get_math_example, get_art_example
  
  # Get relevant example for prompt injection
  gdd_excerpt = get_gdd_example("symbol_hierarchy")
  math_excerpt = get_math_example("simulation_results")
"""


# ============================================================
# GDD Section Examples — Game Designer sees these before writing
# ============================================================

GDD_EXAMPLES = {

    "symbol_hierarchy": '''## 5. Symbol Hierarchy & Paytable

### High-Pay Symbols
| Sym | Name | Visual Description | 5OAK | 4OAK | 3OAK | 2OAK |
|-----|------|-------------------|------|------|------|------|
| H1 | Pharaoh's Mask | Gold death mask with lapis lazuli inlay, glowing amber eyes. 3D-rendered with subsurface scattering on gold surfaces. | 50.0x | 15.0x | 3.0x | 0.5x |
| H2 | Scarab Amulet | Iridescent beetle carved from green malachite, wings spread. Subtle particle effect: gold dust trails. | 30.0x | 10.0x | 2.5x | 0.4x |

### Mid-Pay Symbols
| Sym | Name | Visual Description | 5OAK | 4OAK | 3OAK | 2OAK |
|-----|------|-------------------|------|------|------|------|
| M1 | Eye of Horus | Blue-gold eye symbol with geometric precision. Clean iconographic style. | 15.0x | 5.0x | 1.5x | — |
| M2 | Ankh Cross | Gold ankh with turquoise wrap at intersection. Simple, recognizable silhouette. | 12.0x | 4.0x | 1.2x | — |
| M3 | Canopic Jar | Jackal-headed alabaster jar with hieroglyphic band. Warm amber tones. | 10.0x | 3.5x | 1.0x | — |

### Low-Pay Symbols (Themed Royals)
| Sym | Name | Visual Description | 5OAK | 4OAK | 3OAK |
|-----|------|-------------------|------|------|------|
| L1 | A — Ace of Serpents | Gold "A" entwined with cobra, sandstone texture | 5.0x | 1.5x | 0.5x |
| L2 | K — King of Flames | Gold "K" wreathed in ritual fire, warm orange glow | 4.0x | 1.2x | 0.4x |
| L3 | Q — Queen of Stars | Gold "Q" with constellation pattern, deep blue accent | 3.5x | 1.0x | 0.3x |
| L4 | J — Jack of Sands | Gold "J" with desert wind particle effect | 3.0x | 0.8x | 0.3x |
| L5 | 10 — Ten of Tombs | Gold "10" with carved hieroglyphic texture | 2.5x | 0.7x | 0.2x |
| L6 | 9 — Nine of Shadows | Gold "9" with dark obsidian reflection | 2.0x | 0.5x | 0.2x |

### Special Symbols
| Sym | Name | Behavior | Appears On |
|-----|------|----------|------------|
| W | Golden Scarab WILD | Substitutes for all except SCATTER. Expands to fill reel on any win. 2x multiplier when part of winning combination. | Reels 2, 3, 4 only |
| SC | Book of Curses SCATTER | 3+ anywhere triggers 10 Free Spins. Each scatter adds +2 spins. Pays 2x/5x/50x total bet for 3/4/5. | All reels |

**Total symbols: 12** (2 high + 3 mid + 6 low + 1 WILD + 1 SCATTER = 13 positions on reels)
''',

    "feature_design": '''## 8. Feature Design

### 8.1 Expanding Wild Feature
- **Type:** Symbol mechanic (base game + free spins)
- **Trigger:** Any WILD (W) landing as part of a winning combination
- **Behavior:** WILD expands to cover entire reel (3 positions). Expansion animates top-to-bottom in 400ms with gold particle burst.
- **Multiplier:** Expanded WILDs carry 2x multiplier. Multiple expanded WILDs on same spin multiply (2x × 2x = 4x, etc.)
- **Win evaluation:** Expansion happens BEFORE win evaluation. All paylines re-evaluated after expansion.
- **Frequency:** WILD appears on reels 2/3/4. ~1 in 8 base game spins contain at least one WILD. Expansion triggers ~1 in 12 spins (only when WILD is in a win).
- **RTP contribution:** 8.2% of total 96.0% RTP

### 8.2 Free Spins Feature
- **Type:** Triggered bonus round
- **Trigger:** 3+ SCATTER (SC) symbols anywhere on reels
- **Awards:** 3 SC = 10 spins, 4 SC = 15 spins, 5 SC = 25 spins
- **Retrigger:** 2+ SC during free spins awards +5 spins per scatter. No cap on retriggers.
- **Special modifier:** Before free spins begin, one random M or H symbol is selected as "Expanding Symbol." This symbol behaves like WILD during free spins (expands on any appearance, not just wins).
- **Reel set:** FreeReels.csv — higher concentration of H1, H2, and WILD vs base reels
- **Expected frequency:** Free spins trigger approximately 1 in 180 base game spins
- **Average spins per trigger:** 12.4 (accounting for retriggers)
- **Average win per trigger:** 42x bet
- **RTP contribution:** 18.1% of total 96.0% RTP

### 8.3 Curse Accumulator
- **Type:** Progressive collection mechanic (base game only)
- **Trigger:** Special "Curse Token" symbols (overlay on any winning combination) collected across spins
- **Behavior:** Every 25 curse tokens collected → triggers "Pharaoh's Judgment" bonus:
  - Screen darkens, all symbols except L5/L6 are removed
  - Remaining symbols transform to H1/H2/WILD for 3 guaranteed spins
  - Minimum guaranteed win: 15x bet
- **Collection rate:** ~1 token per 4 spins (visible counter on UI)
- **Persistence:** Counter persists within session only, resets on game close
- **Expected frequency:** Bonus triggers approximately 1 in 100 spins
- **Average win per trigger:** 35x bet
- **RTP contribution:** 9.8% of total 96.0% RTP
''',

    "rtp_breakdown": '''## 10. RTP Budget Breakdown

| Component | RTP Contribution | % of Total | Calculation Basis |
|-----------|-----------------|------------|-------------------|
| Base game (pays without features) | 39.6% | 41.3% | 5-reel, 243-ways evaluation |
| Expanding Wild multiplier | 8.2% | 8.5% | 2x on expansion, frequency 1-in-12 |
| Free Spins (inc. retriggers) | 18.1% | 18.9% | 10-25 spins × enhanced reels × expanding symbol |
| Curse Accumulator bonus | 9.8% | 10.2% | 1-in-100 frequency × 35x avg win |
| Scatter pays (non-trigger) | 1.5% | 1.6% | 2OAK scatter pays (2x × frequency) |
| Dead spin recovery (near-miss) | 2.3% | 2.4% | Low-pay 2OAK and 3OAK combinations |
| Progressive jackpot seed | 0.35% | 0.4% | Seed value contribution rate |
| **TOTAL** | **96.05%** | **100%** | Validated via 10M-spin Monte Carlo |

**Verification:** `calculate_rtp_budget` tool confirms total = 96.05% (within ±0.05% of 96.0% target). ✓
''',
}


# ============================================================
# Math Output Examples — Mathematician sees these structures
# ============================================================

MATH_EXAMPLES = {

    "simulation_results": '''{
  "game_name": "Pharaoh's Curse",
  "total_spins": 10000000,
  "total_wagered": 10000000.0,
  "total_won": 9604832.5,
  "measured_rtp": 96.05,
  "target_rtp": 96.0,
  "deviation_from_target": 0.05,
  "hit_frequency_pct": 28.4,
  "hit_frequency_1_in": 3.52,
  "volatility_index": 14.7,
  "volatility_class": "high",
  "max_win_achieved": 4847,
  "max_win_theoretical": 5000,
  "max_win_path": "5x H1 with 2x expanded WILD during free spins + expanding symbol H1 = 50 × 2 × 5 reels × progressive",
  "std_deviation_per_spin": 4.23,
  "confidence_interval_95": [95.97, 96.13],
  "rtp_breakdown": {
    "base_game": 39.6,
    "expanding_wilds": 8.2,
    "free_spins": 18.1,
    "curse_accumulator": 9.8,
    "scatter_pays": 1.5,
    "dead_spin_recovery": 2.3,
    "progressive_seed": 0.35
  },
  "feature_stats": {
    "free_spins": {
      "trigger_frequency_1_in": 181,
      "avg_spins_per_trigger": 12.4,
      "avg_win_per_trigger_x_bet": 42.3,
      "max_win_in_feature": 3200,
      "retrigger_rate_pct": 8.2
    },
    "curse_accumulator": {
      "trigger_frequency_1_in": 102,
      "avg_win_per_trigger_x_bet": 34.8,
      "max_win_in_feature": 890
    },
    "expanding_wilds": {
      "frequency_1_in": 12,
      "avg_multiplier_when_active": 2.1
    }
  },
  "win_distribution": {
    "zero_win_pct": 71.6,
    "1x_to_5x_pct": 22.1,
    "5x_to_20x_pct": 4.8,
    "20x_to_100x_pct": 1.2,
    "100x_to_500x_pct": 0.25,
    "500x_plus_pct": 0.05
  },
  "session_simulation": {
    "spins_per_session": 200,
    "sessions_simulated": 50000,
    "winning_session_pct": 38.2,
    "avg_session_return_pct": 96.1,
    "median_session_return_pct": 82.4,
    "session_std_deviation": 2.85
  }
}''',

    "paytable_csv": '''Symbol,5OAK,4OAK,3OAK,2OAK,Type
Pharaoh Mask,50.0,15.0,3.0,0.5,high_pay
Scarab Amulet,30.0,10.0,2.5,0.4,high_pay
Eye of Horus,15.0,5.0,1.5,0,mid_pay
Ankh Cross,12.0,4.0,1.2,0,mid_pay
Canopic Jar,10.0,3.5,1.0,0,mid_pay
A,5.0,1.5,0.5,0,low_pay
K,4.0,1.2,0.4,0,low_pay
Q,3.5,1.0,0.3,0,low_pay
J,3.0,0.8,0.3,0,low_pay
10,2.5,0.7,0.2,0,low_pay
9,2.0,0.5,0.2,0,low_pay
WILD,0,0,0,0,special
SCATTER,50.0,5.0,2.0,0,special''',
}


# ============================================================
# Art Brief Example — Art Director sees this format
# ============================================================

ART_EXAMPLES = {

    "mood_board_brief": '''## Mood Board Brief: Pharaoh's Curse

### Color Palette
- **Primary:** Deep gold (#C9A94E), Aged bronze (#8B6914)
- **Secondary:** Lapis lazuli blue (#1F4690), Obsidian black (#0A0A0F)
- **Accent:** Amber glow (#FFB830), Blood ruby (#8B0000)
- **Background gradient:** #0A0A12 → #1A1A2E (deep twilight)

### Atmosphere
Dark, reverent, archaeological. The feeling of stepping into a sealed tomb
for the first time in 3,000 years. Torchlight flickers against gold surfaces.
Dust motes float in beams of light. Ancient but not decayed — preserved.

### Symbol Art Direction
- **High-pay:** Photorealistic 3D renders with subsurface scattering on metals.
  Depth-of-field blur on edges. Each symbol occupies a "floating artifact" space.
- **Mid-pay:** Clean iconographic style with gold outlines on dark backgrounds.
  Slightly flat but with subtle inner glow. Inspired by Art Deco Egyptian Revival.
- **Low-pay:** Themed royals carved from stone with gold inlay. Each letter has
  a unique hieroglyphic accent. Weathered texture but still sharp at 64px.

### Technical Constraints
- All symbols must be distinguishable at 64×64px (mobile minimum)
- Background must not compete with symbol readability
- Win celebration effects use the gold/amber palette only
- Maintain WCAG AA contrast ratio (4.5:1) for all text elements
''',
}


# ============================================================
# Accessor Functions — used by pipeline to inject into prompts
# ============================================================

def get_gdd_example(section_key: str) -> str:
    """Get a gold-standard GDD section example for prompt injection."""
    return GDD_EXAMPLES.get(section_key, "")


def get_math_example(example_key: str) -> str:
    """Get a gold-standard math output example for prompt injection."""
    return MATH_EXAMPLES.get(example_key, "")


def get_art_example(example_key: str) -> str:
    """Get a gold-standard art brief example for prompt injection."""
    return ART_EXAMPLES.get(example_key, "")


def get_all_gdd_examples() -> str:
    """Get all GDD examples concatenated for full injection."""
    return "\n\n".join(GDD_EXAMPLES.values())


def get_designer_examples() -> str:
    """Get combined examples relevant to the Game Designer agent."""
    return (
        "═══ QUALITY REFERENCE — Match or exceed this quality level ═══\n\n"
        + GDD_EXAMPLES["symbol_hierarchy"]
        + "\n\n"
        + GDD_EXAMPLES["feature_design"]
        + "\n\n"
        + GDD_EXAMPLES["rtp_breakdown"]
    )


def get_mathematician_examples() -> str:
    """Get combined examples relevant to the Mathematician agent."""
    return (
        "═══ OUTPUT FORMAT REFERENCE — Your files must match this structure ═══\n\n"
        "### simulation_results.json structure:\n"
        "```json\n"
        + MATH_EXAMPLES["simulation_results"]
        + "\n```\n\n"
        "### paytable.csv structure:\n"
        "```csv\n"
        + MATH_EXAMPLES["paytable_csv"]
        + "\n```"
    )


def get_art_director_examples() -> str:
    """Get combined examples relevant to the Art Director agent."""
    return (
        "═══ MOOD BOARD QUALITY REFERENCE ═══\n\n"
        + ART_EXAMPLES["mood_board_brief"]
    )
