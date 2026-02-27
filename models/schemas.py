"""
Automated Slot Studio - Pydantic Output Models

These enforce structured outputs from every agent, preventing
token waste and ensuring downstream agents get clean, typed data.
Every agent's output is validated against these schemas.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# Enums
# ============================================================

class Volatility(str, Enum):
    LOW = "low"
    MEDIUM_LOW = "medium_low"
    MEDIUM = "medium"
    MEDIUM_HIGH = "medium_high"
    HIGH = "high"
    VERY_HIGH = "very_high"


class SymbolTier(str, Enum):
    HIGH_PAY = "high_pay"
    LOW_PAY = "low_pay"
    WILD = "wild"
    SCATTER = "scatter"
    BONUS = "bonus"
    SPECIAL = "special"


class FeatureType(str, Enum):
    FREE_SPINS = "free_spins"
    MULTIPLIERS = "multipliers"
    EXPANDING_WILDS = "expanding_wilds"
    STICKY_WILDS = "sticky_wilds"
    WALKING_WILDS = "walking_wilds"
    CASCADING_REELS = "cascading_reels"
    PICK_BONUS = "pick_bonus"
    WHEEL_BONUS = "wheel_bonus"
    PROGRESSIVE = "progressive_jackpot"
    MEGAWAYS = "megaways"
    CLUSTER_PAYS = "cluster_pays"
    HOLD_AND_SPIN = "hold_and_spin"
    BUY_BONUS = "bonus_buy"
    MYSTERY_SYMBOLS = "mystery_symbols"
    SPLIT_SYMBOLS = "split_symbols"


class RiskLevel(str, Enum):
    BLOCKER = "blocker"       # Cannot ship without resolving
    HIGH = "high"             # Significant risk, needs attention
    MEDIUM = "medium"         # Manageable with adjustments
    LOW = "low"               # Minor concern
    CLEAR = "clear"           # No issue found


# ============================================================
# User Input Model
# ============================================================

class GameIdeaInput(BaseModel):
    """The user's initial game concept — the pipeline's entry point."""

    theme: str = Field(
        description="Core theme/concept for the slot game",
        examples=["Ancient Egypt - Tomb of the Pharaoh"]
    )
    target_markets: list[str] = Field(
        description="Target jurisdictions for the game",
        examples=[["UK", "Malta", "Ontario"]]
    )
    volatility: Volatility = Field(
        description="Target volatility tier"
    )
    target_rtp: float = Field(
        ge=75.0, le=99.0,
        description="Target Return to Player percentage",
        examples=[96.5]
    )
    grid_rows: int = Field(default=3, ge=1, le=10)
    grid_cols: int = Field(default=5, ge=3, le=8)
    ways_or_lines: str = Field(
        default="243 ways",
        description="Payline structure: e.g. '243 ways', '25 lines', 'megaways', 'cluster'"
    )
    max_win_multiplier: int = Field(
        default=5000, ge=100, le=250000,
        description="Maximum win as multiplier of bet"
    )
    art_style: str = Field(
        default="Cinematic, high-quality",
        description="Visual style direction"
    )
    requested_features: list[FeatureType] = Field(
        default_factory=list,
        description="Desired game features/mechanics"
    )
    competitor_references: list[str] = Field(
        default_factory=list,
        description="Known competitor games for reference",
        examples=[["Book of Dead", "Legacy of Dead"]]
    )
    special_requirements: Optional[str] = Field(
        default=None,
        description="Any additional requirements or constraints"
    )


# ============================================================
# Market Research Models
# ============================================================

class CompetitorGame(BaseModel):
    """Structured data for a single competitor game."""

    name: str
    provider: str
    release_year: Optional[int] = None
    theme_tags: list[str] = Field(default_factory=list)
    rtp: Optional[float] = None
    volatility: Optional[str] = None
    max_win: Optional[str] = None
    grid_config: Optional[str] = None
    features: list[str] = Field(default_factory=list)
    unique_mechanic: Optional[str] = Field(
        default=None,
        description="What makes this game stand out"
    )
    player_sentiment: Optional[str] = Field(
        default=None,
        description="Summary of player reviews: positive/negative themes"
    )
    estimated_popularity: Optional[str] = Field(
        default=None,
        description="Rough popularity tier: top, mid, niche"
    )


class MarketSaturationAnalysis(BaseModel):
    """How crowded is this theme/mechanic space?"""

    theme_keyword: str
    total_games_found: int
    saturation_level: str = Field(
        description="oversaturated / saturated / moderate / underserved / blue_ocean"
    )
    top_providers: list[str]
    dominant_mechanics: list[str]
    underserved_angles: list[str] = Field(
        description="Theme/mechanic combinations that are NOT well covered"
    )
    trending_direction: str = Field(
        description="growing / stable / declining"
    )


class DifferentiationStrategy(BaseModel):
    """Actionable recommendations to stand apart from competitors."""

    primary_differentiator: str = Field(
        description="The single strongest unique angle for this game"
    )
    mechanic_opportunities: list[str] = Field(
        description="Features or mechanics competitors are missing"
    )
    theme_twist: str = Field(
        description="How to make the theme feel fresh vs existing games"
    )
    visual_differentiation: str = Field(
        description="Art direction that stands out from the competitor set"
    )
    player_pain_points: list[str] = Field(
        description="Things players complain about in competitor games that we can fix"
    )


class MarketResearchOutput(BaseModel):
    """Complete output from the Market Research phase."""

    saturation: MarketSaturationAnalysis
    competitors: list[CompetitorGame]
    deep_dive_competitors: list[CompetitorGame] = Field(
        description="Top competitors with detailed analysis"
    )
    differentiation: DifferentiationStrategy
    market_trends: list[str] = Field(
        description="Current trends in the slot market relevant to this game"
    )
    recommended_target_demographic: str


# ============================================================
# Game Design Document Models
# ============================================================

class SymbolDefinition(BaseModel):
    """Definition of a single game symbol."""

    name: str = Field(examples=["Pharaoh's Mask"])
    tier: SymbolTier
    description: str = Field(
        description="Visual description for the art director"
    )
    pay_values: dict[int, float] = Field(
        description="Mapping of symbol_count → payout_multiplier. e.g. {3: 2.0, 4: 5.0, 5: 25.0}"
    )
    special_behavior: Optional[str] = Field(
        default=None,
        description="Any special mechanic tied to this symbol"
    )


class FeatureSpec(BaseModel):
    """Specification for a game feature/bonus."""

    name: str = Field(examples=["Curse of Anubis Free Spins"])
    feature_type: FeatureType
    trigger_description: str = Field(
        description="How the feature is triggered (e.g., '3+ scatters')"
    )
    mechanic_description: str = Field(
        description="Detailed description of how the feature plays"
    )
    expected_rtp_contribution: Optional[float] = Field(
        default=None,
        description="Estimated % of total RTP from this feature"
    )
    max_win_potential: Optional[str] = None
    retrigger_possible: bool = False
    visual_notes: str = Field(
        default="",
        description="Notes for the art director on feature presentation"
    )


class GDDOutput(BaseModel):
    """Complete Game Design Document structured output."""

    # --- Core Identity ---
    game_title: str
    tagline: str
    executive_summary: str = Field(
        description="2-3 paragraph elevator pitch"
    )
    target_audience: str
    unique_selling_points: list[str]

    # --- Grid & Mechanics ---
    grid_config: str = Field(examples=["5x3"])
    payline_structure: str = Field(examples=["243 ways to win"])
    base_game_description: str = Field(
        description="How the base game plays, step by step"
    )
    cascade_mechanic: Optional[str] = None

    # --- Symbols ---
    symbols: list[SymbolDefinition]

    # --- Features ---
    features: list[FeatureSpec]
    feature_flow_description: str = Field(
        description="How features connect and escalate during play"
    )

    # --- Targets ---
    target_rtp: float
    target_volatility: Volatility
    max_win_multiplier: int

    # --- Audio Direction ---
    audio_base_game: str = Field(
        description="Ambient/music direction for base game"
    )
    audio_features: str = Field(
        description="Audio direction for bonus/feature states"
    )
    audio_wins: str = Field(
        description="Win celebration audio scaling description"
    )

    # --- UI/UX ---
    ui_notes: str = Field(
        description="Button layout, bet selector, autoplay, mobile considerations"
    )

    # --- Differentiation ---
    differentiation_strategy: str = Field(
        description="How this game stands apart, pulled from market research"
    )


# ============================================================
# Math Model Output Models
# ============================================================

class ReelStrip(BaseModel):
    """Symbol distribution for a single reel."""

    reel_index: int = Field(description="0-indexed reel position")
    symbols: list[str] = Field(
        description="Ordered list of symbols on the strip"
    )
    total_stops: int


class PaytableEntry(BaseModel):
    """Single paytable row."""

    symbol: str
    count: int
    payout_multiplier: float
    probability: float
    rtp_contribution: float


class SimulationResults(BaseModel):
    """Results from Monte Carlo simulation."""

    total_spins: int
    measured_rtp: float = Field(description="Observed RTP from simulation")
    rtp_confidence_interval: tuple[float, float] = Field(
        description="99% confidence interval for RTP"
    )
    hit_frequency: float = Field(
        description="% of spins that return any win"
    )
    base_game_rtp: float
    feature_rtp_breakdown: dict[str, float] = Field(
        description="RTP contribution per feature"
    )
    volatility_index: float = Field(
        description="Standard deviation of returns per spin"
    )
    max_win_achieved: float = Field(
        description="Highest win multiple observed in simulation"
    )
    max_win_probability: float = Field(
        description="Estimated probability of hitting max win"
    )
    win_distribution: dict[str, float] = Field(
        description="% of spins in each win bucket: 0x, 0-1x, 1-2x, 2-5x, 5-20x, 20-100x, 100x+"
    )
    bankroll_survival_1000_spins: float = Field(
        description="% of players with positive balance after 1000 spins"
    )
    feature_trigger_frequency: dict[str, float] = Field(
        description="Average spins between feature triggers"
    )


class MathModelOutput(BaseModel):
    """Complete math model package."""

    reel_strips: list[ReelStrip]
    paytable: list[PaytableEntry]
    simulation: SimulationResults
    target_rtp: float
    rtp_deviation: float = Field(
        description="Difference between target and measured RTP"
    )
    rtp_within_tolerance: bool = Field(
        description="Whether measured RTP is within ±0.5% of target"
    )
    jurisdiction_rtp_compliance: dict[str, bool] = Field(
        description="Per-jurisdiction RTP compliance check"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Any math model concerns or edge cases"
    )


# ============================================================
# Art Pipeline Models
# ============================================================

class ArtAsset(BaseModel):
    """Metadata for a generated art asset."""

    asset_name: str
    category: str = Field(
        description="mood_board / symbol / background / ui / paytable / logo"
    )
    file_path: str
    prompt_used: str
    dimensions: str
    style_notes: str


class MoodBoardOutput(BaseModel):
    """Mood board generation results — reviewed before full art pipeline."""

    style_direction: str
    color_palette: list[str] = Field(
        description="Hex color codes for primary palette"
    )
    mood_keywords: list[str]
    reference_description: str
    assets: list[ArtAsset]
    recommended_variant: int = Field(
        description="Index of the recommended mood board variant"
    )


class ArtPipelineOutput(BaseModel):
    """Complete art pipeline output."""

    mood_board: MoodBoardOutput
    symbols: list[ArtAsset]
    backgrounds: list[ArtAsset]
    ui_elements: list[ArtAsset]
    paytable_screens: list[ArtAsset]
    logo: Optional[ArtAsset] = None
    total_assets_generated: int
    style_consistency_notes: str


# ============================================================
# Legal & Compliance Models
# ============================================================

class ComplianceFlag(BaseModel):
    """A single compliance finding."""

    jurisdiction: str
    category: str = Field(
        description="rtp / content / responsible_gambling / ip / certification / data_privacy"
    )
    risk_level: RiskLevel
    finding: str = Field(
        description="What was found"
    )
    recommendation: str = Field(
        description="How to resolve or mitigate"
    )
    reference: Optional[str] = Field(
        default=None,
        description="Regulatory section or document reference"
    )


class IPRiskAssessment(BaseModel):
    """Intellectual property risk for the game theme."""

    theme_clear: bool
    potential_conflicts: list[str]
    trademarked_terms_to_avoid: list[str]
    recommendation: str


class ComplianceOutput(BaseModel):
    """Complete legal/compliance review."""

    overall_status: str = Field(
        description="green / yellow / red — overall compliance posture"
    )
    flags: list[ComplianceFlag]
    blocker_count: int = Field(
        description="Number of blocker-level issues"
    )
    ip_assessment: IPRiskAssessment
    jurisdiction_summary: dict[str, str] = Field(
        description="Per-jurisdiction status: green/yellow/red"
    )
    certification_path: list[str] = Field(
        description="Recommended certification bodies and order"
    )
    responsible_gambling_checklist: dict[str, bool] = Field(
        description="Required RG features and their implementation status"
    )


# ============================================================
# Final Package Manifest
# ============================================================

class PackageManifest(BaseModel):
    """Manifest for the complete output package."""

    game_title: str
    generated_at: str
    pipeline_version: str = "1.0.0"
    input_parameters: GameIdeaInput
    files_generated: list[str]
    total_llm_tokens_used: int
    total_images_generated: int
    estimated_cost_usd: float
    compliance_status: str
    rtp_validated: bool
    warnings: list[str] = Field(default_factory=list)
    hitl_approvals: dict[str, bool] = Field(
        default_factory=dict,
        description="Which HITL checkpoints were approved"
    )
