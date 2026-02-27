"""
ARKAINBRAIN — Aggregator Provider SDK Export (Phase 10)

Generates aggregator-specific integration packages for:
- GIG / iSoftBet — Game manifest, RGS hooks, jurisdiction config
- Relax Gaming Silver Bullet — Game descriptor, integration config
- Generic — OpenAPI-compliant versioned JSON for any aggregator
"""

import json
import zipfile
from datetime import datetime
from pathlib import Path


def generate_provider_package(provider: str = "generic", output_dir: str = "",
                              game_title: str = "Untitled Slot", config: dict = None,
                              symbols: list = None, features: list = None,
                              sim_data: dict = None, **kwargs) -> str:
    """Generate aggregator-specific integration package."""
    od = Path(output_dir)
    export_dir = od / "09_export"
    export_dir.mkdir(parents=True, exist_ok=True)

    config = config or {}
    symbols = symbols or []
    features = features or []
    sim_data = sim_data or {}

    slug = game_title.lower().replace(" ", "_").replace("'", "")[:30]
    zip_path = export_dir / f"{slug}_{provider}_sdk.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        pfx = f"{slug}_{provider}"

        if provider == "gig":
            _build_gig_package(zf, pfx, game_title, config, symbols, features, sim_data)
        elif provider == "relax":
            _build_relax_package(zf, pfx, game_title, config, symbols, features, sim_data)
        else:
            _build_generic_package(zf, pfx, game_title, config, symbols, features, sim_data)

    return str(zip_path)


def _build_gig_package(zf, pfx, title, config, symbols, features, sim_data):
    """GIG / iSoftBet aggregator format."""
    game_id = f"ab_{title.lower().replace(' ','_')[:20]}"

    # Game manifest
    manifest = {
        "gameId": game_id,
        "gameName": title,
        "gameType": "video_slot",
        "provider": "arkainbrain",
        "version": "1.0.0",
        "releaseDate": datetime.now().strftime("%Y-%m-%d"),
        "configuration": {
            "grid": {"columns": config.get("grid_cols", 5), "rows": config.get("grid_rows", 3)},
            "waysOrLines": config.get("ways_or_lines", 243),
            "rtp": {
                "target": config.get("target_rtp", 96.0),
                "measured": sim_data.get("measured_rtp"),
                "configurations": [
                    {"id": "rtp_96", "value": config.get("target_rtp", 96.0), "default": True},
                    {"id": "rtp_94", "value": max(88, config.get("target_rtp", 96) - 2), "default": False},
                    {"id": "rtp_92", "value": max(88, config.get("target_rtp", 96) - 4), "default": False},
                ],
            },
            "volatility": config.get("volatility", "medium"),
            "maxWin": {"multiplier": config.get("max_win_multiplier", 5000)},
            "betLimits": {
                "min": 0.10, "max": 100.00, "default": 1.00,
                "currency": "EUR",
                "betLevels": [0.10, 0.20, 0.50, 1.00, 2.00, 5.00, 10.00, 20.00, 50.00, 100.00],
            },
            "features": [
                {"id": f.get("name", f.get("feature", "")).lower().replace(" ", "_"),
                 "name": f.get("name", f.get("feature", "")),
                 "type": f.get("type", "standard")}
                for f in features
            ],
        },
        "jurisdictions": _build_jurisdiction_config(config),
        "metadata": {
            "symbols": len(symbols),
            "simulationSpins": sim_data.get("total_spins"),
            "hitFrequency": sim_data.get("hit_frequency_pct"),
            "generatedBy": "ARKAINBRAIN Pipeline v10",
        },
    }
    zf.writestr(f"{pfx}/game_manifest.json", json.dumps(manifest, indent=2))

    # RGS integration hooks
    rgs_hooks = {
        "endpoints": {
            "init": {"method": "POST", "path": f"/api/v1/games/{game_id}/init",
                     "description": "Initialize game session"},
            "spin": {"method": "POST", "path": f"/api/v1/games/{game_id}/spin",
                     "description": "Execute spin with bet parameters"},
            "freeSpinSpin": {"method": "POST", "path": f"/api/v1/games/{game_id}/freespin",
                             "description": "Execute free spin round"},
            "bonusPick": {"method": "POST", "path": f"/api/v1/games/{game_id}/bonus/pick",
                          "description": "Player pick in bonus round"},
            "gamble": {"method": "POST", "path": f"/api/v1/games/{game_id}/gamble",
                       "description": "Gamble/double-up action"},
            "state": {"method": "GET", "path": f"/api/v1/games/{game_id}/state",
                      "description": "Get current game state"},
            "history": {"method": "GET", "path": f"/api/v1/games/{game_id}/history",
                        "description": "Get round history"},
        },
        "authentication": {
            "type": "Bearer",
            "header": "Authorization",
            "tokenEndpoint": "/api/v1/auth/token",
        },
        "callbacks": {
            "onWin": f"/api/v1/games/{game_id}/callback/win",
            "onJackpot": f"/api/v1/games/{game_id}/callback/jackpot",
            "onError": f"/api/v1/games/{game_id}/callback/error",
        },
    }
    zf.writestr(f"{pfx}/rgs_integration.json", json.dumps(rgs_hooks, indent=2))

    # Paytable config
    zf.writestr(f"{pfx}/paytable.json", json.dumps(symbols, indent=2))
    zf.writestr(f"{pfx}/features.json", json.dumps(features, indent=2))

    # README
    zf.writestr(f"{pfx}/README.md", f"""# {title} — GIG/iSoftBet Integration Package
Generated by ARKAINBRAIN Phase 10

## Files
- `game_manifest.json` — Game configuration with RTP tiers and bet limits
- `rgs_integration.json` — RGS API endpoint definitions and auth config
- `paytable.json` — Symbol pay data
- `features.json` — Feature configurations

## RTP Configurations
Multiple RTP tiers available for different operator requirements.

## Jurisdictions
Pre-configured for: {', '.join(j['id'] for j in manifest['jurisdictions'][:5])}
""")


