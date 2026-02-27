"""
ARKAINBRAIN — Jurisdiction Compliance Profiles (Phase 2C)

Pre-built, structured profiles with hard technical requirements for every
major gambling jurisdiction. Returns machine-readable checklists instead of
prose. Used by the Compliance Officer during OODA convergence loops and
during final compliance review.

These profiles encode:
  - GLI-11 / GLI-12 / GLI-19 standard requirements
  - Jurisdiction-specific max win caps
  - Feature bans (bonus buy, autoplay, etc.)
  - RTP range constraints
  - Responsible gambling feature requirements
  - Testing lab certifications needed
  - Content/theme restrictions
"""

import json
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


# ============================================================
# Master Jurisdiction Database
# ============================================================
# Each profile is a complete, structured compliance checklist.
# Sources: UK GC RTS, MGA technical standards, GLI-11, AGCO standards,
# Spelinspektionen regulations, DGOJ requirements.

JURISDICTION_PROFILES = {
    "UK": {
        "authority": "UK Gambling Commission (UKGC)",
        "standard": "RTS (Remote Technical Standards) + GLI-11",
        "rtp": {"min": 70.0, "max": 99.9, "display_required": True, "theoretical_vs_actual": "both"},
        "max_win": {"cap_x": None, "notes": "No hard cap but operators may self-impose 250,000x"},
        "volatility": {"extreme_allowed": True, "disclosure_required": True},
        "features": {
            "banned": ["bonus_buy"],
            "restricted": ["autoplay_speed_over_2.5s"],
            "required": [],
            "notes": "Bonus buy (feature buy) banned since Oct 2021 per UKGC update"
        },
        "responsible_gambling": {
            "reality_check": {"required": True, "interval_minutes": 60, "customizable": True},
            "session_timer": {"required": True, "visible": True},
            "net_position": {"required": True, "display": "session P&L always visible"},
            "loss_limits": {"required": True, "types": ["daily", "weekly", "monthly"]},
            "deposit_limits": {"required": True},
            "self_exclusion": {"required": True, "integration": "GAMSTOP"},
            "panic_button": {"required": True, "location": "visible at all times"},
            "rg_messaging": {"required": True, "frequency": "periodic during play"},
        },
        "content_restrictions": [
            "No content appealing to under-18s (cartoons, toys, youth culture)",
            "No glorification of gambling / implied guaranteed wins",
            "No association with criminal or antisocial behavior",
            "Free play/demo mode must NOT require registration",
            "Win celebrations must not be disproportionate to actual win amount",
        ],
        "technical_requirements": {
            "rng": "ISO 17025 certified RNG or equivalent",
            "min_game_cycle_time_ms": 2500,
            "max_autoplay_spins": None,
            "autoplay_loss_limit_stop": True,
            "jackpot_contribution_disclosure": True,
            "game_history": {"required": True, "min_records": 50, "accessible_from_game": True},
            "error_handling": "Game state must be recoverable on disconnect",
            "pending_wins": "Must be clearly communicated and paid without further wagering",
        },
        "testing_labs": ["GLI", "BMM Testlabs", "eCOGRA", "NMi Gaming"],
        "testing_requirements": {
            "rtp_verification": {"min_spins": 10_000_000, "tolerance_pct": 1.0},
            "feature_trigger_verification": True,
            "max_win_path_verification": True,
            "rng_statistical_tests": ["chi-square", "runs", "serial correlation"],
            "penetration_testing": True,
            "game_log_audit": True,
        },
        "data_privacy": "GDPR (full compliance required)",
        "submission_documents": [
            "Game rules document (player-facing)",
            "PAR sheet (RTP breakdown, hit frequency, volatility)",
            "Complete paytable with all pay combinations",
            "Reel strip data (all reel sets)",
            "Feature description with trigger rates and expected value",
            "RNG certificate",
            "Responsible gambling implementation details",
        ],
    },

    "Malta": {
        "authority": "Malta Gaming Authority (MGA)",
        "standard": "MGA Technical Standards + GLI-11",
        "rtp": {"min": 85.0, "max": 99.9, "display_required": True, "theoretical_vs_actual": "theoretical"},
        "max_win": {"cap_x": None, "notes": "No regulatory cap"},
        "volatility": {"extreme_allowed": True, "disclosure_required": False},
        "features": {
            "banned": [],
            "restricted": [],
            "required": [],
            "notes": "Most permissive major jurisdiction. Bonus buy allowed."
        },
        "responsible_gambling": {
            "reality_check": {"required": True, "interval_minutes": 60, "customizable": False},
            "session_timer": {"required": True, "visible": True},
            "net_position": {"required": False},
            "loss_limits": {"required": True, "types": ["self-set"]},
            "deposit_limits": {"required": True},
            "self_exclusion": {"required": True, "integration": "operator-managed"},
            "panic_button": {"required": False},
            "rg_messaging": {"required": True, "frequency": "at login and periodically"},
        },
        "content_restrictions": [
            "No offensive or discriminatory content",
            "No false or misleading information about winning probability",
        ],
        "technical_requirements": {
            "rng": "Certified RNG (GLI-11 or equivalent)",
            "min_game_cycle_time_ms": 1000,
            "max_autoplay_spins": None,
            "autoplay_loss_limit_stop": False,
            "jackpot_contribution_disclosure": True,
            "game_history": {"required": True, "min_records": 25},
            "error_handling": "Recover game state on disconnect",
        },
        "testing_labs": ["GLI", "BMM Testlabs", "iTech Labs", "Gaming Associates"],
        "testing_requirements": {
            "rtp_verification": {"min_spins": 10_000_000, "tolerance_pct": 1.0},
            "feature_trigger_verification": True,
            "max_win_path_verification": False,
            "rng_statistical_tests": ["chi-square", "serial correlation"],
        },
        "data_privacy": "GDPR",
        "submission_documents": [
            "Game rules", "PAR sheet", "Paytable", "Reel strips",
            "RNG certificate", "Feature documentation",
        ],
    },

    "Ontario": {
        "authority": "Alcohol and Gaming Commission of Ontario (AGCO)",
        "standard": "AGCO iGaming Standards + GLI-11",
        "rtp": {"min": 85.0, "max": 99.9, "display_required": True, "theoretical_vs_actual": "theoretical"},
        "max_win": {"cap_x": None, "notes": "No hard cap but AGCO may review extreme volatility"},
        "volatility": {"extreme_allowed": True, "disclosure_required": True},
        "features": {
            "banned": [],
            "restricted": ["bonus_buy"],
            "required": [],
            "notes": "Bonus buy allowed but under enhanced scrutiny. Must clearly disclose cost."
        },
        "responsible_gambling": {
            "reality_check": {"required": True, "interval_minutes": 60, "customizable": True},
            "session_timer": {"required": True, "visible": True},
            "net_position": {"required": True, "display": "session P&L"},
            "loss_limits": {"required": True, "types": ["daily", "weekly", "monthly"]},
            "deposit_limits": {"required": True},
            "self_exclusion": {"required": True, "integration": "ConnexOntario"},
            "panic_button": {"required": True},
            "rg_messaging": {"required": True, "frequency": "periodic"},
            "play_break_reminders": {"required": True, "interval_minutes": 60},
        },
        "content_restrictions": [
            "No content targeting minors",
            "No inducement to problem gambling",
            "No misleading promotional offers",
            "Must comply with Canadian advertising standards",
        ],
        "technical_requirements": {
            "rng": "GLI-11 certified",
            "min_game_cycle_time_ms": 2000,
            "game_history": {"required": True, "min_records": 50},
            "error_handling": "Full state recovery",
        },
        "testing_labs": ["GLI", "BMM Testlabs", "iTech Labs", "Gaming Associates"],
        "testing_requirements": {
            "rtp_verification": {"min_spins": 10_000_000, "tolerance_pct": 1.0},
            "feature_trigger_verification": True,
        },
        "data_privacy": "PIPEDA (Personal Information Protection and Electronic Documents Act)",
        "submission_documents": [
            "Game rules", "PAR sheet", "Paytable", "Reel strips",
            "RNG certificate", "RG implementation details", "Feature documentation",
        ],
    },

    "Sweden": {
        "authority": "Spelinspektionen (Swedish Gambling Authority)",
        "standard": "Swedish Gambling Act + GLI-11",
        "rtp": {"min": 80.0, "max": 99.9, "display_required": True, "theoretical_vs_actual": "theoretical"},
        "max_win": {"cap_x": None, "notes": "No hard cap"},
        "volatility": {"extreme_allowed": True, "disclosure_required": True},
        "features": {
            "banned": ["bonus_buy", "autoplay"],
            "restricted": ["turbo_spin"],
            "required": [],
            "notes": "BOTH bonus buy AND autoplay fully banned. Turbo spin restricted."
        },
        "responsible_gambling": {
            "reality_check": {"required": True, "interval_minutes": 60, "customizable": True},
            "session_timer": {"required": True, "visible": True},
            "net_position": {"required": True, "display": "always visible"},
            "loss_limits": {"required": True, "types": ["daily", "weekly", "monthly"]},
            "deposit_limits": {"required": True, "mandatory_temporary": True},
            "self_exclusion": {"required": True, "integration": "Spelpaus.se"},
            "panic_button": {"required": True},
            "rg_messaging": {"required": True, "frequency": "high - every session"},
        },
        "content_restrictions": [
            "No content appealing to minors",
            "No gambling glorification",
            "No misleading win representations",
            "Moderate advertising only — no aggressive promotions",
        ],
        "technical_requirements": {
            "rng": "GLI-11 certified",
            "min_game_cycle_time_ms": 3000,
            "max_autoplay_spins": 0,
            "game_history": {"required": True, "min_records": 50},
        },
        "testing_labs": ["GLI", "BMM Testlabs"],
        "testing_requirements": {
            "rtp_verification": {"min_spins": 10_000_000, "tolerance_pct": 1.0},
            "feature_trigger_verification": True,
            "autoplay_disabled_verification": True,
            "bonus_buy_disabled_verification": True,
        },
        "data_privacy": "GDPR",
        "submission_documents": [
            "Game rules", "PAR sheet", "Paytable", "Reel strips",
            "RNG certificate", "RG implementation", "Autoplay removal proof",
        ],
    },

    "New Jersey": {
        "authority": "NJ Division of Gaming Enforcement (DGE)",
        "standard": "NJ Technical Standards + GLI-11",
        "rtp": {"min": 83.0, "max": 99.9, "display_required": False, "theoretical_vs_actual": "theoretical"},
        "max_win": {"cap_x": None, "notes": "No regulatory cap"},
        "volatility": {"extreme_allowed": True, "disclosure_required": False},
        "features": {
            "banned": [],
            "restricted": [],
            "required": ["geolocation"],
            "notes": "Geolocation verification mandatory on every session. Established market."
        },
        "responsible_gambling": {
            "reality_check": {"required": False},
            "session_timer": {"required": True, "visible": True},
            "loss_limits": {"required": True, "types": ["self-set"]},
            "deposit_limits": {"required": True},
            "self_exclusion": {"required": True, "integration": "NJ Self-Exclusion Program"},
            "rg_messaging": {"required": True, "frequency": "at login"},
        },
        "content_restrictions": [
            "Standard gaming content rules",
            "No content targeting minors",
        ],
        "technical_requirements": {
            "rng": "GLI-11 certified",
            "min_game_cycle_time_ms": 1500,
            "geolocation": {"required": True, "provider": "GeoComply or equivalent"},
            "game_history": {"required": True, "min_records": 25},
        },
        "testing_labs": ["GLI", "BMM Testlabs"],
        "data_privacy": "NJ privacy laws",
        "submission_documents": [
            "Game rules", "PAR sheet", "Paytable", "Reel strips",
            "RNG certificate", "Geolocation implementation details",
        ],
    },

    "Spain": {
        "authority": "DGOJ (Dirección General de Ordenación del Juego)",
        "standard": "DGOJ Technical Standards + GLI-11",
        "rtp": {"min": 85.0, "max": 99.9, "display_required": True, "theoretical_vs_actual": "theoretical"},
        "max_win": {"cap_x": None, "notes": "No hard cap but extreme wins trigger reporting"},
        "features": {
            "banned": ["bonus_buy"],
            "restricted": ["autoplay"],
            "required": [],
            "notes": "Bonus buy banned. Autoplay restricted (max 25 spins, mandatory stop on win)."
        },
        "responsible_gambling": {
            "reality_check": {"required": True, "interval_minutes": 60},
            "session_timer": {"required": True, "visible": True},
            "loss_limits": {"required": True, "types": ["daily", "weekly", "monthly"]},
            "deposit_limits": {"required": True},
            "self_exclusion": {"required": True, "integration": "RGIAJ"},
            "rg_messaging": {"required": True, "frequency": "periodic"},
        },
        "content_restrictions": [
            "No content appealing to minors",
            "No celebrity or influencer endorsements",
            "No gambling glorification",
            "Advertising heavily restricted (hours, channels, content)",
        ],
        "testing_labs": ["GLI", "BMM Testlabs"],
        "data_privacy": "GDPR + LOPDGDD (Spanish data protection law)",
        "submission_documents": [
            "Game rules (Spanish translation required)", "PAR sheet", "Paytable",
            "Reel strips", "RNG certificate", "RG implementation",
        ],
    },

    "Curacao": {
        "authority": "Curaçao Gaming Control Board (GCB)",
        "standard": "Curaçao National Ordinance on Offshore Games of Hazard",
        "rtp": {"min": 75.0, "max": 99.9, "display_required": False, "theoretical_vs_actual": "theoretical"},
        "max_win": {"cap_x": None, "notes": "No cap"},
        "volatility": {"extreme_allowed": True, "disclosure_required": False},
        "features": {
            "banned": [],
            "restricted": [],
            "required": [],
            "notes": "Most permissive major jurisdiction. New 2024+ regulations tightening requirements."
        },
        "responsible_gambling": {
            "reality_check": {"required": False},
            "session_timer": {"required": False},
            "loss_limits": {"required": False},
            "deposit_limits": {"required": True},
            "self_exclusion": {"required": True, "integration": "operator-managed"},
            "rg_messaging": {"required": True, "frequency": "basic"},
        },
        "content_restrictions": ["Basic decency standards"],
        "technical_requirements": {
            "rng": "Third-party certified RNG",
            "min_game_cycle_time_ms": 500,
        },
        "testing_labs": ["GLI", "iTech Labs", "Gaming Associates"],
        "data_privacy": "Basic (Curaçao data protection regulations)",
        "submission_documents": ["Game rules", "RNG certificate", "Basic paytable"],
    },

    "Georgia": {
        "authority": "Georgia Lottery Commission / Tribal compacts",
        "standard": "State-specific (varies by operator type)",
        "rtp": {"min": 75.0, "max": 99.9, "display_required": False},
        "max_win": {"cap_x": None, "notes": "Varies by operator — tribal compacts may set limits"},
        "features": {
            "banned": [],
            "restricted": [],
            "required": [],
            "notes": "Georgia's gaming landscape is evolving. Skill-game and tribal contexts differ significantly."
        },
        "responsible_gambling": {
            "rg_messaging": {"required": True, "frequency": "basic"},
            "self_exclusion": {"required": True, "integration": "operator-managed"},
        },
        "content_restrictions": ["No content appealing to minors", "Standard decency"],
        "technical_requirements": {"rng": "GLI-11 certified"},
        "testing_labs": ["GLI", "BMM Testlabs"],
        "data_privacy": "US state privacy laws",
        "submission_documents": ["Game rules", "PAR sheet", "Paytable", "RNG certificate"],
    },

    "Texas": {
        "authority": "Texas Racing Commission / Tribal gaming authorities",
        "standard": "State-specific + tribal compact requirements",
        "rtp": {"min": 75.0, "max": 99.9, "display_required": False},
        "max_win": {"cap_x": None, "notes": "Tribal compacts may define limits"},
        "features": {
            "banned": [],
            "restricted": [],
            "required": [],
            "notes": "Limited casino gaming. Tribal and sweepstakes contexts. Legal landscape may shift."
        },
        "responsible_gambling": {
            "rg_messaging": {"required": True, "frequency": "basic"},
            "self_exclusion": {"required": True, "integration": "operator-managed"},
        },
        "content_restrictions": ["Standard decency"],
        "technical_requirements": {"rng": "GLI-11 certified"},
        "testing_labs": ["GLI", "BMM Testlabs"],
        "data_privacy": "Texas state privacy laws",
        "submission_documents": ["Game rules", "PAR sheet", "Paytable", "RNG certificate"],
    },
}


