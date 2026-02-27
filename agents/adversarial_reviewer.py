"""
ARKAINBRAIN — Adversarial Reviewer Agent

UPGRADE 5: A dedicated "Red Team" agent that:
1. Reviews every pipeline deliverable before HITL checkpoints
2. Pokes holes in legal arguments, math models, game designs
3. Identifies regulatory risks the compliance officer missed
4. Challenges market assumptions with counter-evidence
5. Writes structured critique reports

This agent runs BETWEEN the production stage and the HITL checkpoint,
so when you see the review in the browser, it includes the adversarial
critique alongside the deliverable.
"""

import json
import os
from crewai import Agent
from config.settings import LLMConfig

from tools.advanced_research import WebFetchTool, DeepResearchTool
from tools.custom_tools import RegulatoryRAGTool, SlotDatabaseSearchTool


def create_adversarial_reviewer() -> Agent:
    """
    The Devil's Advocate. Uses GPT-4o (heavy) because this agent
    needs maximum reasoning depth to find genuine flaws.
    """
    return Agent(
        role="Adversarial Reviewer & Red Team Analyst",
        goal=(
            "Challenge every deliverable with rigorous critique. Find flaws in legal arguments, "
            "math models, game designs, and compliance assessments. Your job is to PREVENT "
            "bad product from reaching production. Be constructive but RUTHLESS. "
            "Every flaw you catch saves the team from costly mistakes."
        ),
        backstory=(
            "Former gaming regulator who spent 12 years reviewing submissions at the UK Gambling Commission "
            "and GLI. You've rejected hundreds of games for subtle compliance failures. Then moved to "
            "private sector as a risk consultant, where you saved studios millions by catching issues "
            "pre-submission. You have an encyclopedic knowledge of how regulators think, what red flags "
            "they look for, and where game designers cut corners. You're not mean — you're protective. "
            "Every critique you write comes with a specific, actionable fix."
        ),
        llm=LLMConfig.get_llm("lead_producer"),  # Uses GPT-4o for deep reasoning
        max_iter=5,
        verbose=True,
        tools=[
            WebFetchTool(),
            DeepResearchTool(),
            RegulatoryRAGTool(),
            SlotDatabaseSearchTool(),
        ],
    )


# ============================================================
# Review Prompts for Each Pipeline Stage
# ============================================================

REVIEW_PROMPTS = {
    "post_research": """
ADVERSARIAL REVIEW: Market Research

You are reviewing the market research output. Your job is to identify:

1. **Confirmation Bias**: Did the research only look for evidence supporting the concept?
   Find counter-evidence. Search for games with this theme that FAILED.

2. **Market Saturation**: How many games already exist with this exact theme?
   If there are 50+ Egyptian slots, the bar for differentiation is extremely high.

3. **Data Recency**: Is the research using current data? The market shifts fast.
   Check if cited games are still actively deployed or have been retired.

4. **Missing Competitors**: What major competitors were MISSED? Use the competitor
   teardown tool to find games the research overlooked.

5. **Audience Assumptions**: Does the research assume a target audience without data?
   Challenge demographic claims with actual market intelligence.

DELIVERABLE: Write a structured critique with:
- CRITICAL ISSUES (must fix before proceeding)
- WARNINGS (should address)
- SUGGESTIONS (nice to have)
- MISSING DATA (what wasn't researched)
""",

    "post_design_math": """
ADVERSARIAL REVIEW: Game Design Document + Math Model

This is the MOST CRITICAL review point. Scrutinize:

1. **Math Integrity**:
   - Does the RTP actually hit the target? Verify the simulation methodology.
   - Is the hit frequency realistic for the claimed volatility?
   - Does the max win actually occur at the claimed frequency?
   - Are the reel strips properly balanced? Check for degenerate patterns.
   - Does the win distribution match the volatility claim?

2. **Feature Feasibility**:
   - Can every feature described in the GDD be mathematically modeled?
   - Are trigger rates realistic? (e.g., if bonus triggers 1 in 200 spins,
     does the base game RTP still work?)
   - Do feature interactions create exploitable patterns?

3. **Regulatory Compliance**:
   - Check RTP against EACH target market's requirements.
   - UK requires 70-99.9% RTP. Malta requires >92%. Ontario varies.
   - Does the max win exceed any market's limits?
   - Is the bonus buy feature legal in all target markets? (UK BANNED it)

4. **Design vs Math Alignment**:
   - Does the GDD describe features the math model doesn't account for?
   - Are there "creative" features that are mathematically impossible?

5. **Competitive Positioning**:
   - Search for the exact feature combination proposed. Has it been done?
   - Is the claimed "differentiation" actually different?

DELIVERABLE: Write a structured critique with specific fixes for each issue.
If the math doesn't work, provide the exact numbers that are wrong.
""",

    "post_art_review": """
ADVERSARIAL REVIEW: Art Direction & Mood Boards

Review the art assets for:

1. **Brand Differentiation**: Does this look like every other slot in the market?
   Search for existing games with similar themes and compare the visual approach.

2. **Regulatory Art Compliance**:
   - No content that could be construed as appealing to minors
   - No glorification of gambling/addiction
   - UK ASA guidelines compliance
   - Symbol distinguishability (critical for accessibility)

3. **Production Feasibility**:
   - Can this art style be consistently maintained across 100+ symbols?
   - Are the proposed animations technically feasible?
   - Will the color palette work on mobile screens?

4. **Cultural Sensitivity**:
   - Check for unintentional cultural insensitivity in theme depiction
   - Religious symbols used inappropriately
   - Stereotypical representations

5. **Consistency**:
   - Do all mood board variants actually match the GDD's theme description?
   - Is there a coherent visual language?

DELIVERABLE: Critique with specific visual references and fixes.
""",
}


def build_review_task_description(stage: str, context_summary: str, output_dir: str) -> str:
    """Build the full adversarial review task description."""
    base_prompt = REVIEW_PROMPTS.get(stage, "")

    return f"""
{base_prompt}

=== CONTEXT ===
{context_summary}

=== OUTPUT DIRECTORY ===
{output_dir}

=== YOUR CRITIQUE FORMAT ===
Write your review as a structured report:

## ADVERSARIAL REVIEW: {stage.replace('_', ' ').title()}

### VERDICT: [PASS / PASS WITH CONDITIONS / FAIL]

### CRITICAL ISSUES (Block pipeline until fixed)
1. [Issue] — [Why it matters] — [Specific fix]
2. ...

### WARNINGS (Should fix but not blocking)
1. [Issue] — [Recommended action]
2. ...

### GAPS IN RESEARCH (What wasn't checked)
1. [Gap] — [Why it matters]

### COMPETITIVE INTELLIGENCE
[What you found about similar products in market]

### RECOMMENDATION
[1-2 sentences: proceed, proceed with changes, or redo this stage]

Save your review to: {output_dir}/adversarial_review_{stage}.md
"""
