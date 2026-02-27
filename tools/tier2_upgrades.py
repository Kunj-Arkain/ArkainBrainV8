"""
ARKAINBRAIN — Tier 2 Intelligence Upgrades

UPGRADE 12: PatentIPScannerTool       — Searches Google Patents + USPTO for mechanic IP conflicts
UPGRADE 13: HTML5PrototypeTool        — Generates a playable browser demo from GDD + math model
UPGRADE 14: SoundDesignTool           — AI sound effects via ElevenLabs + full audio design brief
UPGRADE 15: CertificationPlannerTool  — Maps certification path: test lab, standards, timeline, cost
"""

import json
import os
import re
import base64
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ============================================================
# UPGRADE 12: Patent / IP Scanner
# ============================================================
# Game mechanics can be patented (IGT, Aristocrat, SG hold many).
# This tool searches Google Patents and USPTO to flag potential
# conflicts BEFORE the design is finalized.

class PatentScanInput(BaseModel):
    mechanic_description: str = Field(description="Description of the game mechanic to check, e.g. 'cascading reels where winning symbols are removed and replaced by new symbols falling from above'")
    keywords: list[str] = Field(default_factory=list, description="Specific keywords to search, e.g. ['cascading reels', 'tumbling reels', 'avalanche']")
    theme_name: str = Field(default="", description="Game theme for trademark check, e.g. 'Aztec Gold'")


class PatentIPScannerTool(BaseTool):
    """
    Scans Google Patents + USPTO for potential IP conflicts with proposed
    game mechanics and themes.

    Checks:
    1. PATENTS: Known patented slot mechanics (cascading reels, Megaways, etc.)
    2. TRADEMARKS: Theme name conflicts with existing game titles
    3. KNOWN IP HOLDERS: IGT, Aristocrat, SG Gaming, BTG patent portfolios

    Returns risk assessment with specific patent numbers and recommendations.
    """

    name: str = "patent_ip_scan"
    description: str = (
        "Scan for patent and IP conflicts with proposed game mechanics and themes. "
        "Searches Google Patents, USPTO, and known gaming IP databases. Returns: "
        "patent conflicts (with patent numbers), trademark risks, known IP holders, "
        "and risk mitigation recommendations. Use BEFORE finalizing any novel mechanic."
    )
    args_schema: type[BaseModel] = PatentScanInput

    # Known patented mechanics (hardcoded because these are stable, high-value patents)
    KNOWN_PATENTS: ClassVar[dict] = {
        "megaways": {
            "holder": "Big Time Gaming (BTG)",
            "patent_area": "Variable reel modifier mechanic (up to 117,649 ways)",
            "license": "Licensed to select studios. Must license from BTG or risk infringement.",
            "risk": "HIGH — actively enforced",
        },
        "cascading reels": {
            "holder": "Multiple (IGT has early patents, widely licensed now)",
            "patent_area": "Winning symbols removed, replaced by new symbols",
            "license": "Early patents expired/expiring. Lower risk but check specific implementation.",
            "risk": "LOW-MEDIUM — depends on specific implementation",
        },
        "cluster pays": {
            "holder": "NetEnt (original), now widely adopted",
            "patent_area": "Wins based on clusters of adjacent matching symbols",
            "license": "Widely adopted. Original patents likely expired or not enforced.",
            "risk": "LOW",
        },
        "infinity reels": {
            "holder": "ReelPlay / Yggdrasil",
            "patent_area": "Expanding reel set mechanic",
            "license": "Proprietary mechanic. Must license.",
            "risk": "HIGH — proprietary",
        },
        "hold and spin": {
            "holder": "Aristocrat (Lightning Link family)",
            "patent_area": "Locked symbols with respins until no new symbols land",
            "license": "Aristocrat aggressively enforces. Many variations exist in gray area.",
            "risk": "MEDIUM — depends on implementation specifics",
        },
        "bonus buy": {
            "holder": "No single holder (mechanic is generic)",
            "patent_area": "Pay multiplied bet to trigger bonus directly",
            "license": "No IP issue. Note: BANNED in UK, Sweden, Spain.",
            "risk": "LOW (IP) but HIGH (regulatory in some markets)",
        },
        "mystery symbols": {
            "holder": "No single holder",
            "patent_area": "Symbols that reveal as matching symbol on each spin",
            "license": "Generic mechanic, widely used.",
            "risk": "LOW",
        },
        "split symbols": {
            "holder": "Various studios have implementations",
            "patent_area": "Symbols that split into multiple instances",
            "license": "Check specific implementation against iSoftBet, Thunderkick patents.",
            "risk": "LOW-MEDIUM",
        },
        "walking wilds": {
            "holder": "NetEnt (Gonzo's Quest era), widely adopted",
            "patent_area": "Wild symbols that move across reels each spin",
            "license": "Widely adopted. Low enforcement risk.",
            "risk": "LOW",
        },
        "link and win": {
            "holder": "Microgaming / Various",
            "patent_area": "Connected jackpot mechanic across games",
            "license": "Multiple implementations exist. Check specific variant.",
            "risk": "MEDIUM",
        },
    }

    def _run(self, mechanic_description: str, keywords: list[str] = None, theme_name: str = "") -> str:
        serper_key = os.getenv("SERPER_API_KEY")
        keywords = keywords or []

        results = {
            "mechanic_description": mechanic_description,
            "theme_name": theme_name,
            "known_patent_hits": [],
            "patent_search_results": [],
            "trademark_results": [],
            "risk_assessment": {},
            "recommendations": [],
        }

        # Phase 1: Check against known patents
        desc_lower = mechanic_description.lower()
        all_keywords = set(k.lower() for k in keywords)
        all_keywords.update(desc_lower.split())

        for mechanic, info in self.KNOWN_PATENTS.items():
            if mechanic in desc_lower or any(kw in mechanic for kw in all_keywords):
                results["known_patent_hits"].append({
                    "mechanic": mechanic,
                    **info,
                })

        # Phase 2: Search Google Patents via Serper
        if serper_key:
            import httpx
            search_terms = keywords[:3] if keywords else mechanic_description.split()[:5]

            patent_queries = [
                f"slot machine {' '.join(search_terms)} patent gaming",
                f"gaming device {' '.join(search_terms[:3])} patent US",
            ]

            for q in patent_queries:
                try:
                    resp = httpx.post(
                        "https://google.serper.dev/search",
                        headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                        json={"q": q + " site:patents.google.com", "num": 5},
                        timeout=15.0,
                    )
                    for item in resp.json().get("organic", [])[:5]:
                        results["patent_search_results"].append({
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", ""),
                            "url": item.get("link", ""),
                        })
                except Exception:
                    continue

            # Phase 3: Trademark search for theme name
            if theme_name:
                try:
                    # Search for existing games with similar names
                    resp = httpx.post(
                        "https://google.serper.dev/search",
                        headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                        json={"q": f'"{theme_name}" slot game', "num": 8},
                        timeout=15.0,
                    )
                    for item in resp.json().get("organic", [])[:6]:
                        results["trademark_results"].append({
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", ""),
                            "url": item.get("link", ""),
                        })

                    # Check USPTO
                    resp2 = httpx.post(
                        "https://google.serper.dev/search",
                        headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                        json={"q": f'"{theme_name}" trademark gaming site:tsdr.uspto.gov OR site:tmsearch.uspto.gov', "num": 3},
                        timeout=15.0,
                    )
                    for item in resp2.json().get("organic", [])[:3]:
                        results["trademark_results"].append({
                            "source": "USPTO",
                            "title": item.get("title", ""),
                            "url": item.get("link", ""),
                        })
                except Exception:
                    pass

        # Phase 4: Risk assessment
        high_risks = [h for h in results["known_patent_hits"] if h["risk"].startswith("HIGH")]
        med_risks = [h for h in results["known_patent_hits"] if "MEDIUM" in h["risk"]]
        trademark_hits = len(results["trademark_results"])

        overall_risk = "LOW"
        if high_risks:
            overall_risk = "HIGH"
        elif med_risks or trademark_hits > 3:
            overall_risk = "MEDIUM"

        results["risk_assessment"] = {
            "overall_ip_risk": overall_risk,
            "patent_conflicts": len(high_risks),
            "patent_warnings": len(med_risks),
            "trademark_similar_names": trademark_hits,
        }

        # Recommendations
        if high_risks:
            for h in high_risks:
                results["recommendations"].append(
                    f"HIGH RISK: '{h['mechanic']}' is patented by {h['holder']}. {h['license']} "
                    f"Either license the mechanic or design a distinct alternative."
                )
        if trademark_hits > 3:
            results["recommendations"].append(
                f"Theme name '{theme_name}' has {trademark_hits} existing games with similar names. "
                f"Consider a more distinctive title to avoid confusion."
            )
        if not results["recommendations"]:
            results["recommendations"].append("No significant IP conflicts detected. Proceed with caution — this scan is not legal advice.")

        return json.dumps(results, indent=2)