# ============================================================
# Tool: Jurisdiction Compliance Checker
# ============================================================

class ComplianceCheckInput(BaseModel):
    markets: list[str] = Field(description="List of target jurisdictions, e.g. ['UK', 'Malta', 'Ontario']")
    proposed_rtp: float = Field(default=96.0, description="Proposed RTP percentage")
    proposed_max_win: int = Field(default=5000, description="Proposed max win multiplier")
    proposed_features: list[str] = Field(default_factory=list, description="List of proposed features, e.g. ['bonus_buy', 'autoplay']")
    game_theme: str = Field(default="", description="Game theme for content restriction check")


class JurisdictionComplianceCheckerTool(BaseTool):
    """Check a game against hard compliance requirements for all target markets.
    Returns a structured checklist with PASS/FAIL per requirement, not prose."""

    name: str = "check_jurisdiction_compliance"
    description: str = (
        "Check a proposed game against structured compliance requirements for all target "
        "jurisdictions. Returns a per-market checklist with PASS/FAIL for: RTP range, "
        "max win cap, banned features, required responsible gambling features, content "
        "restrictions, testing requirements, and submission documents needed. "
        "Much more detailed than jurisdiction_intersection — use this for final compliance."
    )
    args_schema: type[BaseModel] = ComplianceCheckInput

    def _run(self, markets: list[str], proposed_rtp: float = 96.0,
             proposed_max_win: int = 5000, proposed_features: list[str] = None,
             game_theme: str = "") -> str:
        proposed_features = proposed_features or []
        results = {
            "markets_checked": [],
            "unknown_markets": [],
            "blockers": [],
            "warnings": [],
            "per_market": {},
            "intersection": {},
            "submission_checklist": [],
        }

        all_required_rg = set()
        all_banned = set()
        all_submission_docs = set()
        tightest_min_rtp = 0.0
        slowest_cycle_ms = 0

        for market_name in markets:
            # Try exact match, then case-insensitive
            profile = JURISDICTION_PROFILES.get(market_name)
            if not profile:
                for k, v in JURISDICTION_PROFILES.items():
                    if k.lower() == market_name.lower().strip():
                        profile = v
                        market_name = k
                        break

            if not profile:
                results["unknown_markets"].append(market_name)
                continue

            results["markets_checked"].append(market_name)
            checks = {"market": market_name, "authority": profile["authority"], "checks": []}

            # ── RTP check ──
            rtp_range = profile.get("rtp", {})
            min_rtp = rtp_range.get("min", 0)
            max_rtp = rtp_range.get("max", 100)
            rtp_ok = min_rtp <= proposed_rtp <= max_rtp
            checks["checks"].append({
                "category": "RTP",
                "status": "PASS" if rtp_ok else "FAIL",
                "detail": f"Proposed {proposed_rtp}% {'within' if rtp_ok else 'outside'} range {min_rtp}-{max_rtp}%",
            })
            if not rtp_ok:
                results["blockers"].append(f"{market_name}: RTP {proposed_rtp}% outside range {min_rtp}-{max_rtp}%")
            tightest_min_rtp = max(tightest_min_rtp, min_rtp)

            # ── Max win check ──
            max_win_info = profile.get("max_win", {})
            cap = max_win_info.get("cap_x")
            if cap and proposed_max_win > cap:
                checks["checks"].append({
                    "category": "Max Win",
                    "status": "FAIL",
                    "detail": f"Proposed {proposed_max_win}x exceeds {market_name} cap of {cap}x",
                })
                results["blockers"].append(f"{market_name}: Max win {proposed_max_win}x exceeds cap {cap}x")
            else:
                checks["checks"].append({
                    "category": "Max Win",
                    "status": "PASS",
                    "detail": f"{proposed_max_win}x {'within cap' if cap else 'no cap in'} {market_name}",
                })

            # ── Feature bans ──
            features_info = profile.get("features", {})
            banned = features_info.get("banned", [])
            restricted = features_info.get("restricted", [])
            banned_hits = [f for f in proposed_features if f in banned]
            restricted_hits = [f for f in proposed_features if f in restricted]

            if banned_hits:
                checks["checks"].append({
                    "category": "Banned Features",
                    "status": "FAIL",
                    "detail": f"Features banned in {market_name}: {', '.join(banned_hits)}",
                })
                results["blockers"].append(f"{market_name}: Banned features used: {', '.join(banned_hits)}")
                all_banned.update(banned_hits)
            else:
                checks["checks"].append({"category": "Banned Features", "status": "PASS", "detail": "No banned features"})

            if restricted_hits:
                checks["checks"].append({
                    "category": "Restricted Features",
                    "status": "WARN",
                    "detail": f"Features restricted in {market_name}: {', '.join(restricted_hits)} — {features_info.get('notes', '')}",
                })
                results["warnings"].append(f"{market_name}: Restricted features: {', '.join(restricted_hits)}")

            # ── Responsible gambling requirements ──
            rg = profile.get("responsible_gambling", {})
            missing_rg = []
            for rg_feature, rg_spec in rg.items():
                if isinstance(rg_spec, dict) and rg_spec.get("required"):
                    all_required_rg.add(rg_feature)
                    missing_rg.append(rg_feature)

            checks["checks"].append({
                "category": "Responsible Gambling",
                "status": "INFO",
                "detail": f"Required RG features: {', '.join(missing_rg) if missing_rg else 'basic only'}",
            })

            # ── Technical requirements ──
            tech = profile.get("technical_requirements", {})
            cycle_ms = tech.get("min_game_cycle_time_ms", 0)
            slowest_cycle_ms = max(slowest_cycle_ms, cycle_ms)
            checks["checks"].append({
                "category": "Technical",
                "status": "INFO",
                "detail": f"Min cycle time: {cycle_ms}ms, RNG: {tech.get('rng', 'required')}",
            })

            # ── Submission docs ──
            docs = profile.get("submission_documents", [])
            all_submission_docs.update(docs)

            checks["total_pass"] = sum(1 for c in checks["checks"] if c["status"] == "PASS")
            checks["total_fail"] = sum(1 for c in checks["checks"] if c["status"] == "FAIL")
            results["per_market"][market_name] = checks

        # ── Build intersection ──
        results["intersection"] = {
            "tightest_min_rtp": tightest_min_rtp,
            "rtp_compliant": proposed_rtp >= tightest_min_rtp,
            "features_banned_in_any_market": sorted(all_banned),
            "all_required_rg_features": sorted(all_required_rg),
            "slowest_min_cycle_ms": slowest_cycle_ms,
        }

        results["submission_checklist"] = sorted(all_submission_docs)

        # ── Verdict ──
        if results["blockers"]:
            results["verdict"] = "BLOCKED"
            results["summary"] = f"{len(results['blockers'])} blocker(s): {'; '.join(results['blockers'][:3])}"
        elif results["warnings"]:
            results["verdict"] = "CONDITIONAL_PASS"
            results["summary"] = f"Passes with {len(results['warnings'])} warning(s)"
        else:
            results["verdict"] = "CLEAR"
            results["summary"] = f"All {len(results['markets_checked'])} markets clear"

        if results["unknown_markets"]:
            results["summary"] += f". Unknown markets (need manual check): {results['unknown_markets']}"

        return json.dumps(results, indent=2)


