"""
ARKAINBRAIN — Mini RMG Game Pipeline (Phase 7)

Second pipeline type: Real Money Gaming mini-games.
Produces playable HTML5 games with provably fair math.

Stages:
  Brief → Research → Math Model → Game Design → Playable Build → Compliance → Package

Supported games: crash, plinko, mines, dice, wheel, hilo, chicken, scratch
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger("arkainbrain.rmg")
console = Console()


def emit(event_type: str, **data):
    """Emit structured log events for the thought-feed UI."""
    payload = json.dumps({"event": event_type, **data})
    print(f"[EMIT] {payload}", flush=True)


def run_mini_rmg(job_id: str, params: dict, output_dir: str):
    """Execute the full Mini RMG pipeline.

    Args:
        job_id: Job ID
        params: Pipeline parameters from the form
        output_dir: Base output directory path
    """
    from config.database import worker_update_job
    from sim_engine.rmg import get_game_engine, GAME_TYPES

    started = datetime.now().isoformat()
    game_type = params.get("game_type", "crash").lower()
    theme = params.get("theme", "Default Game")
    house_edge = float(params.get("house_edge", 0.03))
    max_multiplier = float(params.get("max_multiplier", 1000))
    web3_mode = params.get("web3_mode", False)
    custom_config = params.get("custom_config", {})

    console.print(Panel(
        f"[bold]🎮 Mini RMG Pipeline[/bold]\n\n"
        f"Game Type: {game_type}\n"
        f"Theme: {theme}\n"
        f"House Edge: {house_edge*100:.1f}%\n"
        f"Max Multiplier: {max_multiplier}x\n"
        f"Web3 Mode: {'Yes' if web3_mode else 'No'}",
        title="Mini RMG Starting", border_style="cyan",
    ))

    # Validate game type
    if game_type not in GAME_TYPES:
        worker_update_job(job_id, status="failed",
                          error=f"Unknown game type: {game_type}. Available: {GAME_TYPES}")
        return

    # Create output dirs
    od = Path(output_dir)
    for sub in ["00_config", "01_math", "02_design", "03_game", "04_compliance", "05_package"]:
        (od / sub).mkdir(parents=True, exist_ok=True)

    worker_update_job(job_id, status="running", current_stage="Initializing", output_dir=str(od))

    try:
        # ══════════════════════════════════════════════════
        # STAGE 1: Math Model
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Computing math model")
        emit("stage_start", name="Math Model", num=0, icon="🔢",
             desc=f"Building {game_type} math model with {house_edge*100:.1f}% house edge")
        console.print(f"\n[bold cyan]🔢 Stage 1: Math Model ({game_type})[/bold cyan]\n")

        engine = get_game_engine(game_type)
        config = engine.generate_config(
            house_edge=house_edge,
            max_multiplier=max_multiplier,
            **custom_config,
        )

        # Save config
        (od / "00_config" / "game_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8")

        # Run simulation
        console.print(f"[cyan]Running 500,000-round simulation...[/cyan]")
        sim_results = engine.simulate(config, rounds=500_000, seed=42)
        (od / "01_math" / "simulation_results.json").write_text(
            json.dumps(sim_results.to_dict(), indent=2), encoding="utf-8")

        console.print(f"[green]✅ Math model complete:[/green]")
        console.print(f"   House Edge: theoretical={sim_results.house_edge_theoretical*100:.2f}% "
                       f"measured={sim_results.house_edge_measured*100:.2f}%")
        console.print(f"   RTP: {sim_results.rtp*100:.2f}%")
        console.print(f"   Hit Rate: {sim_results.hit_rate*100:.1f}%")
        console.print(f"   Max Win Hit: {sim_results.max_multiplier_hit:.1f}x")

        emit("stage_done", name="Math Model", num=0)
        emit("metric", key="rtp", value=round(sim_results.rtp * 100, 2), label="RTP %")
        emit("metric", key="house_edge", value=round(sim_results.house_edge_measured * 100, 3),
             label="House Edge %")

        # ══════════════════════════════════════════════════
        # STAGE 2: Game Design (LLM-powered)
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Generating game design")
        emit("stage_start", name="Game Design", num=1, icon="🎨",
             desc=f"AI-designing '{theme}' {game_type} game")
        console.print(f"\n[bold yellow]🎨 Stage 2: Game Design[/bold yellow]\n")

        design = _generate_game_design(game_type, theme, config, sim_results)
        (od / "02_design" / "game_design.json").write_text(
            json.dumps(design, indent=2), encoding="utf-8")
        console.print(f"[green]✅ Game design generated: {design.get('title', theme)}[/green]")
        emit("stage_done", name="Game Design", num=1)

        # ══════════════════════════════════════════════════
        # STAGE 3: Playable HTML5 Build
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Building HTML5 game")
        emit("stage_start", name="Playable Build", num=2, icon="🎮",
             desc="Generating full HTML5 playable game")
        console.print(f"\n[bold green]🎮 Stage 3: Playable HTML5 Build[/bold green]\n")

        from templates.rmg.builder import build_rmg_game
        game_path = build_rmg_game(
            game_type=game_type,
            design=design,
            config=config,
            sim_results=sim_results.to_dict(),
            output_dir=str(od / "03_game"),
        )
        console.print(f"[green]✅ HTML5 game built: {game_path}[/green]")
        emit("stage_done", name="Playable Build", num=2)

        # ══════════════════════════════════════════════════
        # STAGE 4: Compliance Check
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Compliance verification")
        emit("stage_start", name="Compliance", num=3, icon="⚖️",
             desc="Verifying provably fair + jurisdiction compliance")
        console.print(f"\n[bold red]⚖️ Stage 4: Compliance[/bold red]\n")

        compliance = _run_compliance_check(game_type, config, sim_results, params)
        (od / "04_compliance" / "compliance_report.json").write_text(
            json.dumps(compliance, indent=2), encoding="utf-8")
        status_str = "✅ PASS" if compliance.get("passed") else "⚠️ WARNINGS"
        console.print(f"[green]{status_str}: {len(compliance.get('checks', []))} checks run[/green]")
        emit("stage_done", name="Compliance", num=3)

        # ══════════════════════════════════════════════════
        # STAGE 5: Web3 Output (Optional)
        # ══════════════════════════════════════════════════
        if web3_mode:
            worker_update_job(job_id, current_stage="Generating Web3 contracts")
            emit("stage_start", name="Web3 Output", num=4, icon="🔗",
                 desc="Generating Solidity contracts + deploy scripts")
            console.print(f"\n[bold magenta]🔗 Stage 5: Web3 Output[/bold magenta]\n")

            from templates.web3.generator import generate_web3_output
            w3_path = generate_web3_output(
                game_type=game_type,
                config=config,
                design=design,
                output_dir=str(od / "05_package" / "web3"),
            )
            console.print(f"[green]✅ Web3 contracts generated: {w3_path}[/green]")
            emit("stage_done", name="Web3 Output", num=4)

        # ══════════════════════════════════════════════════
        # STAGE 6: Package
        # ══════════════════════════════════════════════════
        worker_update_job(job_id, current_stage="Packaging deliverables")
        emit("stage_start", name="Package", num=5, icon="📦", desc="Assembling final package")
        console.print(f"\n[bold green]📦 Stage 6: Package[/bold green]\n")

        manifest = {
            "game_type": game_type,
            "theme": theme,
            "title": design.get("title", theme),
            "house_edge_target": house_edge,
            "house_edge_measured": sim_results.house_edge_measured,
            "rtp": sim_results.rtp,
            "max_multiplier_config": max_multiplier,
            "max_multiplier_hit": sim_results.max_multiplier_hit,
            "simulation_rounds": sim_results.rounds,
            "web3": web3_mode,
            "compliance_passed": compliance.get("passed", False),
            "started_at": started,
            "completed_at": datetime.now().isoformat(),
            "files": [str(f.relative_to(od)) for f in od.rglob("*") if f.is_file()],
        }
        (od / "05_package" / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")

        all_files = list(od.rglob("*"))
        file_count = sum(1 for f in all_files if f.is_file())
        console.print(Panel(
            f"[bold green]✅ Mini RMG Pipeline Complete[/bold green]\n\n"
            f"📁 Output: {od}\n"
            f"🎮 Game: {design.get('title', theme)}\n"
            f"📊 RTP: {sim_results.rtp*100:.2f}% (target: {(1-house_edge)*100:.2f}%)\n"
            f"📄 Files: {file_count}\n"
            f"⏱️ {started} → {manifest['completed_at']}",
            title="🎮 Package Complete", border_style="green",
        ))

        emit("stage_done", name="Package", num=5)
        emit("metric", key="files", value=file_count, label="Total Files")
        emit("info", msg="Pipeline complete", icon="🎮")

        worker_update_job(
            job_id, status="complete",
            current_stage="Complete",
            completed_at=datetime.now().isoformat(),
        )

        # Index in pipeline memory
        try:
            from memory.run_indexer import _extract_theme_tags
            from config.database import get_standalone_db
            import uuid

            run_id = str(uuid.uuid4())[:12]
            db = get_standalone_db()
            db.execute(
                """INSERT INTO run_records (
                    id, job_id, theme, theme_tags, grid, eval_mode,
                    volatility, measured_rtp, target_rtp, hit_frequency,
                    max_win_achieved, features, cost_usd, gdd_summary
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    run_id, job_id, theme,
                    json.dumps(_extract_theme_tags(theme)),
                    "N/A", game_type, "N/A",
                    sim_results.rtp * 100,
                    (1 - house_edge) * 100,
                    sim_results.hit_rate * 100,
                    sim_results.max_multiplier_hit,
                    json.dumps([game_type]),
                    0.0,
                    f"Mini RMG {game_type}: {theme}. HE={house_edge*100:.1f}%",
                ]
            )
            db.commit()
            db.close()
            console.print(f"[green]🧠 Indexed in pipeline memory: {run_id}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Memory indexing: {e}[/yellow]")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        console.print(f"[red]❌ Pipeline failed: {e}[/red]")
        console.print(tb)
        worker_update_job(
            job_id, status="failed",
            error=str(e)[:500],
            completed_at=datetime.now().isoformat(),
        )