# ============================================================
# UPGRADE 13: HTML5 Prototype Generator
# ============================================================
# Generates a single-file playable browser demo from the GDD + math.
# Output: standalone .html file with embedded JS/CSS.
# Uses the AI-powered prototype engine for theme customization.

from tools.prototype_engine import PrototypeInput, generate_prototype


class HTML5PrototypeTool(BaseTool):
    """
    Generates a playable single-file HTML5 slot demo with AI customization.

    Features:
    - DALL-E symbol images embedded as base64
    - LLM-generated theme CSS (gradients, particles, glows)
    - LLM-generated custom bonus round JavaScript
    - Math model paytable data integration
    - Audio file hookups (if ElevenLabs ran)
    - Mobile-responsive layout
    - Animated spinning reels with win detection

    Output: standalone .html file (no dependencies, offline-capable)
    """

    name: str = "generate_prototype"
    description: str = (
        "Generate a playable HTML5 slot game prototype with AI-customized visuals and bonus rounds. "
        "Single-file, no dependencies. Includes DALL-E symbol art, themed CSS, custom bonus mechanics, "
        "animated reels, win detection, paytable, and mobile layout. "
        "Use AFTER the GDD, math model, and art are complete to create a shareable demo. "
        "Output: standalone .html file that runs in any browser."
    )
    args_schema: type[BaseModel] = PrototypeInput

    def _run(self, game_title: str, theme: str, grid_cols: int = 5, grid_rows: int = 3,
             symbols: list[str] = None, paytable_summary: str = "", features: list[str] = None,
             color_primary: str = "#1a1a2e", color_accent: str = "#e6b800",
             color_text: str = "#ffffff", target_rtp: float = 96.0,
             output_dir: str = "./output",
             art_dir: str = "", audio_dir: str = "",
             gdd_context: str = "", math_context: str = "",
             volatility: str = "medium", max_win_multiplier: int = 5000) -> str:

        return generate_prototype(
            game_title=game_title, theme=theme,
            grid_cols=grid_cols, grid_rows=grid_rows,
            symbols=symbols, features=features,
            color_primary=color_primary, color_accent=color_accent,
            color_text=color_text, target_rtp=target_rtp,
            output_dir=output_dir, paytable_summary=paytable_summary,
            art_dir=art_dir, audio_dir=audio_dir,
            gdd_context=gdd_context, math_context=math_context,
            volatility=volatility, max_win_multiplier=max_win_multiplier,
        )


