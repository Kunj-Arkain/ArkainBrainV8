# ARKAINBRAIN v5.0 — AI-Powered Slot Game Intelligence

Built by [ArkainGames.com](https://arkaingames.com)

## What It Does

Describe a slot game concept and target jurisdictions. ARKAINBRAIN deploys six named AI agents — each a GPT-5 reasoning model with deep industry backstory — that research the market, design the game, build the math model, generate art and audio, scan patents, plan certification, and package everything into 8 branded PDF deliverables plus a playable HTML5 prototype.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in: OPENAI_API_KEY, SERPER_API_KEY (required)
# Optional: ELEVENLABS_API_KEY, QDRANT_URL, QDRANT_API_KEY

python web_app.py
# → http://localhost:5000
```

CLI mode:
```bash
python main.py --theme "Ancient Egyptian" --markets Georgia Texas --volatility high
```

## The Agent Team

Six specialist agents with expert backstories, reasoning protocols, and strict quality gates:

| Agent | Role | Model | Expertise |
|-------|------|-------|-----------|
| **Victoria Kane** | Lead Producer | GPT-5-mini | 280+ concepts evaluated, 38% greenlight rate, Go/No-Go scoring |
| **Dr. Raj Patel** | Market Analyst | GPT-5 | 2,800+ titles tracked across 24 jurisdictions, 6-axis competitive heat maps |
| **Elena Voss** | Game Designer | GPT-5 | 62 shipped titles, RTP-budget-first design, Monte Carlo mental models |
| **Dr. Thomas Black** | Mathematician | GPT-5 | 620+ GLI-certified models, closed-form before simulation, ±0.02% RTP precision |
| **Sophia Laurent** | Art Director | GPT-5-mini | 38 titles averaging $220+/day/unit, symbol hierarchy at 1.5m on 27" cabinet |
| **Marcus Reed** | Compliance Officer | GPT-5 | 620+ submissions, 300+ rejection case database, proactive IP risk mitigation |

All agents share a global mandate: zero placeholders, real precedent citations, file outputs (not summaries), and silent self-review before delivery.

## Pipeline Stages

```
Initialize → Pre-Flight Intel → Research (3-pass) → [Review] →
Design + Math (6 CSV files) → [Review] → Art + Audio → Assembly → 8 PDFs + Prototype
```

### Pre-Flight Intelligence
- **Trend Radar** — theme saturation and momentum scoring
- **Jurisdiction Intersection** — tightest constraints across all target markets
- **Patent/IP Scanner** — mechanic conflict check against known gaming patents
- **Knowledge Base** — Qdrant-backed memory across pipeline runs
- **State Recon** — cached legal research for US states

## Target Jurisdictions

Enter any mix of US states, countries, or regulated markets:
```
Georgia, Texas, UK, Malta, Ontario, New Jersey
```
Unknown US states trigger automatic State Recon before the pipeline runs.

## Output

```
output/{game_slug}/
├── 00_preflight/         Trend radar, jurisdiction scan, patent check
├── 01_research/          Market sweep, competitor analysis, full research report
├── 02_design/            Game Design Document (GDD)
├── 03_math/              BaseReels.csv, FreeReels.csv, FeatureReelStrips.csv,
│                         paytable.csv, simulation_results.json, player_behavior.json
├── 04_art/               DALL-E symbols, backgrounds, logos, mood boards
├── 04_audio/             ElevenLabs sound effects + audio design brief
├── 05_legal/             Compliance report, certification plan
├── 06_pdf/               8 branded PDF deliverables (see below)
├── 07_prototype/         Playable HTML5 slot demo (1stake engine)
└── PACKAGE_MANIFEST.json
```

### 8 PDF Deliverables

| # | PDF | Pages | Contents |
|---|-----|-------|----------|
| 1 | Executive Summary | 8–15 | Metrics dashboard, commandments, market intel, design overview, math summary, compliance, art/audio direction, next steps |
| 2 | Game Design Document | 15–30 | Full GDD with all sections rendered from markdown |
| 3 | Math Model Report | 10–20 | RTP breakdown, reel strips as tables, paytable, win distribution, simulation results |
| 4 | Compliance Report | 5–10 | Per-jurisdiction analysis, risk flags, certification requirements |
| 5 | Market Research Report | 8–12 | Market overview, 5–10 competitors with metrics, target market analysis, revenue potential |
| 6 | Art Direction Brief | 5–8 | Style guide, symbol hierarchy, color palette, animation specs |
| 7 | Audio Design Brief | 3–5 | Sound direction, core effects list, adaptive audio specs |
| 8 | Business Projections | 8–12 | Market sizing, 3-year revenue projections, ROI analysis, comparable benchmarks, risk factors |

### HTML5 Prototype

Powered by the [1stake slot engine](https://github.com/1stake/slot-machine-online-casino-game) (MIT license):
- 5 reels, 20 paylines, real spinning animation
- DALL-E symbol art injected as game assets
- Paytable and reel strips from the math model's CSV output
- Bet controls, balance tracking, win detection
- ARKAINBRAIN info bar showing RTP, volatility, and features

## API Keys

| Key | Required | Purpose |
|-----|----------|---------|
| `OPENAI_API_KEY` | Yes | GPT-5 reasoning agents, DALL-E 3 art, Vision QA |
| `SERPER_API_KEY` | Yes | Web search, patent search, trend radar, competitor teardown |
| `ELEVENLABS_API_KEY` | Optional | AI sound effect generation (13 core game sounds) |
| `QDRANT_URL` + `QDRANT_API_KEY` | Optional | Vector DB for regulation storage and knowledge base |
| `GOOGLE_CLIENT_ID` + `SECRET` | For web UI | Google OAuth sign-in |

## Model Configuration

Default routing (override via environment variables):

| Tier | Model | Agents | Cost |
|------|-------|--------|------|
| HEAVY | `openai/gpt-5` | Market Analyst, Game Designer, Mathematician, Compliance | $1.25 / $10 per 1M tokens |
| LIGHT | `openai/gpt-5-mini` | Lead Producer, Art Director | $0.25 / $1 per 1M tokens |

Override: `LLM_HEAVY=openai/gpt-5.1` or `LLM_HEAVY=openai/gpt-5.2` in your environment.

## State Recon

Standalone legal research pipeline for US states:

```bash
python main.py --recon "North Carolina"
```

Results are cached in Qdrant and automatically referenced when that state appears as a target jurisdiction in future pipeline runs.

## Deployment

See `RAILWAY_DEPLOY.md` for Railway or `DEPLOY_PYTHONANYWHERE.md` for PythonAnywhere.

## License

Prototype engine uses the [1stake slot machine](https://github.com/1stake/slot-machine-online-casino-game) under MIT license. All other code is proprietary to ArkainGames.
