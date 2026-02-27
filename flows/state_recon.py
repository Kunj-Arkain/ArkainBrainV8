"""
Automated Slot Studio — State Recon Flow

Point this at ANY US state and it autonomously:
1. RESEARCHES current gambling statutes, definitions, exemptions, case law, AG opinions
2. ANALYZES legal definitions to map what triggers "gambling" vs what's exempt
3. ARCHITECTS specific game mechanics that fit inside the legal safe harbor
4. GENERATES a legal defense brief mapping each mechanic to its statutory basis

Usage:
    from flows.state_recon import StateReconFlow
    flow = StateReconFlow()
    result = flow.kickoff("North Carolina")

    # Or from CLI:
    python -m flows.state_recon --state "North Carolina"
    python -m flows.state_recon --state "North Carolina" --auto  # skip HITL
"""

import json
import os
VERBOSE = os.getenv("CREWAI_VERBOSE", "false").lower() == "true"
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from crewai import Agent, Crew, Process, Task
from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from config.settings import LLMConfig
from tools.legal_research_tool import LegalResearchTool, StatuteFetchTool
from tools.custom_tools import RegulatoryRAGTool, FileWriterTool
from tools.advanced_research import WebFetchTool, DeepResearchTool

console = Console()


# ============================================================
# Recon State (tracks pipeline data between stages)
# ============================================================

class ReconState(BaseModel):
    """Pipeline state for the State Recon Flow."""
    # Input
    job_id: str = ""  # Web HITL needs this
    target_state: str = ""
    game_type_hint: Optional[str] = None  # e.g. "slot-style", "poker", "skill game"

    # Stage 1: Legal Research
    raw_research: Optional[dict] = None
    statutes_fetched: list[dict] = Field(default_factory=list)

    # Stage 2: Legal Analysis
    legal_profile: Optional[dict] = None
    # Expected structure:
    # {
    #   "gambling_definition": {...},
    #   "exemptions": [{name, requirements, statutory_basis, risk}],
    #   "court_rulings": [{case, holding, relevance}],
    #   "enforcement_posture": "aggressive|moderate|lax",
    #   "pending_legislation": [...],
    #   "risk_tier": "LOW|LOW-MEDIUM|MEDIUM|HIGH|HOSTILE",
    #   "best_legal_pathway": "skill_game|amusement_device|sweepstakes|regulated|none",
    # }

    # Stage 3: Compliant Game Architecture
    game_architecture: Optional[dict] = None
    # Expected structure:
    # {
    #   "legal_pathway": "...",
    #   "core_mechanic": {...},
    #   "skill_elements": [{mechanic, legal_justification, implementation}],
    #   "prize_structure": {...},
    #   "prohibited_features": [...],
    #   "hardware_requirements": {...},
    #   "operational_requirements": {...},
    # }

    # Stage 4: Defense Brief
    defense_brief: Optional[dict] = None
    # Expected structure:
    # {
    #   "legal_theory": "...",
    #   "element_by_element_defense": [{element, statutory_basis, argument, counter_argument, rebuttal}],
    #   "supporting_case_law": [...],
    #   "risk_assessment": {...},
    #   "recommended_precautions": [...],
    # }

    # Meta
    output_dir: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    errors: list[str] = Field(default_factory=list)
    hitl_approvals: dict[str, bool] = Field(default_factory=dict)
    auto_mode: bool = False


# ============================================================
# Agent Factory
# ============================================================