# ============================================================
# UPGRADE 14: Sound Design — ElevenLabs AI Audio
# ============================================================
# Two-layer tool:
# A) Writes a comprehensive audio design document
# B) Generates actual .mp3 sound effects via ElevenLabs Sound Effects API

class SoundDesignInput(BaseModel):
    action: str = Field(description="'generate_brief' for audio design doc, 'generate_sfx' for AI sound effects, 'full' for both")
    theme: str = Field(default="", description="Game theme, e.g. 'Ancient Egyptian'")
    sound_type: str = Field(default="", description="For generate_sfx: 'spin_start', 'spin_stop', 'win_small', 'win_big', 'win_mega', 'scatter_land', 'bonus_trigger', 'free_spin_start', 'ambient', 'reel_tick', 'button_click', 'anticipation'")
    description: str = Field(default="", description="For generate_sfx: detailed description of the sound, e.g. 'mystical Egyptian wind chime with reverb'")
    duration: float = Field(default=2.0, description="For generate_sfx: duration in seconds (0.5-10)")
    output_dir: str = Field(default="./output/audio", description="Save directory")
    gdd_context: str = Field(default="", description="For generate_brief: GDD context for themed audio design")


class SoundDesignTool(BaseTool):
    """
    AI-powered sound design for slot games.

    Two modes:
    - 'generate_brief': Creates a comprehensive audio design document with
      all required sounds, reference descriptions, and emotional targets.
    - 'generate_sfx': Generates actual sound effects via ElevenLabs Sound Effects API.
    - 'full': Brief + generates all core sounds.

    The brief covers: ambient loops, spin mechanics (start/stop/tick), win tiers
    (small/medium/big/mega), feature triggers, bonus music, anticipation builds,
    UI sounds, and adaptive audio specs.
    """

    name: str = "sound_design"
    description: str = (
        "Create game audio: generate a detailed audio design brief and/or produce actual "
        "AI-generated sound effects via ElevenLabs. Use 'generate_brief' for the full audio "
        "design document. Use 'generate_sfx' to create a specific sound effect. Use 'full' "
        "to create the brief AND generate all core sounds. Requires ELEVENLABS_API_KEY for "
        "sound generation."
    )
    args_schema: type[BaseModel] = SoundDesignInput

    # Core sounds every slot needs
    CORE_SOUNDS: ClassVar[dict] = {
        "spin_start": "Short mechanical whoosh, reels beginning to spin, slight metallic click",
        "reel_tick": "Subtle tick as each symbol passes, rhythmic, satisfying",
        "spin_stop": "Reels stopping one by one, solid thunk, decreasing tempo",
        "win_small": "Brief cheerful chime, coins clinking, subtle and quick",
        "win_medium": "Ascending musical phrase, brighter chimes, moderate celebration",
        "win_big": "Dramatic fanfare, orchestral hit, coin cascade, excitement building",
        "win_mega": "Epic orchestral climax, massive coin shower, crowd cheering, triumphant horns",
        "scatter_land": "Mysterious resonant gong, magical shimmer, anticipation trigger",
        "bonus_trigger": "Explosive dramatic transition, cinematic impact, energy building to excitement",
        "free_spin_start": "Ethereal magical transition, atmosphere shift, new world opening",
        "anticipation": "Tension building drone, heartbeat rhythm, increasing intensity",
        "button_click": "Clean tactile click, satisfying haptic feedback",
        "ambient": "Theme-appropriate background atmosphere, subtle and loopable",
    }

    def _run(self, action: str, theme: str = "", sound_type: str = "", description: str = "",
             duration: float = 2.0, output_dir: str = "./output/audio",
             gdd_context: str = "") -> str:

        if action == "generate_brief":
            return self._generate_brief(theme, gdd_context, output_dir)
        elif action == "generate_sfx":
            return self._generate_sfx(theme, sound_type, description, duration, output_dir)
        elif action == "full":
            return self._generate_full(theme, gdd_context, output_dir)
        else:
            return json.dumps({"error": f"Unknown action: {action}. Use 'generate_brief', 'generate_sfx', or 'full'."})

    def _generate_brief(self, theme: str, gdd_context: str, output_dir: str) -> str:
        """Generate a comprehensive audio design document."""
        # Theme-specific audio direction
        theme_audio = self._get_theme_audio_profile(theme)

        brief = f"""# Audio Design Brief — {theme or 'Untitled Game'}
Generated by ARKAINBRAIN Sound Design Engine
Date: {datetime.now().strftime('%Y-%m-%d')}

## Audio Direction
**Theme:** {theme}
**Mood:** {theme_audio['mood']}
**Instruments:** {', '.join(theme_audio['instruments'])}
**Key Signature:** {theme_audio['key']}
**Tempo Range:** {theme_audio['tempo']}

## Core Sound Effects

### Spin Mechanics
| Sound | Duration | Description | Emotional Target |
|-------|----------|-------------|-----------------|
| Spin Start | 0.5s | {theme_audio['theme_prefix']} whoosh with mechanical undertone | Anticipation, energy |
| Reel Tick | 0.1s | Rhythmic tick per symbol, {theme_audio['theme_prefix']} character | Satisfaction, rhythm |
| Spin Stop (per reel) | 0.3s | Solid thunk with {theme_audio['theme_prefix']} resonance, pitched down for each subsequent reel | Resolution, weight |

### Win Tiers
| Tier | Duration | Description | Emotional Target |
|------|----------|-------------|-----------------|
| Small Win (3-10x) | 1.5s | {theme_audio['win_small']} | Pleasant surprise |
| Medium Win (10-50x) | 2.5s | {theme_audio['win_medium']} | Growing excitement |
| Big Win (50-500x) | 4.0s | {theme_audio['win_big']} | Triumph, euphoria |
| Mega Win (500x+) | 8.0s | {theme_audio['win_mega']} | Peak experience, awe |

### Feature Sounds
| Sound | Duration | Description | Emotional Target |
|-------|----------|-------------|-----------------|
| Scatter Land | 1.0s | {theme_audio['scatter']} | Anticipation spike |
| Bonus Trigger | 2.0s | {theme_audio['bonus_trigger']} | Maximum excitement |
| Free Spin Start | 2.0s | {theme_audio['free_spin']} | World transition |
| Anticipation Build | 3-6s | {theme_audio['anticipation']} | Tension, suspense |

### UI Sounds
| Sound | Duration | Description |
|-------|----------|-------------|
| Button Click | 0.1s | Clean {theme_audio['theme_prefix']} tactile click |
| Menu Open/Close | 0.3s | Subtle swoosh with {theme_audio['theme_prefix']} character |
| Bet Change | 0.15s | Pitched coin click, higher pitch = higher bet |
| Autoplay Toggle | 0.2s | Mechanical switch with confirmation tone |

### Ambient / Music
| Layer | Description | Loop Length |
|-------|-------------|-------------|
| Base Game Ambient | {theme_audio['ambient']} | 60-120s seamless loop |
| Feature Ambient | {theme_audio['feature_ambient']} | 30-60s seamless loop |
| Anticipation Underscore | Building tension drone | 10s, layerable |

## Adaptive Audio Specs
- **Win tier crossfade:** 0.5s between tiers, pitch-matched
- **Near-miss:** Subtle tension resolution (minor chord down) after near-win
- **Dry streak relief:** After 20+ no-win spins, slight ambient variation to maintain engagement
- **Mobile considerations:** All SFX audible without headphones at 50% volume
- **Compression:** -14 LUFS target for mobile, -16 LUFS for desktop

## Technical Requirements
- Format: MP3 320kbps + WAV 44.1kHz/16-bit
- Naming: {{game_slug}}_{{sound_type}}_v1.mp3
- Deliver: Separate stems for each layer
- Looping: Ambient must loop seamlessly (crossfade points marked)

{f"## GDD Context" + chr(10) + gdd_context[:2000] if gdd_context else ""}
"""

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        brief_path = Path(output_dir) / "audio_design_brief.md"
        brief_path.write_text(brief, encoding="utf-8")

        return json.dumps({
            "status": "success",
            "file_path": str(brief_path),
            "sounds_specified": len(self.CORE_SOUNDS),
            "theme_profile": theme_audio["mood"],
        }, indent=2)

    def _generate_sfx(self, theme: str, sound_type: str, description: str, duration: float, output_dir: str) -> str:
        """Generate a sound effect using ElevenLabs."""
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return json.dumps({
                "status": "skipped",
                "reason": "ELEVENLABS_API_KEY not set. Add it to .env to enable AI sound generation.",
                "sound_type": sound_type,
                "description": description,
            })

        try:
            import httpx

            # Build the prompt
            theme_audio = self._get_theme_audio_profile(theme)
            if not description:
                description = self.CORE_SOUNDS.get(sound_type, f"{theme_audio['theme_prefix']} game sound effect")

            full_prompt = f"{theme_audio['theme_prefix']} slot game {sound_type}: {description}"

            # Clamp duration
            duration = max(0.5, min(22.0, duration))

            response = httpx.post(
                "https://api.elevenlabs.io/v1/sound-generation",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": full_prompt,
                    "duration_seconds": duration,
                    "prompt_influence": 0.5,
                },
                timeout=30.0,
            )

            if response.status_code == 200:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                file_name = f"{sound_type or 'sfx'}_{re.sub(r'[^a-z0-9]+', '_', theme.lower())[:20]}.mp3"
                file_path = Path(output_dir) / file_name
                file_path.write_bytes(response.content)

                return json.dumps({
                    "status": "success",
                    "file_path": str(file_path),
                    "sound_type": sound_type,
                    "duration_seconds": duration,
                    "prompt": full_prompt,
                    "file_size_kb": round(file_path.stat().st_size / 1024, 1),
                }, indent=2)
            else:
                error_detail = ""
                try:
                    error_detail = response.json().get("detail", {}).get("message", response.text[:200])
                except Exception:
                    error_detail = response.text[:200]
                return json.dumps({
                    "status": "error",
                    "http_status": response.status_code,
                    "error": error_detail,
                    "sound_type": sound_type,
                })

        except Exception as e:
            return json.dumps({"status": "error", "error": str(e), "sound_type": sound_type})

    def _generate_full(self, theme: str, gdd_context: str, output_dir: str) -> str:
        """Generate brief + all core sound effects."""
        results = {"brief": None, "sounds": []}

        # Generate brief
        brief_result = json.loads(self._generate_brief(theme, gdd_context, output_dir))
        results["brief"] = brief_result

        # Generate each core sound
        theme_audio = self._get_theme_audio_profile(theme)
        durations = {
            "spin_start": 0.5, "reel_tick": 0.2, "spin_stop": 0.5,
            "win_small": 1.5, "win_medium": 2.5, "win_big": 4.0, "win_mega": 8.0,
            "scatter_land": 1.0, "bonus_trigger": 2.5, "free_spin_start": 2.0,
            "anticipation": 5.0, "button_click": 0.2, "ambient": 10.0,
        }

        for sound_type, default_desc in self.CORE_SOUNDS.items():
            dur = durations.get(sound_type, 2.0)
            sfx_result = json.loads(self._generate_sfx(theme, sound_type, default_desc, dur, output_dir))
            results["sounds"].append(sfx_result)

        success_count = sum(1 for s in results["sounds"] if s.get("status") == "success")
        return json.dumps({
            "status": "complete",
            "brief": brief_result.get("file_path", ""),
            "sounds_generated": success_count,
            "sounds_total": len(self.CORE_SOUNDS),
            "sounds": results["sounds"],
        }, indent=2)

    def _get_theme_audio_profile(self, theme: str) -> dict:
        """Return theme-specific audio direction."""
        theme_lower = theme.lower() if theme else ""
        profiles = {
            "egypt": {
                "mood": "Mystical, ancient, mysterious with golden opulence",
                "instruments": ["oud", "darbuka", "ney flute", "orchestral strings", "metal chimes"],
                "key": "D minor / Bb major", "tempo": "85-110 BPM",
                "theme_prefix": "Ancient Egyptian mystical",
                "win_small": "Golden coin chimes with soft oud melody",
                "win_medium": "Ascending darbuka rhythm with orchestral strings building",
                "win_big": "Full orchestral pharaoh fanfare with massive percussion and choral voices",
                "win_mega": "Epic cinematic pyramid revelation — thunderous drums, choral climax, gold cascade",
                "scatter": "Deep mystical gong with sand-like shimmer and whispered ancient chant",
                "bonus_trigger": "Tomb door grinding open with dramatic orchestral sting and energy burst",
                "free_spin": "Ethereal dimension shift — swirling sand, mystical portal opening",
                "anticipation": "Low darbuka heartbeat building with ney flute tension",
                "ambient": "Desert wind with distant oud melody, subtle golden chimes, temple atmosphere",
                "feature_ambient": "Inside the pyramid — reverberant, mystical, torch crackling, deeper instruments",
            },
            "chinese": {
                "mood": "Bold yet refined, ceremonial, auspicious with ancient mystery and rising fortune",
                "instruments": ["erhu", "guzheng", "dizi flute", "pipa", "ceremonial drums", "temple bells", "bronze gongs"],
                "key": "D pentatonic / G pentatonic", "tempo": "80-105 BPM",
                "theme_prefix": "Traditional Chinese ceremonial",
                "win_small": "Soft bronze bell with jade chime, gentle coin clink",
                "win_medium": "Ascending guzheng melody with growing drum rhythm and golden gong",
                "win_big": "Powerful temple drum hits with full orchestral Chinese fanfare, coin cascade",
                "win_mega": "Epic celestial revelation — massive gong, choral monks, thunderous drums, imperial fanfare",
                "scatter": "Deep temple gong with mystical shimmer and whispered blessing",
                "bonus_trigger": "Ceremonial drum roll with energy swell, shimmering golden transition",
                "free_spin": "Ethereal silk-like transition, guzheng arpeggio, celestial atmosphere shift",
                "anticipation": "Low ceremonial drum pulse building with distant dizi flute tension",
                "ambient": "Traditional Chinese temple atmosphere — gentle flute, distant drums, flowing water, wind chimes",
                "feature_ambient": "Imperial palace interior — deeper gongs, richer instruments, sacred energy",
            },
            "norse": {
                "mood": "Epic, powerful, mythological with northern coldness",
                "instruments": ["war drums", "hurdy-gurdy", "Nordic fiddle", "brass horns", "choral voices"],
                "key": "E minor / C minor", "tempo": "90-120 BPM",
                "theme_prefix": "Viking Norse epic",
                "win_small": "Shield clang with brief horn note",
                "win_medium": "Rising war drum rhythm with Nordic fiddle melody",
                "win_big": "Full Viking battle fanfare — massive drums, brass, choral warriors",
                "win_mega": "Ragnarok-level epic — thunder, choral crescendo, legendary horn call",
                "scatter": "Thor's hammer strike with electrical crackle and deep resonance",
                "bonus_trigger": "Bifrost bridge activation — massive energy build, dimensional shift",
                "free_spin": "Valhalla gates opening — ethereal choral transition, golden light",
                "anticipation": "War drums building tempo, breath of icy wind",
                "ambient": "Northern wind, distant war drums, ravens calling, crackling fire",
                "feature_ambient": "Valhalla hall — grand reverb, feasting sounds, heroic undertone",
            },
            "dragon": {
                "mood": "Fiery, powerful, majestic with eastern mysticism",
                "instruments": ["taiko drums", "shakuhachi", "orchestral brass", "choral ensemble", "fire crackling FX"],
                "key": "E minor / A minor", "tempo": "95-115 BPM",
                "theme_prefix": "Dragon fire epic",
                "win_small": "Sharp metallic scale chime with subtle fire crackle",
                "win_medium": "Rising taiko rhythm with brass swells and dragon roar undertone",
                "win_big": "Full dragon roar fanfare — massive drums, orchestral fire, metallic cascade",
                "win_mega": "Cataclysmic dragon awakening — earth-shaking drums, choral ascension, fire storm",
                "scatter": "Deep rumbling dragon breath with metallic shimmer",
                "bonus_trigger": "Dragon eye opening — massive bass impact, fire eruption, energy surge",
                "free_spin": "Dimensional rift opening — swirling energy, dragon wings, atmosphere shift",
                "anticipation": "Low rumbling heartbeat of the dragon, growing fire intensity",
                "ambient": "Volcanic cavern with distant dragon breath, metallic echoes, ember crackle",
                "feature_ambient": "Dragon's lair — deeper resonance, treasure chamber acoustics, fire glow",
            },
            "ocean": {
                "mood": "Mysterious, deep, aquatic with underwater wonder",
                "instruments": ["harp", "celesta", "glass harmonica", "strings", "whale calls", "water FX"],
                "key": "F major / D minor", "tempo": "70-95 BPM",
                "theme_prefix": "Deep ocean aquatic",
                "win_small": "Bubbling water chime with soft harp note",
                "win_medium": "Ascending harp arpeggio with growing underwater orchestral swell",
                "win_big": "Majestic ocean fanfare — whale call, full strings, pearl cascade, coral glow",
                "win_mega": "Legendary underwater kingdom reveal — massive wave, choral mermaids, treasure torrent",
                "scatter": "Deep submarine sonar ping with mystical underwater shimmer",
                "bonus_trigger": "Tidal surge — massive wave building, underwater kingdom gates opening",
                "free_spin": "Descent into the deep — pressure change, bioluminescent shimmer, atmosphere shift",
                "anticipation": "Heartbeat pulse with distant whale call, growing current",
                "ambient": "Underwater ambience — gentle currents, distant whale songs, bubbles, coral reef life",
                "feature_ambient": "Deep ocean palace — cavernous reverb, bioluminescent glow, ancient currents",
            },
            "irish": {
                "mood": "Lucky, cheerful, magical with Celtic mysticism",
                "instruments": ["tin whistle", "Celtic harp", "fiddle", "bodhran", "uilleann pipes", "accordion"],
                "key": "G major / E minor", "tempo": "100-130 BPM",
                "theme_prefix": "Irish Celtic lucky",
                "win_small": "Cheerful coin clink with tin whistle trill",
                "win_medium": "Rising Celtic fiddle melody with bodhran building",
                "win_big": "Full Celtic celebration — pipes, fiddle, bodhran, gold coin cascade, crowd cheering",
                "win_mega": "Legendary pot of gold — massive pipes fanfare, rainbow shimmer, epic Celtic crescendo",
                "scatter": "Mystical Celtic harp glissando with shamrock shimmer",
                "bonus_trigger": "Rainbow appearing — magical chime cascade, leprechaun laugh",
                "free_spin": "Enchanted forest portal — harp transition, fairy dust, magical atmosphere",
                "anticipation": "Bodhran heartbeat with whispered Celtic chant",
                "ambient": "Irish countryside — gentle rain, distant fiddle, bird song, rolling hills wind",
                "feature_ambient": "Enchanted fairy forest — deeper magic, crystal cave, ancient Celtic energy",
            },
            "fantasy": {
                "mood": "Magical, adventurous, epic with enchanted wonder",
                "instruments": ["full orchestra", "choir", "celesta", "French horns", "harps", "bells"],
                "key": "Bb major / G minor", "tempo": "85-110 BPM",
                "theme_prefix": "Epic fantasy magical",
                "win_small": "Sparkling crystal chime with soft celesta note",
                "win_medium": "Ascending orchestral phrase with magical shimmer building",
                "win_big": "Full epic fantasy fanfare — French horns, choral triumph, gem cascade",
                "win_mega": "Legendary quest complete — massive orchestral crescendo, choral voices, magical explosion",
                "scatter": "Ancient spell casting — mystical energy surge with deep resonance",
                "bonus_trigger": "Portal opening — massive energy vortex, dimensional shift, orchestral impact",
                "free_spin": "Enchanted realm transition — ethereal choral bridge, atmosphere transformation",
                "anticipation": "Mystical drone building with distant choir, rising magical energy",
                "ambient": "Enchanted kingdom — gentle wind, distant magic, crystal chimes, birdsong",
                "feature_ambient": "Ancient wizard tower — deeper magic, arcane energy, crystalline resonance",
            },
        }

        # Match theme to profile using keyword detection
        keyword_map = {
            "egypt": ["egypt", "pharaoh", "pyramid", "cleopatra", "horus", "ankh", "sphinx", "nile"],
            "chinese": ["chinese", "china", "dragon king", "monkey king", "jade", "emperor", "dynasty",
                       "fortune", "jin", "hou", "bao", "lunar", "zodiac", "panda", "koi", "lotus"],
            "norse": ["norse", "viking", "odin", "thor", "valhalla", "ragnarok", "mjolnir", "rune"],
            "dragon": ["dragon", "fire", "wyrm", "drake", "drago"],
            "ocean": ["ocean", "sea", "underwater", "mermaid", "poseidon", "atlantis", "aqua", "fish",
                     "coral", "pearl", "neptune", "pirate", "treasure"],
            "irish": ["irish", "celtic", "leprechaun", "shamrock", "clover", "rainbow", "lucky",
                     "emerald", "pot of gold"],
            "fantasy": ["fantasy", "wizard", "magic", "enchant", "fairy", "elf", "crystal",
                       "medieval", "castle", "quest", "legend"],
        }

        for profile_key, keywords in keyword_map.items():
            if any(kw in theme_lower for kw in keywords):
                return profiles[profile_key]

        # Default profile
        return {
            "mood": "Dynamic, exciting, premium casino atmosphere",
            "instruments": ["orchestral ensemble", "electronic synths", "percussion", "piano"],
            "key": "C major / A minor", "tempo": "100-120 BPM",
            "theme_prefix": f"{theme} themed" if theme else "Casino",
            "win_small": "Bright chime cascade with subtle celebration",
            "win_medium": "Ascending orchestral phrase with growing energy",
            "win_big": "Full orchestral triumph with percussion crescendo and coin shower",
            "win_mega": "Epic cinematic climax — full orchestra, choral voices, massive celebration",
            "scatter": "Mysterious resonant tone with magical shimmer",
            "bonus_trigger": "Dramatic cinematic impact with energy explosion",
            "free_spin": "Ethereal transition — atmosphere shift, new sonic world opening",
            "anticipation": "Building tension — low drone, heartbeat rhythm, rising pitch",
            "ambient": f"{theme} atmospheric background — subtle, immersive, loopable",
            "feature_ambient": f"Enhanced {theme} atmosphere — deeper, more intense, engaging",
        }