def _build_relax_package(zf, pfx, title, config, symbols, features, sim_data):
    """Relax Gaming Silver Bullet format."""
    game_descriptor = {
        "gameDescriptor": {
            "gameName": title,
            "gameCode": f"ab_{title.lower().replace(' ','_')[:15]}",
            "provider": "arkainbrain",
            "category": "video_slots",
            "subCategory": _volatility_category(config.get("volatility", "medium")),
            "technology": "html5",
            "platforms": ["desktop", "mobile", "tablet"],
            "orientation": "landscape",
            "responsive": True,
        },
        "mathModel": {
            "rtp": config.get("target_rtp", 96.0),
            "measuredRtp": sim_data.get("measured_rtp"),
            "volatility": config.get("volatility", "medium"),
            "hitFrequency": sim_data.get("hit_frequency_pct"),
            "maxWinMultiplier": config.get("max_win_multiplier", 5000),
            "grid": {
                "columns": config.get("grid_cols", 5),
                "rows": config.get("grid_rows", 3),
                "payMethod": "ways" if config.get("ways_or_lines", 243) > 50 else "lines",
                "waysOrLines": config.get("ways_or_lines", 243),
            },
        },
        "features": [
            {"name": f.get("name", ""), "type": f.get("type", ""), "buyable": False}
            for f in features
        ],
        "betConfig": {
            "minBet": 0.10, "maxBet": 100.00, "defaultBet": 1.00,
            "coinValues": [0.01, 0.02, 0.05, 0.10, 0.20, 0.50],
        },
        "jurisdictions": [j["id"] for j in _build_jurisdiction_config(config)],
        "languages": ["en", "de", "fr", "es", "it", "pt", "ja", "ko", "zh"],
        "certification": {
            "status": "pending",
            "testHouse": "TBD",
            "simulationSpins": sim_data.get("total_spins", 0),
        },
    }
    zf.writestr(f"{pfx}/game_descriptor.json", json.dumps(game_descriptor, indent=2))

    # Integration config
    integration = {
        "silverBullet": {
            "version": "2.0",
            "gameServer": {
                "url": "https://gs.arkainbrain.com/api/v1",
                "healthCheck": "/health",
                "timeout": 5000,
            },
            "clientConfig": {
                "loadingScreen": True,
                "autoplay": True,
                "turboSpin": True,
                "soundEnabled": True,
                "qualitySettings": ["low", "medium", "high"],
            },
            "regulatoryConfig": {
                "realityCheck": {"enabled": True, "intervalMinutes": 60},
                "sessionTimeout": {"enabled": True, "maxMinutes": 240},
                "autoplayLimit": {"enabled": True, "maxSpins": 100},
            },
        }
    }
    zf.writestr(f"{pfx}/integration_config.json", json.dumps(integration, indent=2))
    zf.writestr(f"{pfx}/paytable.json", json.dumps(symbols, indent=2))

    zf.writestr(f"{pfx}/README.md", f"""# {title} — Relax Gaming Silver Bullet Package
Generated by ARKAINBRAIN Phase 10

## Files
- `game_descriptor.json` — Silver Bullet game descriptor with math model
- `integration_config.json` — Server and client configuration
- `paytable.json` — Symbol pay data

## Platforms
Desktop, Mobile, Tablet — responsive HTML5

## Languages
{', '.join(game_descriptor['languages'])}
""")


