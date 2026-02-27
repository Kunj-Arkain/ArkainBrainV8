"""
ARKAINBRAIN — Sprite Atlas Export (Phase 10)

Generates TexturePacker-compatible sprite atlas metadata with:
- Frame definitions for each symbol (idle, win, anticipation)
- Animation sequences with timing
- Background layer separation metadata
- Atlas packing configuration
"""

import json
import zipfile
from datetime import datetime
from pathlib import Path


# ─── Animation Frame Definitions ───

SYMBOL_ANIMATIONS = {
    "idle": {"frames": 1, "fps": 0, "loop": False, "description": "Static idle state"},
    "win_small": {"frames": 8, "fps": 12, "loop": True, "description": "Small win celebration loop"},
    "win_big": {"frames": 12, "fps": 15, "loop": True, "description": "Big win celebration with particles"},
    "anticipation": {"frames": 6, "fps": 10, "loop": True, "description": "Anticipation glow/pulse before win reveal"},
    "land": {"frames": 4, "fps": 24, "loop": False, "description": "Symbol landing impact on reel stop"},
    "scatter_trigger": {"frames": 10, "fps": 15, "loop": False, "description": "Scatter activation burst"},
}

BACKGROUND_LAYERS = [
    {"name": "bg_base", "depth": 0, "parallax": 1.0, "description": "Static base background"},
    {"name": "bg_middle", "depth": 1, "parallax": 0.8, "description": "Middle parallax layer (clouds, particles)"},
    {"name": "bg_foreground", "depth": 2, "parallax": 0.5, "description": "Foreground decorative elements"},
    {"name": "bg_overlay", "depth": 3, "parallax": 0.0, "description": "Fixed overlay (vignette, frame)"},
    {"name": "bg_feature", "depth": 1, "parallax": 0.8, "description": "Feature-mode background swap"},
]


