"""
ARKAINBRAIN — Audio Middleware Export (Phase 10)

Generates FMOD Studio or Wwise project skeletons with:
- Event sheets mapped to all slot game events
- Bus hierarchy (SFX, Music, Ambience, UI)
- RTPC parameter definitions (win_intensity, reel_index, feature_state)
- Placeholder sound assignments
- Integration guide
"""

import json
import zipfile
from datetime import datetime
from pathlib import Path

# ─── Slot Game Audio Events ───

SLOT_AUDIO_EVENTS = [
    {"id": "ui_spin_click", "type": "one_shot", "bus": "SFX", "priority": "high",
     "description": "Player taps spin button"},
    {"id": "ui_button_hover", "type": "one_shot", "bus": "UI", "priority": "low",
     "description": "Mouse hover over buttons"},
    {"id": "ui_bet_change", "type": "one_shot", "bus": "UI", "priority": "medium",
     "description": "Bet amount changed"},
    {"id": "reel_spin_loop", "type": "loop", "bus": "SFX",
     "parameters": ["reel_index"], "description": "Continuous reel spinning sound"},
    {"id": "reel_stop_1", "type": "one_shot", "bus": "SFX", "variations": 3,
     "description": "Reel 1 stops"},
    {"id": "reel_stop_2", "type": "one_shot", "bus": "SFX", "variations": 3,
     "description": "Reel 2 stops"},
    {"id": "reel_stop_3", "type": "one_shot", "bus": "SFX", "variations": 3,
     "description": "Reel 3 stops"},
    {"id": "reel_stop_4", "type": "one_shot", "bus": "SFX", "variations": 3,
     "description": "Reel 4 stops"},
    {"id": "reel_stop_5", "type": "one_shot", "bus": "SFX", "variations": 3,
     "description": "Reel 5 stops"},
    {"id": "reel_anticipation", "type": "loop", "bus": "SFX",
     "parameters": ["anticipation_level"], "fade_in": 0.5,
     "description": "Building anticipation before last reel stops"},
    {"id": "win_small", "type": "one_shot", "bus": "Music", "intensity": 0.3,
     "description": "Small win celebration (< 5x bet)"},
    {"id": "win_medium", "type": "one_shot", "bus": "Music", "intensity": 0.5,
     "description": "Medium win celebration (5-20x bet)"},
    {"id": "win_big", "type": "layered", "bus": "Music", "intensity": 0.8,
     "layers": ["base", "excitement"], "description": "Big win (20-100x bet)"},
    {"id": "win_mega", "type": "layered", "bus": "Music", "intensity": 1.0,
     "layers": ["base", "excitement", "epic"], "description": "Mega win (> 100x bet)"},
    {"id": "win_line_highlight", "type": "one_shot", "bus": "SFX",
     "parameters": ["win_amount"], "description": "Payline highlight flash"},
    {"id": "coins_cascade", "type": "loop", "bus": "SFX",
     "parameters": ["coin_rate"], "description": "Coins counting up during win display"},
    {"id": "free_spin_trigger", "type": "stinger", "bus": "Music",
     "description": "Free spins feature triggered (scatter lands)"},
    {"id": "free_spin_ambient", "type": "loop", "bus": "Ambience",
     "description": "Background ambience during free spins mode"},
    {"id": "free_spin_end", "type": "one_shot", "bus": "Music",
     "description": "Free spins mode ends, return to base game"},
    {"id": "bonus_trigger", "type": "stinger", "bus": "Music",
     "description": "Bonus feature triggered"},
    {"id": "bonus_anticipation", "type": "loop", "bus": "Music",
     "fade_in": 2.0, "description": "Building tension during bonus anticipation"},
    {"id": "bonus_pick", "type": "one_shot", "bus": "SFX",
     "description": "Player picks an item in pick-and-click bonus"},
    {"id": "bonus_reveal", "type": "one_shot", "bus": "SFX",
     "parameters": ["reveal_value"], "description": "Bonus item revealed"},
    {"id": "wild_land", "type": "one_shot", "bus": "SFX",
     "description": "Wild symbol lands on reel"},
    {"id": "scatter_land", "type": "one_shot", "bus": "SFX",
     "variations": 3, "description": "Scatter symbol lands (increasing intensity per scatter)"},
    {"id": "multiplier_increase", "type": "one_shot", "bus": "SFX",
     "parameters": ["multiplier_value"], "description": "Multiplier increases"},
    {"id": "cascade_break", "type": "one_shot", "bus": "SFX",
     "description": "Symbols break during cascade/tumble feature"},
    {"id": "cascade_fill", "type": "one_shot", "bus": "SFX",
     "description": "New symbols fill in after cascade"},
    {"id": "base_game_music", "type": "loop", "bus": "Music",
     "description": "Main base game background music"},
    {"id": "idle_ambient", "type": "loop", "bus": "Ambience",
     "description": "Ambient sounds when game is idle"},
]

# ─── Bus Hierarchy ───