# ============================================================
# UPGRADE 15: Certification Path Planner
# ============================================================
# Maps the full certification journey: which test lab, which
# standards, timeline, estimated cost, submission requirements.

class CertPlanInput(BaseModel):
    target_markets: list[str] = Field(description="Target markets, e.g. ['UK', 'Malta', 'Ontario']")
    game_type: str = Field(default="video_slot", description="'video_slot', 'jackpot_slot', 'table_game', 'instant_win'")
    has_progressive_jackpot: bool = Field(default=False, description="Does the game have a progressive jackpot?")
    has_bonus_buy: bool = Field(default=False, description="Does the game have a bonus buy feature?")
    rtp: float = Field(default=96.0, description="Game RTP percentage")
    target_launch_date: str = Field(default="", description="Desired launch date, e.g. '2026-06'")


class CertificationPlannerTool(BaseTool):
    """
    Plans the full certification path for a slot game across target markets.

    Returns: recommended test lab, applicable standards, estimated timeline,
    estimated cost, submission requirements, and a step-by-step checklist.
    """

    name: str = "certification_planner"
    description: str = (
        "Plan the full certification path for a game across target markets. Returns: "
        "recommended test lab, applicable GLI/BMM standards, estimated timeline and cost, "
        "submission documentation requirements, and step-by-step checklist. Use AFTER "
        "the game design is complete to plan the road to market."
    )
    args_schema: type[BaseModel] = CertPlanInput

    CERT_DATABASE: ClassVar[dict] = {
        "UK": {
            "regulator": "UK Gambling Commission (UKGC)",
            "standards": ["GLI-11 v3.0", "Remote Gambling & Software Technical Standards (RTS)"],
            "test_labs": ["GLI", "BMM Testlabs", "eCOGRA", "NMi Gaming"],
            "typical_timeline_weeks": 8,
            "estimated_cost_range": "$15,000 - $30,000",
            "requirements": [
                "Full game mathematics report with 10M+ spin simulation",
                "RNG certification (if not using pre-certified RNG)",
                "Responsible gambling feature compliance (reality checks, session limits)",
                "Game rules clearly displayed",
                "Return to Player displayed to at least 2 decimal places",
                "No bonus buy feature (banned since Oct 2021)",
                "No content appealing primarily to under-18s",
                "Server-based game outcome determination",
                "Full audit trail capability",
            ],
            "notes": "UK is the most scrutinized market. Plan extra time for RTS compliance review.",
        },
        "Malta": {
            "regulator": "Malta Gaming Authority (MGA)",
            "standards": ["GLI-11 v3.0", "MGA Technical Standards"],
            "test_labs": ["GLI", "BMM Testlabs", "iTech Labs"],
            "typical_timeline_weeks": 6,
            "estimated_cost_range": "$10,000 - $20,000",
            "requirements": [
                "RNG certification",
                "Game rules and paytable display",
                "RTP within declared range",
                "Responsible gambling messaging",
                "Player history accessible",
                "Multi-currency support",
            ],
            "notes": "Slightly faster than UK. Often done in parallel.",
        },
        "Ontario": {
            "regulator": "Alcohol and Gaming Commission of Ontario (AGCO) / iGaming Ontario (iGO)",
            "standards": ["GLI-11", "AGCO iGaming Standards"],
            "test_labs": ["GLI", "BMM Testlabs", "iTech Labs", "Gaming Associates"],
            "typical_timeline_weeks": 8,
            "estimated_cost_range": "$12,000 - $25,000",
            "requirements": [
                "Full math report with RTP verification",
                "Responsible gambling tools (deposit limits, self-exclusion integration)",
                "Play break reminders",
                "Game rules in English and French",
                "Geolocation compliance",
                "Age verification integration",
            ],
            "notes": "French language support required. Strong RG focus.",
        },
        "New Jersey": {
            "regulator": "NJ Division of Gaming Enforcement (DGE)",
            "standards": ["GLI-11", "NJ DGE Technical Standards"],
            "test_labs": ["GLI", "BMM Testlabs"],
            "typical_timeline_weeks": 10,
            "estimated_cost_range": "$20,000 - $40,000",
            "requirements": [
                "Full math certification with 10M+ spin sim",
                "Geolocation system integration (GeoComply or similar)",
                "Age verification (21+ in NJ)",
                "Responsible gambling features",
                "Server location within NJ or approved jurisdiction",
                "Operator-specific integration testing",
            ],
            "notes": "Most expensive US market. Geolocation adds complexity.",
        },
        "Sweden": {
            "regulator": "Spelinspektionen",
            "standards": ["GLI-11", "Swedish Gaming Act requirements"],
            "test_labs": ["GLI", "BMM Testlabs"],
            "typical_timeline_weeks": 8,
            "estimated_cost_range": "$12,000 - $22,000",
            "requirements": [
                "No bonus buy feature",
                "No autoplay feature",
                "Deposit limit system",
                "Session time limits",
                "Panic button (immediate self-exclusion)",
                "RTP display",
                "Swedish language support",
            ],
            "notes": "Very strict feature restrictions. Bonus buy AND autoplay both banned.",
        },
        "Curacao": {
            "regulator": "Curacao Gaming Control Board",
            "standards": ["GLI-11 (recommended, not required)", "Curacao Technical Standards"],
            "test_labs": ["GLI", "iTech Labs"],
            "typical_timeline_weeks": 4,
            "estimated_cost_range": "$5,000 - $12,000",
            "requirements": [
                "Basic RNG certification",
                "Game rules display",
                "Responsible gambling messaging",
                "Basic player protection tools",
            ],
            "notes": "Fastest and cheapest. New regulations tightening requirements in 2025+.",
        },
    }

    def _run(self, target_markets: list[str], game_type: str = "video_slot",
             has_progressive_jackpot: bool = False, has_bonus_buy: bool = False,
             rtp: float = 96.0, target_launch_date: str = "") -> str:

        plan = {
            "game_type": game_type,
            "rtp": rtp,
            "target_markets": target_markets,
            "per_market": {},
            "recommended_lab": None,
            "total_timeline": {},
            "total_cost": {},
            "critical_flags": [],
            "submission_checklist": [],
            "optimization_tips": [],
        }

        total_min_cost = 0
        total_max_cost = 0
        max_weeks = 0
        lab_frequency = {}

        for market in target_markets:
            cert = self.CERT_DATABASE.get(market)
            if cert:
                # Parse cost range
                cost_str = cert["estimated_cost_range"]
                costs = re.findall(r'\$([\d,]+)', cost_str)
                min_cost = int(costs[0].replace(",", "")) if costs else 10000
                max_cost = int(costs[1].replace(",", "")) if len(costs) > 1 else min_cost

                # Add jackpot surcharge
                if has_progressive_jackpot:
                    min_cost = int(min_cost * 1.3)
                    max_cost = int(max_cost * 1.3)

                timeline = cert["typical_timeline_weeks"]
                if has_progressive_jackpot:
                    timeline += 2

                plan["per_market"][market] = {
                    "regulator": cert["regulator"],
                    "standards": cert["standards"],
                    "recommended_labs": cert["test_labs"],
                    "timeline_weeks": timeline,
                    "cost_range": f"${min_cost:,} - ${max_cost:,}",
                    "requirements": cert["requirements"],
                    "notes": cert["notes"],
                }

                total_min_cost += min_cost
                total_max_cost += max_cost
                max_weeks = max(max_weeks, timeline)

                for lab in cert["test_labs"]:
                    lab_frequency[lab] = lab_frequency.get(lab, 0) + 1

                # Check for feature conflicts
                if has_bonus_buy and market in ("UK", "Sweden", "Spain"):
                    plan["critical_flags"].append(
                        f"BLOCKER: Bonus buy is BANNED in {market}. Remove the feature "
                        f"or create a market-specific build without it."
                    )
            else:
                plan["per_market"][market] = {
                    "status": "unknown_market",
                    "note": f"No certification data for {market}. Research required.",
                }

        # Recommend the lab that covers the most markets
        if lab_frequency:
            best_lab = max(lab_frequency.items(), key=lambda x: x[1])
            plan["recommended_lab"] = {
                "name": best_lab[0],
                "covers_markets": best_lab[1],
                "reason": f"Covers {best_lab[1]}/{len(target_markets)} target markets — minimizes multi-lab coordination.",
            }

        # Timeline calculation
        # Parallel testing saves time vs sequential
        parallel_weeks = max_weeks + 2  # Allow 2 weeks for lab setup/coordination
        sequential_weeks = sum(
            plan["per_market"].get(m, {}).get("timeline_weeks", 8) for m in target_markets
        )
        plan["total_timeline"] = {
            "parallel_testing_weeks": parallel_weeks,
            "sequential_testing_weeks": sequential_weeks,
            "recommendation": "parallel",
            "note": f"Parallel testing with {plan['recommended_lab']['name'] if plan.get('recommended_lab') else 'GLI'} saves ~{sequential_weeks - parallel_weeks} weeks.",
        }

        if target_launch_date:
            plan["total_timeline"]["target_launch"] = target_launch_date
            plan["total_timeline"]["start_testing_by"] = f"~{parallel_weeks} weeks before {target_launch_date}"

        plan["total_cost"] = {
            "estimated_range": f"${total_min_cost:,} - ${total_max_cost:,}",
            "per_market_breakdown": {
                m: plan["per_market"][m].get("cost_range", "unknown")
                for m in target_markets if m in plan["per_market"]
            },
            "note": "Costs may be lower if using a single lab for multiple markets (volume discount).",
        }

        # Submission checklist
        all_requirements = set()
        for m in target_markets:
            reqs = plan["per_market"].get(m, {}).get("requirements", [])
            all_requirements.update(reqs)

        plan["submission_checklist"] = [
            "Game mathematics report (10M+ spin simulation with RTP, hit freq, volatility, max win)",
            "Paytable specification document",
            "Game rules (all supported languages)",
            "RNG certification or pre-certified RNG documentation",
            "Responsible gambling features documentation",
            "Server architecture and audit trail documentation",
            "Test environment access (staging server)",
            "Source code access (some labs require)",
        ] + sorted(all_requirements)

        # Optimization tips
        plan["optimization_tips"] = [
            "Submit to all markets simultaneously with the same lab to reduce total timeline.",
            "Pre-certify your RNG separately — it speeds up individual game submissions.",
            "Build market-specific feature toggles (e.g., bonus buy ON/OFF) rather than separate builds.",
            "Prepare the math report FIRST — it's the longest review item for every lab.",
            "Use the recommended lab's template for math reports to avoid back-and-forth.",
        ]

        if has_progressive_jackpot:
            plan["optimization_tips"].append(
                "Progressive jackpot adds ~2 weeks and ~30% cost. Ensure jackpot contribution "
                "rate documentation is ready. Some labs require separate jackpot system certification."
            )

        return json.dumps(plan, indent=2)
