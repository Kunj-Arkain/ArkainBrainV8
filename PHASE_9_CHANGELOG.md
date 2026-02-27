# PHASE 9: Multi-Variant Generation (Enhanced) — Implementation Complete

## Summary
Transforms the basic variant system (N parallel identical runs) into a **strategic
divergence engine**. Each variant now explores a deliberately different design space
with unique volatility, feature sets, RTP budgets, and target audiences. Adds
LLM-powered strategy generation, visual comparison dashboards with charts, and a
**mix-and-match system** for creating hybrid games from the best parts of each variant.

---

## Architecture

```
User picks "A/B Variants" → variant_count (2-5)
    ↓
Strategy Engine (LLM or template fallback)
    ↓
  Variant A: 🔥 High Vol + Hold-and-Spin (10,000x max, thrill seekers)
  Variant B: 🌊 Cascading (5,000x, regular players)
  Variant C: 🎯 Low Vol + Frequent Features (2,000x, casual/mobile)
  Variant D: 💎 Megaways + Progressive (25,000x, jackpot chasers)
    ↓
Each variant → full pipeline with modified params
    ↓
Comparison Dashboard (server-rendered + React SPA)
    ↓
Mix-and-Match: "A's math + C's design + B's features" → Hybrid game
```

---

## Variant Strategy Engine (flows/variant_strategy.py — 258 lines)

### 7 Predefined Strategy Templates
| # | Icon | Label | Volatility | Max Win | Key Features | Target Audience |
|---|------|-------|-----------|---------|--------------|-----------------|
| 1 | 🔥 | High Vol + Hold-and-Spin | high | 10,000x | hold_and_spin, expanding_wilds | High-roller thrill seekers |
| 2 | 🌊 | Medium Vol + Cascading | medium_high | 5,000x | cascading_reels, multiplier_wilds | Regular players |
| 3 | 🎯 | Low Vol + Frequent Features | low | 2,000x | stacked_wilds, random_wilds, respin | Casual/mobile players |
| 4 | 💎 | Megaways + Progressive | extreme | 25,000x | megaways, progressive_jackpot | Jackpot chasers |
| 5 | 👑 | Premium High RTP | medium | 5,000x | bonus_buy, scatter_pays | Value-conscious experienced |
| 6 | ⚡ | Cluster Pays + Multipliers | medium_high | 8,000x | cluster_pays, cascading_reels | Modern slot enthusiasts |
| 7 | 🎁 | Pick-and-Click Bonus | medium | 3,000x | pick_bonus, gamble_feature | Interactive experience seekers |

### LLM-Powered Creative Divergence
- Uses GPT-4o-mini (configurable) with temperature 0.9 for maximum creativity
- Prompt enforces: unique volatility per variant, different feature sets, different RTP budgets, different max wins (2x spread minimum), different player segments
- Returns structured JSON with label, icon, strategy, volatility, rtp_budget, max_win, features, target_audience
- Automatic fallback to template strategies if LLM unavailable

### RTP Budget Allocation
Each strategy includes a percentage-based RTP budget breakdown:
```
High Vol: 55% base / 15% free spins / 30% hold-and-spin
Cascading: 65% base / 25% cascade multipliers / 10% free spins  
Low Vol: 72% base / 18% free spins / 10% multipliers
Megaways: 58% base / 22% free spins / 20% progressive
```
These budgets are visualized as stacked bars in the comparison dashboard.

---

## Variant Mixer (flows/variant_mixer.py — 256 lines)

### 6 Mixable Component Types
| Type | Icon | What It Contains | Source Directory |
|------|------|-----------------|-----------------|
| Math Model | 🔢 | Paytable, RTP budget, reel strips, simulation config | 03_math |
| Game Design | 🎨 | GDD, theme, art direction, symbol design | 02_design |
| Feature Set | ⚡ | Bonus config, free spins, special mechanics | 03_math |
| Compliance | ⚖️ | Jurisdiction approvals, legal analysis | 05_legal |
| Revenue Model | 💰 | Revenue projections, market analysis | 08_revenue |
| Prototype | 🎮 | HTML5 playable prototype | 06_prototype |