def _build_generic_package(zf, pfx, title, config, symbols, features, sim_data):
    """OpenAPI-compliant generic provider format."""
    # Versioned game config
    game_config = {
        "apiVersion": "1.0.0",
        "kind": "SlotGameConfig",
        "metadata": {
            "name": title,
            "version": "1.0.0",
            "generator": "ARKAINBRAIN Pipeline v10",
            "generatedAt": datetime.now().isoformat(),
        },
        "spec": {
            "grid": {
                "columns": config.get("grid_cols", 5),
                "rows": config.get("grid_rows", 3),
                "payMethod": "ways" if config.get("ways_or_lines", 243) > 50 else "lines",
                "waysOrLines": config.get("ways_or_lines", 243),
            },
            "math": {
                "targetRtp": config.get("target_rtp", 96.0),
                "measuredRtp": sim_data.get("measured_rtp"),
                "volatility": config.get("volatility", "medium"),
                "hitFrequency": sim_data.get("hit_frequency_pct"),
                "maxWinMultiplier": config.get("max_win_multiplier", 5000),
            },
            "symbols": symbols,
            "features": features,
            "betLimits": {
                "min": 0.10, "max": 100.00, "default": 1.00,
                "levels": [0.10, 0.20, 0.50, 1.00, 2.00, 5.00, 10.00, 20.00, 50.00, 100.00],
            },
            "jurisdictions": _build_jurisdiction_config(config),
        },
    }
    zf.writestr(f"{pfx}/game_config.json", json.dumps(game_config, indent=2))

    # OpenAPI schema
    openapi = {
        "openapi": "3.0.3",
        "info": {"title": f"{title} Game API", "version": "1.0.0",
                 "description": f"API specification for {title} slot game"},
        "paths": {
            "/init": {"post": {"summary": "Initialize game session", "operationId": "initGame",
                               "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/InitRequest"}}}},
                               "responses": {"200": {"description": "Session initialized"}}}},
            "/spin": {"post": {"summary": "Execute spin", "operationId": "spin",
                               "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/SpinRequest"}}}},
                               "responses": {"200": {"description": "Spin result"}}}},
            "/state": {"get": {"summary": "Get game state", "operationId": "getState",
                               "responses": {"200": {"description": "Current state"}}}},
        },
        "components": {
            "schemas": {
                "InitRequest": {"type": "object", "properties": {
                    "sessionToken": {"type": "string"}, "currency": {"type": "string"},
                    "language": {"type": "string"}, "jurisdiction": {"type": "string"}}},
                "SpinRequest": {"type": "object", "properties": {
                    "betAmount": {"type": "number"}, "betLevel": {"type": "integer"},
                    "sessionToken": {"type": "string"}}},
                "SpinResult": {"type": "object", "properties": {
                    "grid": {"type": "array"}, "totalWin": {"type": "number"},
                    "winLines": {"type": "array"}, "features": {"type": "array"}}},
            }
        },
    }
    zf.writestr(f"{pfx}/openapi.json", json.dumps(openapi, indent=2))

    if sim_data:
        zf.writestr(f"{pfx}/simulation_results.json", json.dumps(sim_data, indent=2))

    zf.writestr(f"{pfx}/README.md", f"""# {title} — Generic Provider SDK Package
Generated by ARKAINBRAIN Phase 10

## Files
- `game_config.json` — Versioned game configuration (OpenAPI-style)
- `openapi.json` — OpenAPI 3.0 specification for game API endpoints
- `simulation_results.json` — Math model simulation data

## Integration
This package follows a provider-agnostic format.
Adapt `game_config.json` to your specific aggregator's requirements.
""")


def _build_jurisdiction_config(config: dict) -> list:
    """Build jurisdiction-specific configurations."""
    markets = config.get("target_markets", [])
    if isinstance(markets, str):
        markets = [m.strip() for m in markets.split(",")]

    jurisdictions = []
    market_map = {
        "uk": {"id": "UKGC", "maxBet": 5.00, "autoplayLimit": 25, "realityCheck": True, "spinSpeed": "normal"},
        "malta": {"id": "MGA", "maxBet": 100.00, "autoplayLimit": 100, "realityCheck": True},
        "gibraltar": {"id": "GRA", "maxBet": 100.00, "realityCheck": True},
        "sweden": {"id": "SGA", "maxBet": 100.00, "autoplayLimit": 0, "bonusBuyDisabled": True},
        "denmark": {"id": "DGA", "maxBet": 100.00, "realityCheck": True},
        "ontario": {"id": "AGCO", "maxBet": 100.00, "realityCheck": True, "autoplayLimit": 0},
        "georgia": {"id": "GEO_GRA", "maxBet": 100.00},
        "texas": {"id": "TX_GC", "maxBet": 100.00},
        "michigan": {"id": "MGCB", "maxBet": 100.00, "realityCheck": True},
        "new jersey": {"id": "DGE_NJ", "maxBet": 100.00, "realityCheck": True},
    }

    for market in markets:
        ml = market.lower().strip()
        for key, cfg in market_map.items():
            if key in ml:
                jurisdictions.append(cfg)
                break
        else:
            jurisdictions.append({"id": ml.upper()[:10], "maxBet": 100.00})

    if not jurisdictions:
        jurisdictions = [
            {"id": "MGA", "maxBet": 100.00, "realityCheck": True},
            {"id": "UKGC", "maxBet": 5.00, "autoplayLimit": 25, "realityCheck": True},
        ]

    return jurisdictions


def _volatility_category(vol: str) -> str:
    return {"low": "frequent_wins", "medium": "balanced", "medium_high": "high_action",
            "high": "high_volatility", "extreme": "extreme_volatility"}.get(vol, "balanced")