def generate_atlas_package(output_dir: str, game_title: str, config: dict,
                           symbols: list, **kwargs) -> str:
    """Generate sprite atlas metadata package."""
    od = Path(output_dir)
    export_dir = od / "09_export"
    export_dir.mkdir(parents=True, exist_ok=True)

    slug = game_title.lower().replace(" ", "_").replace("'", "")[:30]
    zip_path = export_dir / f"{slug}_atlas.zip"

    cols = config.get("grid_cols", 5)
    rows = config.get("grid_rows", 3)

    # Calculate symbol cell size based on common atlas sizes
    cell_w = 256
    cell_h = 256

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        pfx = f"{slug}_atlas"

        # ── TexturePacker JSON (symbols atlas) ──
        frames = {}
        animations = {}
        frame_idx = 0

        for sym in symbols:
            name = sym.get("name", "Unknown")
            slug_s = name.lower().replace(" ", "_")

            for anim_name, anim_info in SYMBOL_ANIMATIONS.items():
                num_frames = anim_info["frames"]
                anim_frames = []

                for f_idx in range(num_frames):
                    frame_name = f"{slug_s}_{anim_name}_{f_idx:03d}"
                    # Calculate atlas position (grid layout)
                    grid_x = frame_idx % 8
                    grid_y = frame_idx // 8

                    frames[frame_name] = {
                        "frame": {"x": grid_x * cell_w, "y": grid_y * cell_h,
                                  "w": cell_w, "h": cell_h},
                        "rotated": False,
                        "trimmed": False,
                        "spriteSourceSize": {"x": 0, "y": 0, "w": cell_w, "h": cell_h},
                        "sourceSize": {"w": cell_w, "h": cell_h},
                        "pivot": {"x": 0.5, "y": 0.5},
                    }
                    anim_frames.append(frame_name)
                    frame_idx += 1

                if num_frames > 1:
                    animations[f"{slug_s}_{anim_name}"] = {
                        "frames": anim_frames,
                        "fps": anim_info["fps"],
                        "loop": anim_info["loop"],
                    }

        # Atlas metadata columns
        atlas_cols = 8
        atlas_rows = (frame_idx + atlas_cols - 1) // atlas_cols
        atlas_w = atlas_cols * cell_w
        atlas_h = atlas_rows * cell_h

        tp_json = {
            "frames": frames,
            "animations": animations,
            "meta": {
                "app": "ARKAINBRAIN Atlas Generator",
                "version": "10.0",
                "image": f"{slug}_symbols.png",
                "format": "RGBA8888",
                "size": {"w": atlas_w, "h": atlas_h},
                "scale": 1,
                "smartupdate": datetime.now().isoformat(),
            }
        }
        zf.writestr(f"{pfx}/symbols_atlas.json", json.dumps(tp_json, indent=2))

        # ── Animation metadata ──
        anim_metadata = {
            "game_title": game_title,
            "cell_size": {"w": cell_w, "h": cell_h},
            "symbols": [],
        }

        for sym in symbols:
            name = sym.get("name", "Unknown")
            slug_s = name.lower().replace(" ", "_")
            sym_anims = {}
            for anim_name, anim_info in SYMBOL_ANIMATIONS.items():
                sym_anims[anim_name] = {
                    "frames": anim_info["frames"],
                    "fps": anim_info["fps"],
                    "loop": anim_info["loop"],
                    "frame_prefix": f"{slug_s}_{anim_name}_",
                    "description": anim_info["description"],
                }
            anim_metadata["symbols"].append({
                "name": name,
                "slug": slug_s,
                "type": _symbol_type(name),
                "animations": sym_anims,
            })
        zf.writestr(f"{pfx}/animation_metadata.json", json.dumps(anim_metadata, indent=2))

        # ── Background layers metadata ──
        bg_meta = {
            "game_title": game_title,
            "viewport": {"w": 1920, "h": 1080},
            "layers": BACKGROUND_LAYERS,
            "feature_backgrounds": {
                "base_game": "bg_base",
                "free_spins": "bg_feature",
                "bonus": "bg_feature",
            },
        }
        zf.writestr(f"{pfx}/background_layers.json", json.dumps(bg_meta, indent=2))

        # ── Atlas packing config (for TexturePacker CLI) ──
        tp_config = {
            "algorithm": "MaxRects",
            "maxSize": {"w": 4096, "h": 4096},
            "padding": 2,
            "allowRotation": False,
            "trimMode": "Trim",
            "extrude": 1,
            "format": "json-array",
            "pngOptLevel": 7,
            "textureFormat": "png",
            "premultiplyAlpha": False,
        }
        zf.writestr(f"{pfx}/texturepacker_config.json", json.dumps(tp_config, indent=2))

        # ── Reel layout metadata ──
        reel_layout = {
            "grid": {"cols": cols, "rows": rows},
            "cell_size": {"w": cell_w, "h": cell_h},
            "reel_spacing": 10,
            "symbol_spacing": 5,
            "viewport_offset": {"x": (1920 - cols * (cell_w + 10)) // 2,
                                "y": (1080 - rows * (cell_h + 5)) // 2},
            "reel_mask": {
                "visible_rows": rows,
                "overflow_rows": 1,  # Extra row above/below for scroll effect
            },
        }
        zf.writestr(f"{pfx}/reel_layout.json", json.dumps(reel_layout, indent=2))

        # ── Placeholder directories ──
        zf.writestr(f"{pfx}/sprites/symbols/.gitkeep", "")
        zf.writestr(f"{pfx}/sprites/backgrounds/.gitkeep", "")
        zf.writestr(f"{pfx}/sprites/ui/.gitkeep", "")
        zf.writestr(f"{pfx}/sprites/effects/.gitkeep", "")

        # ── Copy existing art ──
        art_dir = od / "04_art"
        if art_dir.exists():
            for img in art_dir.rglob("*"):
                if img.is_file() and img.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    zf.write(img, f"{pfx}/sprites/{img.relative_to(art_dir)}")

        # ── README ──
        zf.writestr(f"{pfx}/README.md", f"""# {game_title} — Sprite Atlas Package
Generated by ARKAINBRAIN Phase 10 on {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Contents
- `symbols_atlas.json` — TexturePacker-compatible frame definitions ({len(frames)} frames)
- `animation_metadata.json` — Per-symbol animation sequences and timing
- `background_layers.json` — Background parallax layer definitions ({len(BACKGROUND_LAYERS)} layers)
- `reel_layout.json` — Grid positioning and masking config
- `texturepacker_config.json` — TexturePacker CLI settings

## Animation Types per Symbol
| Animation | Frames | FPS | Loop | Usage |
|-----------|--------|-----|------|-------|
| idle | 1 | — | — | Static reel display |
| win_small | 8 | 12 | Yes | Small win celebration |
| win_big | 12 | 15 | Yes | Big win with particles |
| anticipation | 6 | 10 | Yes | Pre-reveal glow |
| land | 4 | 24 | No | Reel stop impact |
| scatter_trigger | 10 | 15 | No | Scatter activation |

## Symbols: {len(symbols)}
## Total Frames: {len(frames)}
## Atlas Size: {atlas_w}×{atlas_h} ({atlas_cols} cols × {atlas_rows} rows)
""")

    return str(zip_path)


def _symbol_type(name: str) -> str:
    n = name.lower()
    if "wild" in n: return "wild"
    if "scatter" in n: return "scatter"
    if "bonus" in n: return "bonus"
    if n.startswith("h"): return "high"
    if n.startswith("l"): return "low"
    return "medium"