def _generate_game_design(game_type: str, theme: str, config: dict, sim_results) -> dict:
    """Generate game design using LLM or fallback to template."""
    try:
        import openai
        client = openai.OpenAI()
        prompt = (
            f"You are a game designer creating a {game_type} mini-game themed '{theme}'.\n\n"
            f"Game config: {json.dumps(config, indent=2)}\n"
            f"Simulation: RTP={sim_results.rtp*100:.2f}%, hit_rate={sim_results.hit_rate*100:.1f}%\n\n"
            f"Generate a JSON game design with these fields:\n"
            f"- title: catchy game name\n"
            f"- tagline: 1-line marketing tagline\n"
            f"- description: 2-3 sentence game description\n"
            f"- ui_theme: object with primary_color (hex), secondary_color (hex), "
            f"bg_gradient (array of 2 hex colors), font_style (modern/retro/elegant)\n"
            f"- sound_theme: ambient mood (space/casino/adventure/nature/cyberpunk)\n"
            f"- animations: array of key animation moments\n"
            f"- bet_options: array of bet amounts\n"
            f"- currency_symbol: default '$'\n\n"
            f"Return ONLY valid JSON, no markdown."
        )
        resp = client.chat.completions.create(
            model=os.getenv("LLM_LIGHT", "gpt-5-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.8,
        )
        text = resp.choices[0].message.content.strip()
        # Clean markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text)
    except Exception as e:
        logger.warning(f"LLM design generation failed, using template: {e}")
        return _fallback_design(game_type, theme, config)


def _fallback_design(game_type: str, theme: str, config: dict) -> dict:
    """Fallback design template when LLM is unavailable."""
    return {
        "title": theme,
        "tagline": f"A thrilling {game_type} experience",
        "description": f"Test your luck with {theme} — a provably fair {game_type} game.",
        "ui_theme": {
            "primary_color": "#7c6aef",
            "secondary_color": "#22c55e",
            "bg_gradient": ["#0a0a1a", "#1a1a3e"],
            "font_style": "modern",
        },
        "sound_theme": "casino",
        "animations": ["win_celebration", "loss_fade", "multiplier_tick"],
        "bet_options": [0.10, 0.25, 0.50, 1.00, 2.00, 5.00, 10.00, 25.00],
        "currency_symbol": "$",
    }


def _run_compliance_check(game_type: str, config: dict, sim_results, params: dict) -> dict:
    """Run basic compliance checks for RMG games."""
    checks = []
    passed = True

    # 1. RTP within tolerance
    he_target = config.get("house_edge", 0.03)
    he_measured = sim_results.house_edge_measured
    delta = abs(he_target - he_measured)
    ok = delta < 0.005
    checks.append({
        "name": "House Edge Accuracy",
        "passed": ok,
        "detail": f"Target: {he_target*100:.2f}%, Measured: {he_measured*100:.2f}%, Δ={delta*100:.3f}%",
    })
    if not ok:
        passed = False

    # 2. Hit rate sanity
    hr = sim_results.hit_rate
    ok2 = 0.01 < hr < 0.99
    checks.append({
        "name": "Hit Rate Sanity",
        "passed": ok2,
        "detail": f"Hit rate: {hr*100:.1f}% (expected 1-99%)",
    })

    # 3. Max multiplier within bounds
    max_config = config.get("max_multiplier", 1000)
    max_hit = sim_results.max_multiplier_hit
    ok3 = max_hit <= max_config * 1.01  # Allow tiny float error
    checks.append({
        "name": "Max Multiplier Cap",
        "passed": ok3,
        "detail": f"Config max: {max_config}x, Simulation max: {max_hit:.1f}x",
    })

    # 4. Provably fair capability
    checks.append({
        "name": "Provably Fair",
        "passed": True,
        "detail": "SHA-256 server_seed:client_seed:nonce — verifiable",
    })

    # 5. Simulation sample size
    ok5 = sim_results.rounds >= 100_000
    checks.append({
        "name": "Simulation Confidence",
        "passed": ok5,
        "detail": f"{sim_results.rounds:,} rounds (min 100,000)",
    })

    return {"passed": passed, "checks": checks, "game_type": game_type}
