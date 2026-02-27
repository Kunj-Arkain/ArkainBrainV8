# PHASE 7: Mini RMG Game Pipeline — Implementation Complete

## Summary
A second pipeline type alongside "Slot Pipeline" — focused on Real Money Gaming
mini-games. Produces playable HTML5 games with provably fair math, optional Web3
smart contracts, and full compliance checks. 8 game types supported.

---

## Architecture

```
User picks game type (crash/plinko/mines/etc.)
    ↓
Math Engine → generate_config() → simulate(500K rounds) → verify HE accuracy
    ↓
Game Design → LLM generates theme/colors/animations (fallback: template)
    ↓
HTML5 Builder → Self-contained playable game (Canvas + Web Audio + Provably Fair)
    ↓
Compliance → HE accuracy, hit rate, max mult cap, sim confidence
    ↓
[Optional] Web3 → Solidity contract + Chainlink VRF + deploy scripts
    ↓
Package → MANIFEST.json + all files + pipeline memory indexing
```

---

## 8 Game Engines with Verified Math

| Game | Engine | Theoretical HE | Simulated HE | RTP | Status |
|------|--------|----------------|--------------|-----|--------|
| Crash | Exponential (inverse CDF) | 3.00% | 2.93% | 97.07% | ✅ |
| Plinko | Binomial (8/12/16 rows × 3 risk levels) | 2.06% | 1.62% | 98.38% | ✅ |
| Mines | Combinatorial (nCk survival) | 3.00% | 2.87% | 97.13% | ✅ |
| Dice | Uniform threshold | 1.00% | 0.99% | 99.01% | ✅ |
| Wheel | Weighted segments | 5.00% | 4.41% | 95.59% | ✅ |
| Hi-Lo | Card probability + tie edge | 10.46% | 10.68% | 89.32% | ✅ |
| Chicken | Sequential survival | 3.00% | 2.46% | 97.54% | ✅ |
| Scratch | Prize distribution table | 14.96% | 15.24% | 84.76% | ✅ |

All engines verified at 100K+ rounds with <2% deviation from theoretical.

---

## Playable HTML5 Games

Each game type generates a **self-contained single-file HTML** (10-13KB) with:
- **Canvas rendering** with game-specific UI (crash curve, plinko board, mine grid, etc.)
- **Provably fair** — SHA-256(server_seed:client_seed:nonce) with verification panel
- **Bet controls** — configurable bet amounts, one-click play
- **Sound effects** — Web Audio API (no external dependencies)
- **Touch-friendly** — mobile responsive, viewport-locked
- **History panel** — last 50 rounds with win/loss indicators
- **Balance tracking** — simulated $1,000 starting balance

### Game-Specific Features
- **Crash**: Real-time multiplier counter, cash-out button
- **Plinko**: Peg board visualization, slot multiplier display
- **Mines**: Grid reveal with gem/mine animations, incremental cash-out
- **Dice**: Roll bar with target marker, instant roll display
- **Wheel**: Animated spin with segment highlighting
- **Hi-Lo**: Card display with higher/lower/cash-out buttons
- **Chicken**: Lane-by-lane crossing with hazard reveals
- **Scratch**: 3×3 scratch-to-reveal grid

---

## Web3 Output (Optional)

When "Web3 Mode" is enabled, generates:

| File | Description |
|------|-------------|
| `{Name}Game.sol` | Solidity contract with Chainlink VRF v2 integration |
| `deploy.js` | Hardhat deployment script (Sepolia + mainnet) |
| `hardhat.config.js` | Hardhat configuration |
| `connector.js` | Frontend ethers.js connector class |
| `package.json` | Node.js dependencies |
| `README.md` | Setup guide + **audit requirements** (clearly labeled) |

**Security notice**: All contracts are labeled as unaudited templates requiring
professional security review before mainnet deployment.

---

## Pipeline Flow

### Mini RMG Pipeline (flows/mini_rmg_pipeline.py)
6 stages, fully automated:

1. **Math Model** — Engine generates config, runs 500K-round Monte Carlo
2. **Game Design** — LLM designs theme/UI (GPT-5-mini) with template fallback
3. **Playable Build** — HTML5 game generated from design + config
4. **Compliance** — 5 automated checks (HE accuracy, hit rate, max mult, provably fair, sample size)
5. **Web3** (optional) — Solidity + deploy scripts
6. **Package** — Manifest, memory indexing, email notification

---

## New Files (18 files, 2,210 lines)

```
NEW:  flows/mini_rmg_pipeline.py          (382 lines) — Full pipeline flow
NEW:  sim_engine/rmg/__init__.py          (42 lines)  — Engine registry
NEW:  sim_engine/rmg/base.py              (151 lines) — Abstract base + SimResult
NEW:  sim_engine/rmg/crash.py             (45 lines)  — Exponential crash
NEW:  sim_engine/rmg/plinko.py            (81 lines)  — Binomial pegs
NEW:  sim_engine/rmg/mines.py             (58 lines)  — Combinatorial mines
NEW:  sim_engine/rmg/dice.py              (50 lines)  — Uniform threshold
NEW:  sim_engine/rmg/wheel.py             (53 lines)  — Weighted segments
NEW:  sim_engine/rmg/hilo.py              (73 lines)  — Card probability
NEW:  sim_engine/rmg/chicken.py           (53 lines)  — Sequential survival
NEW:  sim_engine/rmg/scratch.py           (53 lines)  — Prize distribution
NEW:  templates/rmg/__init__.py           (1 line)
NEW:  templates/rmg/builder.py            (767 lines) — HTML5 game generator (all 8 types)
NEW:  templates/web3/__init__.py          (1 line)
NEW:  templates/web3/generator.py         (402 lines) — Solidity + deploy scripts
EDIT: worker.py                           (+44 lines) — mini_rmg job dispatch
EDIT: web_app.py                          (+108 lines) — Form page, launch route, dashboard card, nav
```

---

## Web UI

### Dashboard
New action card: **🎮 Mini RMG Game** — "Crash, Plinko, Mines → playable HTML5"
(Between "New Slot Pipeline" and "State Recon")

### `/mini-rmg` Form Page
- 8 game type cards with icons, descriptions, and house edge ranges
- Radio select (visual cards, not dropdown)
- Theme/name input
- House edge % (0.5–40%)
- Max multiplier (10–100,000)
- Web3 mode checkbox
- One-click launch → redirects to live log stream

### Nav
Added 🎮 Mini RMG between "New Pipeline" and "State Recon"

### API
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/mini-rmg` | Game creation form |
| POST | `/api/mini-rmg` | Launch mini RMG pipeline job |

---

## Base Engine Features

All 8 engines inherit from `BaseRMGEngine`:
- `generate_config(**kwargs)` → game-specific configuration dict
- `compute_house_edge(config)` → theoretical house edge
- `simulate_round(config, rng)` → single round return multiplier
- `simulate(config, rounds, seed)` → full Monte Carlo with SimResult
- `provably_fair_hash(server_seed, client_seed, nonce)` → SHA-256
- `hash_to_float(hash_hex)` → deterministic float from hash
- `get_metadata()` → game type info for UI/API

`SimResult` dataclass includes: house_edge (theoretical + measured), RTP,
avg/max multiplier, hit rate, 95% confidence interval, distribution buckets.

---

## Next: Phase 8 — Interactive Review UI