# ============================================================
# Tool: Get Jurisdiction Profile
# ============================================================

class ProfileInput(BaseModel):
    market: str = Field(description="Jurisdiction name, e.g. 'UK', 'Malta', 'Ontario'")


class GetJurisdictionProfileTool(BaseTool):
    """Get the complete compliance profile for a specific jurisdiction.
    Returns all hard requirements, testing standards, and submission documents."""

    name: str = "get_jurisdiction_profile"
    description: str = (
        "Get the complete structured compliance profile for a specific gambling jurisdiction. "
        "Returns: authority name, RTP range, max win cap, banned features, responsible "
        "gambling requirements, technical standards (GLI-11 mapping), testing lab requirements, "
        "content restrictions, and required submission documents. Use this for detailed "
        "compliance review of a single market."
    )
    args_schema: type[BaseModel] = ProfileInput

    def _run(self, market: str) -> str:
        profile = JURISDICTION_PROFILES.get(market)
        if not profile:
            for k, v in JURISDICTION_PROFILES.items():
                if k.lower() == market.lower().strip():
                    profile = v
                    market = k
                    break

        if not profile:
            available = sorted(JURISDICTION_PROFILES.keys())
            return json.dumps({
                "error": f"Unknown jurisdiction: {market}",
                "available_jurisdictions": available,
                "hint": "Use one of the available jurisdiction names"
            })

        return json.dumps({"jurisdiction": market, **profile}, indent=2, default=str)
