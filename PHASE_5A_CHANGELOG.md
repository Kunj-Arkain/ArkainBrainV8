# PHASE 5A: Infrastructure & Railway Pro — Implementation Complete

## GPT-5 Tier 3 Optimization
- **MAX_CONCURRENT_JOBS=6** (up from 3) — Tier 3 provides 800K+ TPM for gpt-5, 2M+ TPM for gpt-5-mini
- All 6 agents run on HEAVY (gpt-5) without rate-limit contention
- Pipeline timeout configurable via `PIPELINE_TIMEOUT_SECONDS` env var

---

## ✅ Infrastructure (Already Implemented in Prior Sprint)

### PostgreSQL + Connection Pooling (`config/database.py`)
- Dual-mode: SQLite (local dev) ↔ PostgreSQL (Railway production)
- Auto-detects via `DATABASE_URL` env var
- `psycopg3` with connection pool (min=2, max=20)
- Unified `DatabaseConnection` wrapper normalizes `?` vs `%s` placeholders
- Worker-safe helpers: `worker_update_job()`, `worker_query()`

### Redis/RQ Job Queue (`config/database.py`)
- `enqueue_job()` dispatches to Redis/RQ when available
- Automatic subprocess fallback when Redis unavailable
- Separate queues: `arkainbrain` (pipelines), `arkainbrain:sim` (simulations)
- Job timeout 5400s, dead-letter queue support

### SQLite → PostgreSQL Migration (`migrations/001_sqlite_to_pg.py`)
- Idempotent migration script (safe to run multiple times)
- Migrates users, jobs, reviews tables
- Dry-run mode: `python migrations/001_sqlite_to_pg.py --dry-run`
- Preserves all existing data with `ON CONFLICT DO NOTHING`

### Docker Compose (`deploy/docker-compose.yml`)
- 4-service local dev stack: web, worker, sim-runner, postgres, redis
- Uses `pgvector/pgvector:pg16` for vector search readiness
- Shared volume for output files

---

## ✅ New in This Sprint

### 1. Sim-Runner Service Config (`deploy/railway-sim.toml`)
- Dedicated Monte Carlo simulation service
- 4 vCPU / 8 GB RAM, auto-scales 1→10 replicas
- Listens on `arkainbrain:sim` Redis queue
- Ready for Phase 5B validated simulation engine

### 2. ZIP Download (`GET /job/{id}/download-zip`)
- Streams entire job output folder as ZIP
- Safe filename generation from job title
- ZIP_DEFLATED compression
- Already wired into file browser with "ZIP ↓" buttons

### 3. File Search (`GET /files?q=...&ext=...`)
- Full-text search across ALL job outputs by filename/path
- Extension filter quick-links: PDF, JSON, HTML, CSV, Images, Audio
- Combined search + filter (e.g., `?q=paytable&ext=json`)
- Results show parent job context
- Capped at 200 results for performance

### 4. File Tagging API
- `POST /api/files/tag` — tag any file with custom labels
- `DELETE /api/files/tag` — remove a tag
- `GET /api/job/{id}/tags` — list all tags for a job's files
- Tags stored in `file_tags` table (already in schema)
- Tags visible inline in file browser

### 5. Favorites/Pin System
- `POST /api/files/favorites` — toggle favorite on any file
- Implemented as special "favorite" tag in file_tags table
- ★ star icon in file browser (gold when favorited)
- One-click toggle

### 6. Inline File Preview Panel
- `GET /job/{id}/preview/{path}` — returns rendered HTML preview
- Split-panel layout: file list (left) + preview (right)
- Supported preview types:
  - **Images** (png, jpg, gif, svg, webp): inline `<img>` with border
  - **PDF**: embedded `<iframe>` viewer
  - **HTML**: sandboxed `<iframe>` (prototypes render live)
  - **JSON**: syntax-highlighted `<pre>` block (up to 50KB)
  - **CSV**: formatted HTML table (up to 50 rows)
  - **Audio** (mp3, wav): `<audio>` player
  - **Code/Text** (py, js, md, txt, etc.): monospace `<pre>` block
  - **Other**: download button with file info

### 7. Bulk Select + Download
- Checkbox on every file row
- "Select all" toggle button
- Selection counter ("3 selected")
- `POST /api/job/{id}/bulk-zip` — ZIP only selected files
- Client-side blob download (no page reload)

### 8. Sort & Filter Controls
- In-browser sort: A→Z (name), Size, Type
- Extension filter buttons with active state highlighting
- JavaScript-based (no page reload) for instant response

### 9. Enhanced File Row Design
- File type icons (📄 PDF, 📋 JSON, 🌐 HTML, 🖼️ images, etc.)
- Folder path shown as subdued subtext
- Inline tag badges (purple pills)
- Favorite star with gold active state
- Click-to-preview on any row
- Selected row highlight (purple left border)

### 10. Settings Page — 3-Service Architecture Display
- Visual grid showing web, worker, sim-runner services
- Resource allocation per service (vCPU, RAM, replicas)
- GPT-5 Tier 3 label with 800K+ TPM note
- Feature list updated with new Phase 5A capabilities

---

## Railway Pro Resource Allocation

| Service | vCPU | RAM | Replicas | Config File |
|---------|------|-----|----------|-------------|
| `web` | 2 | 4 GB | 2 | `deploy/railway-web.toml` |
| `worker` | 8 | 16 GB | 1→5 (auto) | `deploy/railway-worker.toml` |
| `sim-runner` | 4 | 8 GB | 1→10 (auto) | `deploy/railway-sim.toml` |
| PostgreSQL | managed | managed | 1 | Railway add-on |
| Redis | managed | managed | 1 | Railway add-on |

---

## Files Changed

```
EDIT:  web_app.py                         (+362 lines)  — 7 new API routes, preview endpoint, enhanced file browser
EDIT:  config/settings.py                 (comments)    — Tier 3 rate limit documentation
EDIT:  .env.example                       (+2 lines)    — PIPELINE_TIMEOUT_SECONDS
EDIT:  deploy/docker-compose.yml          (+18 lines)   — sim-runner service
NEW:   deploy/railway-sim.toml            (21 lines)    — sim-runner Railway config
```

No changes to: `config/database.py`, `worker.py`, `migrations/001_sqlite_to_pg.py` (already complete)

---

## New API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/job/{id}/download-zip` | Stream job output as ZIP |
| POST | `/api/files/tag` | Tag a file |
| DELETE | `/api/files/tag` | Remove a tag |
| GET | `/api/job/{id}/tags` | List tags for a job |
| POST | `/api/files/favorites` | Toggle file favorite |
| GET | `/job/{id}/preview/{path}` | Inline file preview HTML |
| POST | `/api/job/{id}/bulk-zip` | ZIP selected files |

---

## Next: Phase 5B — Validated Simulation Engine
The sim-runner service is deployed and ready. Phase 5B will add:
- `sim_engine/` directory with hardened Monte Carlo evaluator
- JSON config schema (agent output → engine input)
- Reference game validation suite (Starburst, Book of Dead, etc.)
- Confidence intervals + convergence analysis
- REST API on sim-runner for instant RTP recalculation