BUS_HIERARCHY = {
    "Master": {
        "Music": {"volume": 0.7, "description": "Background music and win celebrations"},
        "SFX": {"volume": 0.9, "description": "Sound effects: reels, buttons, symbols"},
        "Ambience": {"volume": 0.4, "description": "Background ambient sounds"},
        "UI": {"volume": 0.8, "description": "UI interaction sounds"},
    }
}

# ─── RTPC Parameters ───

RTPC_PARAMETERS = [
    {"name": "win_intensity", "min": 0.0, "max": 1.0, "default": 0.0,
     "description": "Win size normalized (0=no win, 1=max win)"},
    {"name": "reel_index", "min": 0, "max": 4, "default": 0,
     "description": "Which reel is active (0-4 for 5 reels)"},
    {"name": "anticipation_level", "min": 0.0, "max": 1.0, "default": 0.0,
     "description": "Anticipation building intensity"},
    {"name": "feature_state", "min": 0, "max": 3, "default": 0,
     "description": "0=base, 1=free_spins, 2=bonus, 3=gamble"},
    {"name": "multiplier_value", "min": 1, "max": 100, "default": 1,
     "description": "Current active multiplier"},
    {"name": "coin_rate", "min": 0.0, "max": 1.0, "default": 0.5,
     "description": "Coin counting speed during win display"},
]


def generate_audio_package(engine: str = "fmod", output_dir: str = "",
                           game_title: str = "Untitled Slot",
                           config: dict = None, **kwargs) -> str:
    """Generate FMOD or Wwise audio project skeleton."""
    od = Path(output_dir)
    export_dir = od / "09_export"
    export_dir.mkdir(parents=True, exist_ok=True)

    slug = game_title.lower().replace(" ", "_").replace("'", "")[:30]
    zip_path = export_dir / f"{slug}_{engine}_audio.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        pfx = f"{slug}_{engine}"

        if engine == "fmod":
            _build_fmod_project(zf, pfx, game_title, config or {})
        else:
            _build_wwise_project(zf, pfx, game_title, config or {})

        # Common: event manifest JSON
        zf.writestr(f"{pfx}/audio_events.json", json.dumps({
            "events": SLOT_AUDIO_EVENTS,
            "buses": BUS_HIERARCHY,
            "parameters": RTPC_PARAMETERS,
            "game_title": game_title,
            "engine": engine,
            "generated_at": datetime.now().isoformat(),
        }, indent=2))

        # Integration guide
        zf.writestr(f"{pfx}/INTEGRATION_GUIDE.md", _integration_guide(engine, game_title))

        # Placeholder audio directories
        for bus in ["sfx", "music", "ambience", "ui"]:
            zf.writestr(f"{pfx}/audio/{bus}/.gitkeep", "")

    return str(zip_path)


def _build_fmod_project(zf, pfx, title, config):
    """Generate FMOD Studio project skeleton (.fspro XML)."""
    events_xml = ""
    for evt in SLOT_AUDIO_EVENTS:
        params_xml = ""
        for p in evt.get("parameters", []):
            params_xml += f'        <parameter name="{p}"/>\n'
        layers_xml = ""
        for layer in evt.get("layers", []):
            layers_xml += f'        <layer name="{layer}"/>\n'

        events_xml += f'''    <event name="{evt["id"]}" type="{evt["type"]}" bus="{evt["bus"]}">
      <description>{evt["description"]}</description>
{params_xml}{layers_xml}    </event>
'''

    buses_xml = ""
    for parent, children in BUS_HIERARCHY.items():
        buses_xml += f'    <bus name="{parent}">\n'
        for name, props in children.items():
            buses_xml += f'      <bus name="{name}" volume="{props["volume"]}"/>\n'
        buses_xml += f'    </bus>\n'

    params_xml = ""
    for p in RTPC_PARAMETERS:
        params_xml += f'    <parameter name="{p["name"]}" min="{p["min"]}" max="{p["max"]}" default="{p["default"]}"/>\n'

    fspro = f'''<?xml version="1.0" encoding="utf-8"?>
<!-- FMOD Studio Project — Auto-generated by ARKAINBRAIN Phase 10 -->
<!-- Game: {title} -->
<!-- Generated: {datetime.now().isoformat()} -->
<!-- NOTE: This is a skeleton project. Import into FMOD Studio and add audio assets. -->
<fmod_studio_project version="2.02">
  <metadata>
    <name>{title}</name>
    <generator>ARKAINBRAIN Phase 10</generator>
  </metadata>
  <buses>
{buses_xml}  </buses>
  <events>
{events_xml}  </events>
  <parameters>
{params_xml}  </parameters>
</fmod_studio_project>
'''
    zf.writestr(f"{pfx}/{title.replace(' ', '_')}.fspro", fspro)

    # Event sheet CSV (for quick overview)
    csv_lines = ["Event ID,Type,Bus,Description"]
    for evt in SLOT_AUDIO_EVENTS:
        csv_lines.append(f'{evt["id"]},{evt["type"]},{evt["bus"]},"{evt["description"]}"')
    zf.writestr(f"{pfx}/event_sheet.csv", "\n".join(csv_lines))