def create_recon_agents() -> dict[str, Agent]:
    """Build the 4 recon agents with appropriate tools.
    UPGRADED: Deep research + web fetch for maximum legal research depth."""

    legal_search = LegalResearchTool()
    statute_fetch = StatuteFetchTool()
    reg_rag = RegulatoryRAGTool()
    file_writer = FileWriterTool()
    web_fetch = WebFetchTool()
    deep_research = DeepResearchTool()

    agents = {}

    # ---- 1. Legal Recon Agent (UPGRADED: deep research + web fetch) ----
    agents["legal_recon"] = Agent(
        role="State Gaming Law Researcher",
        goal=(
            "Conduct exhaustive legal research on a target state's gambling laws. "
            "USE deep_research AS YOUR PRIMARY TOOL — it reads FULL web pages, not snippets. "
            "Find and extract: (1) the EXACT statutory definition of 'gambling', 'lottery', "
            "'game of chance'; (2) ALL exemptions — skill games, amusement devices, sweepstakes, "
            "social gambling, fraternal/charitable; (3) relevant court rulings with case names; "
            "(4) AG opinions; (5) enforcement actions and posture; (6) pending legislation. "
            "ALWAYS use fetch_web_page to read the FULL TEXT of any statute URL you find. "
            "200-char snippets are NOT enough for legal research."
        ),
        backstory=(
            "You are a legal researcher specializing in US state gambling law with 20 years "
            "of experience at a top gaming law firm. You know that gambling law is entirely "
            "about DEFINITIONS — the exact words in the statute determine what is and isn't "
            "legal. You ALWAYS read the full text of statutes, never rely on summaries. "
            "You use deep_research for comprehensive multi-angle searches and fetch_web_page "
            "to read complete legal documents. You cite specific statute numbers, case names, "
            "and AG opinion dates."
        ),
        llm=LLMConfig.get_llm("compliance_officer"),
        max_iter=20,  # More iterations for deep multi-pass research
        verbose=VERBOSE,
        tools=[deep_research, web_fetch, legal_search, statute_fetch, reg_rag],
    )

    # ---- 2. Definition Analyzer Agent (UPGRADED: web fetch for full statute text) ----
    agents["definition_analyzer"] = Agent(
        role="Legal Definition Analyst & Loophole Mapper",
        goal=(
            "Analyze the raw legal research and build a structured legal profile. "
            "Use fetch_web_page to verify the EXACT statutory language — one word can change everything. "
            "For each statutory definition, identify the ELEMENTS that must ALL be present "
            "for an activity to constitute 'gambling'. Then identify which elements can be "
            "NEGATED or AVOIDED by game design choices."
        ),
        backstory=(
            "You are a gaming compliance attorney who has successfully argued the legality "
            "of skill-based gaming devices in 15 states. You think in terms of LEGAL ELEMENTS — "
            "every gambling definition has 3-4 required elements (typically consideration + "
            "chance + prize), and if you can negate ANY ONE element, the activity is NOT gambling "
            "by definition."
        ),
        llm=LLMConfig.get_llm("compliance_officer"),
        max_iter=8,
        verbose=VERBOSE,
        tools=[web_fetch, reg_rag, file_writer],
    )

    # ---- 3. Compliant Game Architect Agent ----
    agents["game_architect"] = Agent(
        role="Compliant Game Mechanic Architect",
        goal=(
            "Design specific, implementable game mechanics that satisfy ALL legal requirements "
            "identified by the Definition Analyzer. For each legal constraint, produce a concrete "
            "game design solution. The output must be specific enough that a developer could "
            "implement it — not just 'add skill element' but exactly WHAT skill element, HOW it "
            "affects the outcome, and WHAT the player decision flow looks like. Also specify "
            "prohibited features that would break the legal pathway."
        ),
        backstory=(
            "You are a veteran slot game designer who specializes in compliance-first design. "
            "You have designed games for Pace-O-Matic, Miele Manufacturing, Prominent Games, "
            "and other skill-game hardware providers operating in gray-area US markets. You know "
            "exactly how to add a 'skill gate' that satisfies regulators without destroying the "
            "gameplay experience. You understand the spectrum from pure skill (arcade) to pure "
            "chance (slot), and you know how to position a game at exactly the right point on "
            "that spectrum for each jurisdiction. You design games that PLAYERS enjoy and that "
            "LAWYERS can defend."
        ),
        llm=LLMConfig.get_llm("game_designer"),  # TIER 1
        max_iter=5,
        verbose=VERBOSE,
        tools=[file_writer],
    )

    # ---- 4. Defense Brief Agent (UPGRADED: deep research for case law) ----
    agents["defense_counsel"] = Agent(
        role="Gaming Defense Attorney & Brief Writer",
        goal=(
            "Produce a comprehensive legal defense brief that could be presented to a court. "
            "Use deep_research to find SUPPORTING CASE LAW — actual cases where courts ruled "
            "in favor of similar games. Use fetch_web_page to read full court opinions. "
            "For EACH game mechanic, map it to its specific statutory basis. Anticipate the "
            "prosecution's arguments and prepare rebuttals. Include an honest risk assessment."
        ),
        backstory=(
            "You are a gaming defense litigator who has won cases in state courts across "
            "the US defending skill-based gaming devices. You've argued before hostile judges, "
            "aggressive DAs, and skeptical regulators. You ALWAYS verify your case law citations "
            "by reading the full opinion text via web fetch — citing a case incorrectly is "
            "malpractice. You write briefs that are honest about risks."
        ),
        llm=LLMConfig.get_llm("compliance_officer"),
        max_iter=10,
        verbose=VERBOSE,
        tools=[deep_research, web_fetch, reg_rag, file_writer],
    )

    return agents


