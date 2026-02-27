# ARKAINBRAIN v8.0 — AI Slot Game Studio + Admin Platform

Built by [ArkainGames.com](https://arkaingames.com)

**77 Python files · 31,600+ lines · 100 routes · 15 database tables · 4 React SPAs**

---

## What It Does

Describe a slot game concept and target jurisdictions. ARKAINBRAIN deploys six specialist AI agents that research the market, design the game, build the math model, generate art and audio, scan patents, plan certification, and package everything into 8 branded PDF deliverables plus a playable HTML5 prototype.

Beyond the core pipeline, v6 adds: a validated simulation engine, pipeline memory with vector search, a mini-RMG builder for 8 non-slot game types, an interactive review UI with inline editing, multi-variant generation with mix-and-match hybrids, production-grade export to Unity/Godot/FMOD/Wwise/provider SDKs, a portfolio intelligence dashboard with market alignment scoring, and a full admin backend with user management, cost tracking, and job monitoring.

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Required: OPENAI_API_KEY, SERPER_API_KEY
# Optional: ELEVENLABS_API_KEY, QDRANT_URL, QDRANT_API_KEY
# For web UI: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

python web_app.py
# → http://localhost:5000
```

CLI mode:
```bash
python main.py --theme "Ancient Egyptian" --markets Georgia Texas --volatility high
```

Promote yourself to admin:
```bash
python web_app.py set-admin your@email.com
```

---

## Platform Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Web UI (Flask + server-rendered HTML)                   │
│  ├── Pipeline Launcher        ├── Mini RMG Builder       │
│  ├── State Recon             ├── Review UI (React SPA)   │
│  ├── Variant Comparisons     ├── Export Dashboard        │
│  ├── Portfolio Intelligence  ├── Job File Browser        │
│  └── Settings + Memory       └── History                 │
├──────────────────────────────────────────────────────────┤
│  Admin Panel (/admin)                                    │
│  ├── Dashboard (users, jobs, costs at a glance)          │
│  ├── User Management (plans, roles, suspend, impersonate)│
│  ├── Job Monitor (browse, preview content, cancel/delete)│
│  ├── Cost Tracking (LLM spend by provider/model/user)    │
│  └── Audit Log (every admin action recorded)             │
├──────────────────────────────────────────────────────────┤
│  Pipeline Engine                                         │
│  ├── 6 AI Agents (GPT-5 reasoning models)                │
│  ├── Simulation Engine (Monte Carlo + convergence)       │
│  ├── Export Engine (8 formats → ZIP packages)            │
│  ├── Portfolio Engine (gap analysis + alignment scoring) │
│  └── Cost Tracker (per-call LLM metering)                │
├──────────────────────────────────────────────────────────┤
│  Storage                                                 │
│  ├── SQLite / PostgreSQL (15 tables)                     │
│  ├── Qdrant (vector search for jurisdictions + memory)   │
│  └── File system (output ZIPs, PDFs, prototypes)         │
└──────────────────────────────────────────────────────────┘
```

---

## The Agent Team

| Agent | Role | Expertise |
|-------|------|-----------|
| **Victoria Kane** | Lead Producer | 280+ concepts evaluated, 38% greenlight rate, Go/No-Go scoring |
| **Dr. Raj Patel** | Market Analyst | 2,800+ titles tracked across 24 jurisdictions, competitive heat maps |
| **Elena Voss** | Game Designer | 62 shipped titles, RTP-budget-first design, Monte Carlo mental models |
| **Dr. Thomas Black** | Mathematician | 620+ GLI-certified models, closed-form before simulation, ±0.02% RTP |
| **Sophia Laurent** | Art Director | 38 titles averaging $220+/day/unit, symbol hierarchy optimization |
| **Marcus Reed** | Compliance Officer | 620+ submissions, 300+ rejection case database, proactive IP risk |

---

## Pipeline Output

```
output/{game_slug}/
├── 00_preflight/         Trend radar, jurisdiction scan, patent check
├── 01_research/          Market sweep, competitor analysis, research report
├── 02_design/            Game Design Document (GDD)
├── 03_math/              Reel strips (CSV), paytable, simulation results
├── 04_art/               DALL-E symbols, backgrounds, logos, mood boards
├── 04_audio/             Sound effects + audio design brief
├── 05_legal/             Compliance report, certification plan
├── 06_pdf/               8 branded PDF deliverables
├── 07_prototype/         Playable HTML5 slot demo
├── 08_revenue/           Revenue projections + comparable benchmarks
└── 09_export/            Unity/Godot/FMOD/Wwise/provider SDK packages
```

### 8 PDF Deliverables

| # | PDF | Contents |
|---|-----|----------|
| 1 | Executive Summary | Metrics dashboard, market intel, design overview, math summary |
| 2 | Game Design Document | Full GDD rendered from markdown |
| 3 | Math Model Report | RTP breakdown, reel strips, paytable, simulation results |
| 4 | Compliance Report | Per-jurisdiction analysis, risk flags, certification requirements |
| 5 | Market Research | Competitors with metrics, target market analysis |
| 6 | Art Direction Brief | Style guide, symbol hierarchy, color palette |
| 7 | Audio Design Brief | Sound direction, core effects, adaptive audio specs |
| 8 | Business Projections | 3-year revenue, ROI analysis, comparable benchmarks |

---

## Feature Phases

### Phase 5A — Infrastructure
PostgreSQL support, Redis queue, Railway multi-service deployment, ZIP download, file manager.

### Phase 5B — Simulation Engine
Monte Carlo simulator with core evaluators, feature modules, reference game validation, JSON config schema, convergence detection, confidence intervals.

### Phase 6 — Pipeline Memory
Run indexing, component extraction, semantic vector search (Qdrant), agent prompt injection from historical runs.

### Phase 7 — Mini RMG Pipeline
8 non-slot game types with math models and HTML5 builders:

| Game | House Edge | Description |
|------|-----------|-------------|
| Crash | 1-5% | Multiplier curve with cash-out timing |
| Plinko | 1-4% | Ball-drop with configurable pegs |
| Mines | 1-5% | Grid reveal with progressive multipliers |
| Dice | 1-2% | Over/under with adjustable threshold |
| Wheel | 2-5% | Weighted wheel with segments |
| Hi-Lo | 2-4% | Card prediction with streak multipliers |
| Chicken | 1-5% | Lane-crossing risk game |
| Scratch | 5-15% | Instant reveal with prize tiers |

Includes optional Web3 scaffold (Solidity contracts + Chainlink VRF).

### Phase 8 — Interactive Review UI
React SPA with inline GDD editing, drag-and-drop paytable editor with instant RTP recalculation, threaded comments, per-section approvals, diff viewer. 13 API endpoints.

### Phase 9 — Multi-Variant Generation
LLM-powered strategy engine with 7 variant templates, mix-and-match hybrid creator, React comparison dashboard with side-by-side visual diffs.

### Phase 10 — Export Pipeline
8 production-grade export formats:

| Format | Output |
|--------|--------|
| Unity | ScriptableObjects, C# SpinController, prefab scaffolds |
| Godot 4 | .tscn scenes, .gd scripts, .tres resources |
| FMOD | .fspro project, 15 event sheets, RTPC mappings |
| Wwise | .wproj project, SoundBank definitions |
| Sprite Atlas | TexturePacker JSON, per-symbol animation metadata |
| GIG/iSoftBet | Game manifest, RGS integration config |
| Relax Gaming | Silver Bullet descriptor, integration config |
| Generic SDK | OpenAPI schema, versioned game config JSON |

Batch export (all 8 in one mega-ZIP), preview API, export history tracking, dedicated dashboard.

### Phase 11 — Portfolio Intelligence
React SPA dashboard with 4 tabs:

- **Overview** — stat cards, theme/volatility/mechanic/jurisdiction bar charts, generation timeline, theme×volatility heatmap, market alignment score (0-100 with A+ to D grading)
- **Gap Analysis** — missing themes, underweight categories, mechanic gaps, jurisdiction gaps, RTP distribution — all with severity ratings and actionable recommendations
- **Revenue** — 4-scenario projections (conservative/base/optimistic/bull), top games ranking, launch scenario builder
- **Trends** — theme market share, mechanic adoption curves, regulatory updates, trend signals

Auto-captures daily portfolio snapshots for historical comparison.

### Admin Backend (A1 + A2 + A3)

**User Management:**
- Paginated user list with search, plan/role filters, CSV export
- User detail: job history, usage stats, cost breakdown, audit trail
- Actions: change plan, change role, suspend/unsuspend, impersonate
- 4 plan tiers: Free (10 jobs/mo), Pro $49 (100), Studio $199 (500), Enterprise (unlimited)

**Job Monitor:**
- Browse all jobs across all users with status/type/user filters
- Job detail with content previews: GDD, paytable, simulation results, art assets
- Actions: cancel, delete (with files), re-queue failed jobs
- Per-job cost breakdown with every API call logged

**Cost Tracking:**
- Every LLM call instrumented: provider, model, tokens in/out, cost, latency
- 13 default rates (GPT-4o, Claude Sonnet, DALL-E, compute)
- Dashboard: daily burn chart, spend by provider/model, top spenders, most expensive jobs
- Projected monthly spend, updatable rate table

**Audit Log:**
- Every admin action recorded: who, what, when, target, IP address

---

## Database Schema (15 Tables)

| Table | Purpose |
|-------|---------|
| `users` | Accounts with role, plan, usage limits, suspension |
| `jobs` | Pipeline runs with params, status, output paths |
| `reviews` | Review sessions linking to jobs |
| `review_comments` | Threaded comments on job sections |
| `section_approvals` | Per-section approval status |
| `file_tags` | Tags on output files |
| `run_records` | Pipeline memory — indexed past runs |
| `component_library` | Extracted reusable components |
| `iteration_feedback` | Feedback on iterated jobs |
| `market_trends` | Market data (themes, mechanics, regulations) |
| `export_history` | Export tracking with format/size/timestamp |
| `portfolio_snapshots` | Daily portfolio state captures |
| `admin_audit_log` | Admin action tracking |
| `cost_events` | Per-call LLM/compute cost events |
| `cost_rates` | Provider pricing table (updatable) |

---

## Route Summary

| Area | Count | Examples |
|------|-------|---------|
| Core app | 77 | `/`, `/new`, `/job/{id}/files`, `/portfolio`, `/api/...` |
| Admin | 23 | `/admin`, `/admin/users`, `/admin/jobs`, `/admin/costs` |
| **Total** | **100** | |

---

## API Keys

| Key | Required | Purpose |
|-----|----------|---------|
| `OPENAI_API_KEY` | Yes | GPT agents, DALL-E art, Vision QA |
| `SERPER_API_KEY` | Yes | Web search, patent search, trend radar |
| `ELEVENLABS_API_KEY` | Optional | AI sound effect generation |
| `QDRANT_URL` + `QDRANT_API_KEY` | Optional | Vector DB for regulations + memory |
| `GOOGLE_CLIENT_ID` + `SECRET` | For web UI | Google OAuth sign-in |

---

## Deployment

### Local Development
```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python web_app.py
```

### Railway (Production)
See `RAILWAY_DEPLOY.md` — multi-service deployment with web, worker, sim-runner, PostgreSQL, and Redis.

### PythonAnywhere
See `DEPLOY_PYTHONANYWHERE.md` — single-service SQLite deployment.

### Docker
```bash
docker-compose -f deploy/docker-compose.yml up
```

### Admin Setup
After first login via Google OAuth:
```bash
python web_app.py set-admin your@email.com
```
The 🔒 Admin link appears in your sidebar. From there you can manage all users, monitor jobs, track costs, and view the audit log.

---

## File Structure

```
arkainbrain/
├── web_app.py                  Flask app (3,847 lines, 77 routes)
├── worker.py                   Background job processor
├── main.py                     CLI entry point
│
├── admin/                      Admin backend (A1/A2/A3)
│   ├── __init__.py             Blueprint registration
│   ├── decorators.py           @admin_required, audit_log, plan defs
│   ├── routes.py               Dashboard + user management (562 lines)
│   ├── cost_routes.py          Cost tracking dashboard (203 lines)
│   └── job_routes.py           Job monitor + content preview (392 lines)
│
├── agents/                     AI agent definitions
│   └── adversarial_reviewer.py Review agent
│
├── api/
│   └── review_routes.py        Review UI API (13 endpoints)
│
├── config/
│   ├── database.py             Schema (15 tables) + migrations (776 lines)
│   ├── settings.py             Environment config
│   └── context_guard.py        Context window management
│
├── flows/
│   ├── pipeline.py             Core slot pipeline
│   ├── state_recon.py          US state legal research
│   ├── variant_strategy.py     Multi-variant LLM strategy engine
│   ├── variant_mixer.py        Mix-and-match hybrid creator
│   └── mini_rmg_pipeline.py    8 game-type pipeline
│
├── memory/                     Pipeline memory + vector search
│   ├── embeddings.py           Embedding generation
│   ├── query_engine.py         Semantic search
│   ├── run_indexer.py          Run indexing
│   ├── component_extractor.py  Component extraction
│   └── prompt_injector.py      Agent prompt enrichment
│
├── sim_engine/rmg/             8 RMG game simulators
│   ├── crash.py, plinko.py, mines.py, dice.py
│   ├── wheel.py, hilo.py, chicken.py, scratch.py
│   └── base.py                 Shared simulator base
│
├── static/
│   ├── portfolio/index.html    Portfolio Intelligence SPA (18KB)
│   ├── review-app/index.html   Review UI SPA (23KB)
│   └── review-app/variant-compare.html  Variant comparison SPA (11KB)
│
├── templates/
│   ├── rmg/builder.py          HTML5 game template builder
│   └── web3/generator.py       Solidity + Chainlink scaffold
│
├── tools/
│   ├── cost_tracker.py         LLM cost instrumentation (270 lines)
│   ├── export_engine.py        Export pipeline (831 lines)
│   ├── export_formats/         8 format generators (1,360 lines)
│   │   ├── unity.py, godot.py, audio.py, atlas.py, provider.py
│   │   └── __init__.py         Format registry
│   ├── portfolio_engine.py     Portfolio analytics (540 lines)
│   ├── market_scraper.py       Market trend data (142 lines)
│   ├── pdf_generator.py        8-PDF branded generator
│   ├── prototype_engine.py     HTML5 slot prototype builder
│   ├── revenue_engine.py       Revenue projection engine
│   └── ...                     12 more tool modules
│
├── requirements.txt
├── Dockerfile
└── deploy/                     Railway + Docker configs
```

---

## License

Prototype engine uses the [1stake slot machine](https://github.com/1stake/slot-machine-online-casino-game) under MIT license. All other code is proprietary to ArkainGames.