def _build_wwise_project(zf, pfx, title, config):
    """Generate Wwise project skeleton (.wproj XML)."""
    events_xml = ""
    for evt in SLOT_AUDIO_EVENTS:
        events_xml += f'''      <Event Name="{evt["id"]}" ID="{hash(evt["id"]) & 0xFFFFFFFF}">
        <PropertyList>
          <Property Name="EventType" Type="string" Value="{evt["type"]}"/>
          <Property Name="Bus" Type="string" Value="{evt["bus"]}"/>
        </PropertyList>
      </Event>
'''

    rtpc_xml = ""
    for p in RTPC_PARAMETERS:
        rtpc_xml += f'''      <GameParameter Name="{p["name"]}" ID="{hash(p["name"]) & 0xFFFFFFFF}">
        <PropertyList>
          <Property Name="RangeMin" Type="Real64" Value="{p["min"]}"/>
          <Property Name="RangeMax" Type="Real64" Value="{p["max"]}"/>
          <Property Name="InitialValue" Type="Real64" Value="{p["default"]}"/>
        </PropertyList>
      </GameParameter>
'''

    wproj = f'''<?xml version="1.0" encoding="utf-8"?>
<!-- Wwise Project — Auto-generated by ARKAINBRAIN Phase 10 -->
<WwiseDocument Type="WorkUnit" ID="{{00000000-0000-0000-0000-000000000000}}">
  <AudioObjects>
    <WorkUnit Name="{title}" ID="{{00000001-0000-0000-0000-000000000000}}" PersistMode="Standalone">
      <ChildrenList>
{events_xml}      </ChildrenList>
    </WorkUnit>
  </AudioObjects>
  <GameParameters>
    <WorkUnit Name="Game Parameters" ID="{{00000002-0000-0000-0000-000000000000}}">
      <ChildrenList>
{rtpc_xml}      </ChildrenList>
    </WorkUnit>
  </GameParameters>
</WwiseDocument>
'''
    zf.writestr(f"{pfx}/{title.replace(' ', '_')}.wproj", wproj)

    # SoundBank definition
    zf.writestr(f"{pfx}/SoundBanks/SlotGame.json", json.dumps({
        "soundbanks": [
            {"name": "SFX_Bank", "events": [e["id"] for e in SLOT_AUDIO_EVENTS if e["bus"] == "SFX"]},
            {"name": "Music_Bank", "events": [e["id"] for e in SLOT_AUDIO_EVENTS if e["bus"] == "Music"]},
            {"name": "Ambience_Bank", "events": [e["id"] for e in SLOT_AUDIO_EVENTS if e["bus"] == "Ambience"]},
            {"name": "UI_Bank", "events": [e["id"] for e in SLOT_AUDIO_EVENTS if e["bus"] == "UI"]},
        ]
    }, indent=2))


def _integration_guide(engine, title):
    tool = "FMOD Studio" if engine == "fmod" else "Audiokinetic Wwise"
    return f"""# {title} — {tool} Audio Integration Guide
Generated by ARKAINBRAIN Phase 10 on {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Overview
This package contains a {tool} project skeleton with **{len(SLOT_AUDIO_EVENTS)} audio events**
pre-mapped to slot game actions, **{len(RTPC_PARAMETERS)} RTPC parameters** for dynamic audio,
and a **4-bus hierarchy** (Music, SFX, Ambience, UI).

## Audio Events ({len(SLOT_AUDIO_EVENTS)} total)
See `audio_events.json` for the complete event manifest with descriptions.

### Key Events
- **Spin cycle**: ui_spin_click → reel_spin_loop → reel_stop_1..5 → win_*
- **Win tiers**: win_small (< 5x) → win_medium (5-20x) → win_big (20-100x) → win_mega (100x+)
- **Features**: free_spin_trigger → free_spin_ambient → free_spin_end
- **Bonus**: bonus_trigger → bonus_anticipation → bonus_pick → bonus_reveal

## RTPC Parameters
| Parameter | Range | Description |
|-----------|-------|-------------|
| win_intensity | 0.0 — 1.0 | Normalized win size for dynamic mixing |
| reel_index | 0 — 4 | Active reel for positional audio |
| anticipation_level | 0.0 — 1.0 | Anticipation build intensity |
| feature_state | 0 — 3 | Base/FreeSpins/Bonus/Gamble |
| multiplier_value | 1 — 100 | Current multiplier for escalating audio |
| coin_rate | 0.0 — 1.0 | Win counter speed |

## Quick Start
1. Open the .{'fspro' if engine == 'fmod' else 'wproj'} file in {tool}
2. Add your audio assets to the placeholder directories in `audio/`
3. Assign audio files to each event
4. Configure RTPC curves for dynamic parameters
5. Build sound banks and integrate with your game engine

## Bus Hierarchy
```
Master
├── Music (vol: 0.7) — Background music, win celebrations
├── SFX (vol: 0.9) — Reels, buttons, symbols
├── Ambience (vol: 0.4) — Background ambient sounds
└── UI (vol: 0.8) — UI interaction sounds
```
"""