# ============================================================
# HITL Checkpoint
# ============================================================

def recon_hitl(name: str, summary: str, state: ReconState) -> bool:
    """Human-in-the-loop checkpoint. Skipped in auto mode."""
    if state.auto_mode:
        console.print(f"[dim]⏭ Auto-approved: {name}[/dim]")
        state.hitl_approvals[name] = True
        return True

    console.print(Panel(summary, title=f"🔍 RECON CHECKPOINT: {name}", border_style="cyan"))
    approved = Confirm.ask("[bold cyan]Approve and proceed?[/bold cyan]", default=True)
    state.hitl_approvals[name] = approved

    if not approved:
        fb = Prompt.ask("[cyan]Feedback (or 'abort' to stop)[/cyan]")
        if fb.lower() == "abort":
            state.errors.append(f"Pipeline aborted at {name}")
            return False
        state.errors.append(f"HITL revision at {name}: {fb}")

    return approved


# ============================================================
# State Recon Flow
# ============================================================

class StateReconFlow(Flow[ReconState]):
    """
    Autonomous pipeline: point at any US state → get a legally defensible
    game design with full statutory mapping.

    Stages:
    1. Legal Recon (web search + statute fetching)
    2. Definition Analysis (element mapping + loophole identification)
    3. Compliant Game Architecture (mechanic design within legal constraints)
    4. Defense Brief Generation (statutory mapping + risk assessment)
    """

    def __init__(self, auto_mode: bool = False):
        super().__init__()
        self.agents = create_recon_agents()
        self.auto_mode = auto_mode

    # ────────────────────────────────────────
    # STAGE 0: Initialize
    # ────────────────────────────────────────

    @start()
    def initialize(self):
        """Set up output directory and validate input."""
        state = self.state
        state.auto_mode = self.auto_mode
        state.started_at = datetime.now().isoformat()

        slug = state.target_state.lower().replace(" ", "_")
        state.output_dir = str(Path("output") / "recon" / slug)
        Path(state.output_dir).mkdir(parents=True, exist_ok=True)

        console.print(Panel(
            f"[bold green]STATE RECON: {state.target_state}[/bold green]\n"
            f"Output: {state.output_dir}\n"
            f"Mode: {'AUTO' if state.auto_mode else 'HITL'}",
            title="🔍 Arkain State Recon Pipeline",
            border_style="green",
        ))
        return state

    # ────────────────────────────────────────
    # STAGE 1: Legal Research
    # ────────────────────────────────────────

    @listen(initialize)
    def legal_research(self):
        """Multi-pass web search for gambling laws, definitions, exemptions, case law."""
        state = self.state
        console.print("\n[bold blue]═══ STAGE 1: LEGAL RESEARCH ═══[/bold blue]\n")

        task = Task(
            description=f"""
Conduct comprehensive legal research on {state.target_state}'s gambling laws.

Execute the following research passes using the legal_research tool:

1. STATUTES: Search for the state's core gambling statutes and penal code sections.
   Use search_pass='statutes' with state='{state.target_state}'

2. DEFINITIONS: Search for how the state legally defines 'gambling', 'game of chance',
   'consideration', 'prize', and 'skill game'.
   Use search_pass='definitions'

3. EXEMPTIONS: Search for ALL exemptions — skill games, amusement devices, sweepstakes,
   social gambling, fraternal/charitable orgs, promotional contests.
   Use search_pass='exemptions'

4. CASE LAW: Search for court rulings on skill vs chance, device classifications.
   Use search_pass='case_law'

5. ENFORCEMENT: Search for recent enforcement actions, DA posture, seizures.
   Use search_pass='enforcement'

6. LEGISLATION: Search for pending bills that might change the landscape.
   Use search_pass='legislation'

After searching, use the fetch_statute tool to retrieve the FULL TEXT of the most
important statutes and court opinions you find (at least 2-3 key sources).

Also check the search_regulations tool for any existing data on {state.target_state}.

OUTPUT FORMAT (JSON):
{{
    "state": "{state.target_state}",
    "primary_gambling_statute": {{
        "citation": "...",
        "url": "...",
        "key_text": "..."
    }},
    "additional_statutes": [...],
    "definitions_found": {{
        "gambling": "exact statutory text...",
        "lottery": "...",
        "game_of_chance": "...",
        "consideration": "...",
        "prize": "...",
        "skill_game": "... (if defined)"
    }},
    "exemptions_found": [
        {{
            "name": "...",
            "statutory_basis": "...",
            "requirements": "...",
            "key_text": "..."
        }}
    ],
    "court_rulings": [
        {{
            "case_name": "...",
            "year": "...",
            "holding": "...",
            "relevance": "..."
        }}
    ],
    "ag_opinions": [...],
    "enforcement_posture": "aggressive|moderate|lax|unknown",
    "enforcement_examples": [...],
    "pending_legislation": [...],
    "key_sources": [
        {{
            "url": "...",
            "title": "...",
            "reliability": "OFFICIAL|LEGAL_DB|INDUSTRY|GENERAL"
        }}
    ]
}}
""",
            expected_output="Comprehensive JSON legal research profile",
            agent=self.agents["legal_recon"],
        )

        crew = Crew(
            agents=[self.agents["legal_recon"]],
            tasks=[task],
            process=Process.sequential,
            verbose=VERBOSE,
        )

        result = crew.kickoff()
        raw = result.raw if hasattr(result, "raw") else str(result)

        # Try to parse as JSON
        try:
            state.raw_research = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from mixed output
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                try:
                    state.raw_research = json.loads(json_match.group())
                except json.JSONDecodeError:
                    state.raw_research = {"raw_text": raw}
            else:
                state.raw_research = {"raw_text": raw}

        # Save raw research
        research_path = Path(state.output_dir) / "01_raw_research.json"
        research_path.write_text(json.dumps(state.raw_research, indent=2, default=str), encoding="utf-8")
        console.print(f"[green]✓ Research saved: {research_path}[/green]")

        # HITL checkpoint
        summary = f"Research for {state.target_state}:\n"
        if isinstance(state.raw_research, dict):
            defs = state.raw_research.get("definitions_found", {})
            exemptions = state.raw_research.get("exemptions_found", [])
            rulings = state.raw_research.get("court_rulings", [])
            summary += f"• Definitions found: {len(defs)}\n"
            summary += f"• Exemptions found: {len(exemptions)}\n"
            summary += f"• Court rulings found: {len(rulings)}\n"
            summary += f"• Enforcement posture: {state.raw_research.get('enforcement_posture', 'unknown')}\n"

        recon_hitl("Legal Research", summary, state)
        return state

    # ────────────────────────────────────────
    # STAGE 2: Definition Analysis
    # ────────────────────────────────────────

    @listen(legal_research)
    def analyze_definitions(self):
        """Map legal definitions to game design constraints and identify pathways."""
        state = self.state

        if state.errors and "aborted" in state.errors[-1].lower():
            return state

        console.print("\n[bold yellow]═══ STAGE 2: DEFINITION ANALYSIS ═══[/bold yellow]\n")

        research_json = json.dumps(state.raw_research, indent=2, default=str)

        task = Task(
            description=f"""
Analyze the following legal research for {state.target_state} and build a structured
legal profile with actionable game design constraints.

RAW RESEARCH:
{research_json[:12000]}

YOUR ANALYSIS MUST INCLUDE:

1. GAMBLING DEFINITION ELEMENTS: Break down the state's definition into its required
   elements. Most states require ALL of: (a) consideration, (b) chance, (c) prize.
   Identify which TEST the state uses for chance vs skill:
   - PREDOMINANCE TEST: Is the game PREDOMINANTLY chance? (most common, most favorable)
   - ANY CHANCE TEST: Does ANY element of chance exist? (strictest)
   - MATERIAL ELEMENT TEST: Is chance a MATERIAL element? (moderate)
   - GAMBLING INSTINCT TEST: Does it appeal to the gambling instinct? (vague, risky)

2. ELEMENT NEGATION MAP: For each required element, identify how game design can
   NEGATE it:
   - Chance → Add skill elements (what kind? how much?)
   - Consideration → Free play option (sweepstakes model)
   - Prize → Prize restrictions (what's allowed?)

3. EXEMPTION ANALYSIS: For each exemption found, detail:
   - Exact requirements to qualify
   - Game design constraints imposed
   - Prize limits
   - Location/licensing requirements
   - Strength of the exemption (tested in court? well-established? untested?)

4. RISK CLASSIFICATION:
   - DEPLOY_NOW: Clear legal pathway, well-tested, low prosecution risk
   - STRUCTURED_DEPLOY: Legal but requires specific game design, moderate risk
   - GRAY_AREA: Untested loophole, could go either way
   - HIGH_RISK: Hostile enforcement, narrow exemptions
   - DO_NOT_ENTER: No viable pathway, active prosecution

5. BEST LEGAL PATHWAY: Recommend the strongest legal theory for operating a
   slot-style game in this state. Rank all viable pathways.

OUTPUT FORMAT (JSON):
{{
    "state": "{state.target_state}",
    "gambling_definition": {{
        "citation": "...",
        "elements": ["consideration", "chance", "prize"],
        "chance_test": "predominance|any_chance|material_element|gambling_instinct",
        "chance_test_source": "statute|case_law|ag_opinion",
        "key_language": "exact statutory text..."
    }},
    "element_negation_map": {{
        "chance": {{
            "can_negate": true/false,
            "strategy": "...",
            "minimum_skill_required": "...",
            "legal_basis": "..."
        }},
        "consideration": {{
            "can_negate": true/false,
            "strategy": "...",
            "legal_basis": "..."
        }},
        "prize": {{
            "can_negate": true/false,
            "strategy": "...",
            "max_prize": "...",
            "legal_basis": "..."
        }}
    }},
    "exemptions": [
        {{
            "name": "...",
            "statutory_basis": "...",
            "requirements": [...],
            "prize_limits": "...",
            "location_requirements": "...",
            "strength": "STRONG|MODERATE|WEAK|UNTESTED",
            "game_design_constraints": [...]
        }}
    ],
    "court_rulings_analysis": [
        {{
            "case": "...",
            "holding": "...",
            "impact_on_game_design": "..."
        }}
    ],
    "enforcement_profile": {{
        "posture": "aggressive|moderate|lax",
        "primary_enforcer": "AG|DA|gaming_commission|police",
        "recent_actions": [...],
        "prosecution_targets": "..."
    }},
    "risk_tier": "DEPLOY_NOW|STRUCTURED_DEPLOY|GRAY_AREA|HIGH_RISK|DO_NOT_ENTER",
    "legal_pathways_ranked": [
        {{
            "pathway": "skill_game|amusement_device|sweepstakes|regulated|vlt|other",
            "viability": "HIGH|MEDIUM|LOW",
            "legal_theory": "...",
            "key_risks": [...]
        }}
    ],
    "red_flags": [...],
    "pending_changes": [...]
}}
""",
            expected_output="Structured legal profile JSON with element analysis and pathway ranking",
            agent=self.agents["definition_analyzer"],
        )

        crew = Crew(
            agents=[self.agents["definition_analyzer"]],
            tasks=[task],
            process=Process.sequential,
            verbose=VERBOSE,
        )

        result = crew.kickoff()
        raw = result.raw if hasattr(result, "raw") else str(result)

        try:
            state.legal_profile = json.loads(raw)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                try:
                    state.legal_profile = json.loads(json_match.group())
                except json.JSONDecodeError:
                    state.legal_profile = {"raw_text": raw}
            else:
                state.legal_profile = {"raw_text": raw}

        profile_path = Path(state.output_dir) / "02_legal_profile.json"
        profile_path.write_text(json.dumps(state.legal_profile, indent=2, default=str), encoding="utf-8")
        console.print(f"[green]✓ Legal profile saved: {profile_path}[/green]")

        risk = state.legal_profile.get("risk_tier", "UNKNOWN") if isinstance(state.legal_profile, dict) else "UNKNOWN"
        pathway = "none"
        pathways = state.legal_profile.get("legal_pathways_ranked", []) if isinstance(state.legal_profile, dict) else []
        if pathways:
            pathway = pathways[0].get("pathway", "unknown")

        summary = (
            f"Legal Profile for {state.target_state}:\n"
            f"• Risk Tier: {risk}\n"
            f"• Best Pathway: {pathway}\n"
            f"• Pathways Found: {len(pathways)}\n"
        )

        if risk == "DO_NOT_ENTER":
            console.print(f"[bold red]⚠ {state.target_state} classified as DO_NOT_ENTER[/bold red]")
            console.print("[red]Proceeding with game architecture for research purposes only.[/red]")

        recon_hitl("Legal Analysis", summary, state)
        return state

    # ────────────────────────────────────────
    # STAGE 3: Compliant Game Architecture
    # ────────────────────────────────────────

    @listen(analyze_definitions)
    def architect_game(self):
        """Design game mechanics that fit inside the identified legal safe harbor."""
        state = self.state

        if state.errors and "aborted" in state.errors[-1].lower():
            return state

        console.print("\n[bold magenta]═══ STAGE 3: COMPLIANT GAME ARCHITECTURE ═══[/bold magenta]\n")

        profile_json = json.dumps(state.legal_profile, indent=2, default=str)

        task = Task(
            description=f"""
Design a slot-style game that is LEGALLY DEFENSIBLE in {state.target_state} based
on the following legal profile:

LEGAL PROFILE:
{profile_json[:12000]}

DESIGN REQUIREMENTS:

1. LEGAL PATHWAY: Use the #1 ranked legal pathway from the profile.
   EVERY game mechanic must map to a specific legal justification.

2. SKILL ELEMENTS (if pathway requires skill):
   Design SPECIFIC, IMPLEMENTABLE skill mechanics. NOT vague concepts.
   For each skill element, specify:
   - Exact player action (e.g., "player taps to stop reels within a 500ms window")
   - How it affects outcome (e.g., "stopping within target zone awards 2x multiplier")
   - Skill/chance ratio (e.g., "skilled player achieves 94% RTP vs 88% for unskilled")
   - Implementation spec (enough detail for a developer)

3. PRIZE STRUCTURE: Design prizes that comply with state limits.
   Specify: form (cash/gift card/merchandise/credits), max value, payout mechanism.

4. PROHIBITED FEATURES: Explicitly list what the game CANNOT have.
   These are features that would push the game outside the legal safe harbor.

5. GAME FLOW: Design the complete player experience from session start to cash-out.
   Mark every point where a legal requirement is satisfied.

6. HARDWARE/SOFTWARE REQUIREMENTS: If the legal pathway requires specific hardware
   (e.g., no coin slot for Virginia QVS2 model), specify it.

7. OPERATIONAL REQUIREMENTS: Location type, licensing, signage, age verification,
   record-keeping, tax reporting.

OUTPUT FORMAT (JSON):
{{
    "state": "{state.target_state}",
    "legal_pathway": "...",
    "legal_classification": "skill_game|amusement_device|sweepstakes|vlt|other",

    "game_concept": {{
        "name": "...",
        "description": "...",
        "player_experience": "..."
    }},

    "core_mechanics": {{
        "base_game": {{
            "type": "reel_spin|card_draw|puzzle|other",
            "grid": "5x3 or similar",
            "description": "..."
        }},
        "skill_elements": [
            {{
                "mechanic": "...",
                "player_action": "exact description of what player does",
                "outcome_effect": "exactly how this affects the result",
                "skill_advantage": "percentage advantage for skilled player",
                "legal_justification": "maps to which statute/exemption",
                "implementation_spec": "developer-level detail"
            }}
        ],
        "rng_elements": {{
            "what_is_random": "...",
            "what_is_player_controlled": "...",
            "chance_skill_ratio": "estimated percentage"
        }}
    }},

    "prize_structure": {{
        "form": "cash|gift_card|merchandise|credits|other",
        "max_single_prize": "...",
        "payout_mechanism": "...",
        "statutory_basis": "...",
        "prohibited_prize_types": [...]
    }},

    "rtp_design": {{
        "unskilled_rtp": "...",
        "skilled_rtp": "...",
        "theoretical_max": "...",
        "house_edge": "..."
    }},

    "prohibited_features": [
        {{
            "feature": "...",
            "reason": "would trigger [statute] because..."
        }}
    ],

    "game_flow": [
        {{
            "step": 1,
            "action": "...",
            "legal_note": "satisfies [requirement] because..."
        }}
    ],

    "hardware_requirements": {{
        "payment_acceptance": "...",
        "display": "...",
        "input_devices": "...",
        "special_requirements": "..."
    }},

    "operational_requirements": {{
        "location_types": [...],
        "licensing": "...",
        "age_verification": "...",
        "signage": "...",
        "record_keeping": "...",
        "tax_reporting": "..."
    }}
}}
""",
            expected_output="Complete compliant game architecture JSON with statutory mapping",
            agent=self.agents["game_architect"],
        )

        crew = Crew(
            agents=[self.agents["game_architect"]],
            tasks=[task],
            process=Process.sequential,
            verbose=VERBOSE,
        )

        result = crew.kickoff()
        raw = result.raw if hasattr(result, "raw") else str(result)

        try:
            state.game_architecture = json.loads(raw)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                try:
                    state.game_architecture = json.loads(json_match.group())
                except json.JSONDecodeError:
                    state.game_architecture = {"raw_text": raw}
            else:
                state.game_architecture = {"raw_text": raw}

        arch_path = Path(state.output_dir) / "03_game_architecture.json"
        arch_path.write_text(json.dumps(state.game_architecture, indent=2, default=str), encoding="utf-8")
        console.print(f"[green]✓ Game architecture saved: {arch_path}[/green]")

        game_name = "Unknown"
        skill_count = 0
        if isinstance(state.game_architecture, dict):
            concept = state.game_architecture.get("game_concept", {})
            game_name = concept.get("name", "Unknown")
            mechs = state.game_architecture.get("core_mechanics", {})
            skill_count = len(mechs.get("skill_elements", []))

        summary = (
            f"Game Architecture for {state.target_state}:\n"
            f"• Game: {game_name}\n"
            f"• Skill elements: {skill_count}\n"
            f"• Legal pathway: {state.game_architecture.get('legal_pathway', 'unknown') if isinstance(state.game_architecture, dict) else 'unknown'}\n"
        )

        recon_hitl("Game Architecture", summary, state)
        return state

    # ────────────────────────────────────────
    # STAGE 4: Defense Brief
    # ────────────────────────────────────────

    @listen(architect_game)
    def generate_defense_brief(self):
        """Produce a legal defense brief mapping every mechanic to statute."""
        state = self.state

        if state.errors and "aborted" in state.errors[-1].lower():
            return state

        console.print("\n[bold red]═══ STAGE 4: DEFENSE BRIEF ═══[/bold red]\n")

        profile_json = json.dumps(state.legal_profile, indent=2, default=str)
        arch_json = json.dumps(state.game_architecture, indent=2, default=str)

        task = Task(
            description=f"""
Generate a comprehensive legal defense brief for operating the proposed game in
{state.target_state}. This brief should be usable by a real attorney as a starting point.

LEGAL PROFILE:
{profile_json[:8000]}

GAME ARCHITECTURE:
{arch_json[:8000]}

BRIEF MUST INCLUDE:

1. EXECUTIVE SUMMARY: One-paragraph statement of the legal theory.

2. STATUTORY FRAMEWORK: Cite the exact statutes at issue.

3. ELEMENT-BY-ELEMENT DEFENSE: For each element of the gambling definition,
   demonstrate why this game does NOT satisfy that element. For each argument:
   - State the element
   - Cite the statutory basis
   - Explain how the game negates this element
   - Anticipate the prosecution's counter-argument
   - Provide a rebuttal
   - Cite supporting case law if available

4. EXEMPTION DEFENSE (if applicable): Demonstrate the game qualifies for a
   specific statutory exemption. Map each exemption requirement to a game feature.

5. SUPPORTING CASE LAW: Cite relevant cases with holdings.

6. RISK MATRIX:
   - Probability of prosecution (LOW/MEDIUM/HIGH)
   - Probability of conviction if prosecuted (LOW/MEDIUM/HIGH)
   - Severity of penalties if convicted
   - Mitigating factors

7. PROSECUTION'S BEST CASE: Honestly present the strongest argument AGAINST
   the game's legality. Then explain why it fails on the law/facts.

8. RECOMMENDED PRECAUTIONS: Specific operational steps to strengthen the defense
   (record-keeping, signage, compliance documentation, expert witnesses to retain).

9. LEGISLATIVE WATCHLIST: Laws or bills that could change the analysis.

OUTPUT FORMAT (JSON):
{{
    "state": "{state.target_state}",
    "brief_date": "...",
    "disclaimer": "FOR RESEARCH PURPOSES ONLY — NOT LEGAL ADVICE. Requires review by licensed attorney.",

    "executive_summary": "...",

    "statutory_framework": [
        {{
            "citation": "...",
            "title": "...",
            "relevance": "...",
            "key_language": "..."
        }}
    ],

    "legal_theory": "...",

    "element_by_element_defense": [
        {{
            "element": "chance|consideration|prize",
            "statutory_basis": "...",
            "game_design_negation": "...",
            "prosecution_argument": "...",
            "rebuttal": "...",
            "supporting_case_law": "...",
            "strength": "STRONG|MODERATE|WEAK"
        }}
    ],

    "exemption_defense": {{
        "exemption_name": "...",
        "statutory_basis": "...",
        "requirement_mapping": [
            {{
                "requirement": "...",
                "game_feature": "...",
                "compliance_evidence": "..."
            }}
        ]
    }},

    "supporting_case_law": [
        {{
            "case": "...",
            "holding": "...",
            "application": "..."
        }}
    ],

    "risk_matrix": {{
        "prosecution_probability": "LOW|MEDIUM|HIGH",
        "conviction_probability_if_prosecuted": "LOW|MEDIUM|HIGH",
        "penalty_severity": "...",
        "mitigating_factors": [...],
        "aggravating_factors": [...]
    }},

    "prosecutions_best_case": {{
        "argument": "...",
        "why_it_fails": "..."
    }},

    "recommended_precautions": [...],

    "expert_witnesses": [
        {{
            "type": "...",
            "purpose": "..."
        }}
    ],

    "legislative_watchlist": [...],

    "overall_assessment": "..."
}}
""",
            expected_output="Complete legal defense brief JSON",
            agent=self.agents["defense_counsel"],
        )

        crew = Crew(
            agents=[self.agents["defense_counsel"]],
            tasks=[task],
            process=Process.sequential,
            verbose=VERBOSE,
        )

        result = crew.kickoff()
        raw = result.raw if hasattr(result, "raw") else str(result)

        try:
            state.defense_brief = json.loads(raw)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                try:
                    state.defense_brief = json.loads(json_match.group())
                except json.JSONDecodeError:
                    state.defense_brief = {"raw_text": raw}
            else:
                state.defense_brief = {"raw_text": raw}

        brief_path = Path(state.output_dir) / "04_defense_brief.json"
        brief_path.write_text(json.dumps(state.defense_brief, indent=2, default=str), encoding="utf-8")
        console.print(f"[green]✓ Defense brief saved: {brief_path}[/green]")

        state.completed_at = datetime.now().isoformat()

        # Save complete recon package
        package = {
            "state": state.target_state,
            "started_at": state.started_at,
            "completed_at": state.completed_at,
            "risk_tier": state.legal_profile.get("risk_tier", "UNKNOWN") if isinstance(state.legal_profile, dict) else "UNKNOWN",
            "legal_pathway": state.game_architecture.get("legal_pathway", "unknown") if isinstance(state.game_architecture, dict) else "unknown",
            "files": {
                "raw_research": "01_raw_research.json",
                "legal_profile": "02_legal_profile.json",
                "game_architecture": "03_game_architecture.json",
                "defense_brief": "04_defense_brief.json",
            },
            "hitl_approvals": state.hitl_approvals,
            "errors": state.errors,
        }
        pkg_path = Path(state.output_dir) / "recon_package.json"
        pkg_path.write_text(json.dumps(package, indent=2), encoding="utf-8")

        console.print(Panel(
            f"[bold green]✓ RECON COMPLETE: {state.target_state}[/bold green]\n\n"
            f"Risk Tier: {package['risk_tier']}\n"
            f"Legal Pathway: {package['legal_pathway']}\n"
            f"Output: {state.output_dir}/\n"
            f"Duration: {state.started_at} → {state.completed_at}",
            title="🏁 State Recon Package",
            border_style="green",
        ))

        # ── Auto-ingest into Qdrant ──
        # This makes the data immediately available for future queries
        # so the system gets smarter with every state researched.
        console.print("\n[bold cyan]Auto-ingesting into Qdrant...[/bold cyan]")
        try:
            from tools.auto_ingest import ingest_recon_result
            ingest_result = ingest_recon_result(state.output_dir, embed=True)
            if ingest_result:
                console.print(f"[green]✓ Ingested into Qdrant: {ingest_result.get('state', 'unknown')}[/green]")
                console.print(f"[green]  RAG doc: {ingest_result.get('rag_path', 'N/A')}[/green]")
            else:
                console.print("[yellow]⚠ Ingest returned no result (Qdrant may not be configured)[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠ Auto-ingest failed: {e}[/yellow]")
            console.print("[yellow]  Run manually: python -m tools.auto_ingest {state.output_dir} --embed[/yellow]")

        return state


# ============================================================
# Convenience launcher
# ============================================================

def run_recon(state_name: str, auto: bool = False, game_hint: Optional[str] = None, job_id: str = ""):
    """Run the State Recon Flow on a target state."""
    flow = StateReconFlow(auto_mode=auto)
    flow.state.target_state = state_name
    flow.state.game_type_hint = game_hint
    flow.state.job_id = job_id
    result = flow.kickoff()
    return result


# ============================================================
# CLI Entry Point
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Arkain State Recon — Autonomous Legal Research Pipeline")
    parser.add_argument("--state", required=True, help="Target US state, e.g. 'North Carolina'")
    parser.add_argument("--auto", action="store_true", help="Skip HITL checkpoints (auto-approve)")
    parser.add_argument("--game-hint", default=None, help="Game type hint, e.g. 'slot-style'")
    args = parser.parse_args()

    run_recon(args.state, auto=args.auto, game_hint=args.game_hint)