### Hybrid Creation Flow
```
User selects: Math from V1 + Design from V3 + Features from V2
    ↓
create_hybrid() copies directories from each variant
    ↓
HYBRID_MANIFEST.json records provenance
    ↓
GDD gets "Hybrid Provenance" section appended
    ↓
build_hybrid_params() merges pipeline params (RTP from math source, features from features source)
    ↓
New "hybrid" job created with status=complete (files already copied)
```

### Component Detection
`get_variant_components()` scans each variant's output to determine what's available,
returning file counts and summaries (e.g., "RTP: 96.2%" for math components).

---

## Enhanced Comparison Dashboard

### Server-Rendered (`/job/{id}/variants`)
- **Strategy cards** with icon, label, description, target audience
- **RTP budget bars** — stacked horizontal bars showing allocation percentages
- **Metric badges** — RTP, Max Win, Hit Rate, Volatility inline per card
- **Side-by-side table** — 11 metrics across all variants
- **Action links** — View Files, Interactive Review per variant
- **Mix-and-Match UI** — dropdown selectors for each component type → Create Hybrid button
- **Link to React SPA** — "📈 Open Interactive Charts" for full visual comparison

### React SPA (`/job/{id}/variants/compare`)
- **3 tabs**: Strategies, Table, Charts
- **Strategy Cards** — colored left borders, RTP budget stacked bars with legend, audience badges
- **Metric Table** — with "best" badges (green pill) on winning metrics
- **Bar Charts** — side-by-side bars for RTP, Max Win, Hit Frequency, GDD Words
- **Color-coded** — consistent per-variant colors throughout all views

---

## New API Endpoints (4 new routes)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/variants/{parent_id}/mix` | Create hybrid game from selected components |
| GET | `/api/variants/{parent_id}/components` | Get available components per variant |
| GET | `/job/{id}/variants/compare` | React SPA comparison dashboard |
| POST | `/api/variants/preview-strategies` | Preview strategies before launching |

---

## Files Created/Modified

```
NEW:  flows/variant_strategy.py               (258 lines) — Strategy engine with 7 templates + LLM
NEW:  flows/variant_mixer.py                  (256 lines) — Mix-and-match hybrid creator
NEW:  static/review-app/variant-compare.html  (206 lines) — React SPA comparison dashboard
EDIT: web_app.py                              (~200 lines changed) — Enhanced comparison page,
                                                4 new routes, strategy engine integration,
                                                mix-and-match UI, React SPA serving
```

**Total new code: ~720 lines (new files) + ~200 lines (web_app changes)**

---

## Variant Launch Flow (Updated)

### Before (Phase pre-9)
```
User brief → 5 hardcoded strategies (Conservative/Aggressive/Hybrid/Premium/Jackpot)
           → Simple vol/rtp/maxwin adjustments → N parallel identical pipeline runs
```

### After (Phase 9)
```
User brief → Strategy Engine analyzes theme + base params
           → LLM generates N creative divergent strategies (or template fallback)
           → Each strategy gets: unique volatility, feature set, RTP budget, max win, audience
           → build_variant_params() creates fully differentiated pipeline params
           → Strategy context injected into pipeline agents' special_requirements
           → N parallel pipeline runs with truly different design philosophies
```

---

## Mix-and-Match Flow

1. All variants must be `complete` status
2. User sees 6 component dropdowns (math, design, features, compliance, revenue, prototype)
3. Each dropdown lists all completed variants with icon + label
4. User picks best-of-breed: "Math from 🔥 High Vol, Design from 🎯 Low Vol"
5. Click "🧬 Create Hybrid Game" → `create_hybrid()`:
   - Copies selected directories from source variants
   - Writes HYBRID_MANIFEST.json with provenance
   - Appends provenance section to GDD
   - Creates job with status=complete (files already merged)
6. Redirect to hybrid job files page

---

## Next: Phase 10 — Export Pipeline (Production-Grade)
