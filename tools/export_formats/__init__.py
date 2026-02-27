"""
ARKAINBRAIN — Export Format Plugins (Phase 10)

Production-grade export generators for engine packages, audio middleware,
sprite atlases, and aggregator provider SDKs.
"""

from tools.export_formats.unity import generate_unity_package
from tools.export_formats.godot import generate_godot_package
from tools.export_formats.audio import generate_audio_package
from tools.export_formats.atlas import generate_atlas_package
from tools.export_formats.provider import generate_provider_package

EXPORT_FORMATS = {
    "unity": {
        "label": "Unity Package",
        "icon": "🎮",
        "description": "Full .unitypackage with ScriptableObjects, prefab scaffolds, symbol atlas metadata",
        "generator": generate_unity_package,
        "extension": ".zip",
    },
    "godot": {
        "label": "Godot 4 Project",
        "icon": "🤖",
        "description": "Godot 4 project scaffold: .tscn scenes, .gd scripts, reel data, export presets",
        "generator": generate_godot_package,
        "extension": ".zip",
    },
    "audio_fmod": {
        "label": "FMOD Studio Project",
        "icon": "🔊",
        "description": "FMOD Studio .fspro skeleton with event sheets mapped to all game events",
        "generator": lambda **kw: generate_audio_package(engine="fmod", **kw),
        "extension": ".zip",
    },
    "audio_wwise": {
        "label": "Wwise Project",
        "icon": "🎧",
        "description": "Audiokinetic Wwise .wproj with event/bus hierarchy and RTPC mappings",
        "generator": lambda **kw: generate_audio_package(engine="wwise", **kw),
        "extension": ".zip",
    },
    "atlas": {
        "label": "Sprite Atlas",
        "icon": "🖼️",
        "description": "TexturePacker JSON atlas + animation metadata (idle/win/anticipation frames)",
        "generator": generate_atlas_package,
        "extension": ".zip",
    },
    "provider_gig": {
        "label": "GIG / iSoftBet SDK",
        "icon": "🏢",
        "description": "GIG/iSoftBet aggregator integration config with game manifest and RGS hooks",
        "generator": lambda **kw: generate_provider_package(provider="gig", **kw),
        "extension": ".zip",
    },
    "provider_relax": {
        "label": "Relax Gaming SDK",
        "icon": "🏢",
        "description": "Relax Gaming Silver Bullet integration config and game descriptor",
        "generator": lambda **kw: generate_provider_package(provider="relax", **kw),
        "extension": ".zip",
    },
    "provider_generic": {
        "label": "Generic Provider SDK",
        "icon": "📦",
        "description": "OpenAPI-compliant JSON bundle with versioned game config for any aggregator",
        "generator": lambda **kw: generate_provider_package(provider="generic", **kw),
        "extension": ".zip",
    },
}
