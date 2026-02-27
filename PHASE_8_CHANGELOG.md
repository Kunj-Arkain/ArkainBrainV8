# PHASE 8: Interactive Review UI — Implementation Complete

## Summary
Replaces the basic approve/reject review flow with a full interactive review
system featuring section-by-section GDD editing, inline paytable editing with
RTP recalculation, threaded comments, per-section approvals, OODA revision
diffs, and a comprehensive simulation dashboard. Built as a React SPA served
from Flask with server-rendered data injection.

---

## Architecture

```
/review/{job_id}/interactive
    ↓
Flask reads job output → parses GDD sections, paytable, sim results, diffs
    ↓
Injects JSON data into React SPA template
    ↓
React renders 5 tabs: Overview, GDD Editor, Paytable, Diffs, Files
    ↓
User edits trigger API calls → backend updates files + returns new RTP
```

---

## React SPA Components

### SimDashboard
- **RTP gauge** — large numeric display with color-coded tolerance indicator
- **Delta badge** — shows ±% from target with ✅/⚠️/❌ status
- **Stat pills** — hit rate, max win, volatility index, total spins
- **Progress bar** — visual RTP gauge from 0-100%

### GDDEditor
- **Section-by-section view** — collapsible sections parsed from `## ` headers
- **Inline editing** — toggle edit mode per section with textarea + save
- **Per-section approval** — ✅ Approve / 🔄 Request Changes buttons
- **Approval badges** — color-coded status (approved/pending/changes requested)
- **Section border coloring** — green for approved, red for changes requested
- **Threaded comments** — per-section comment input with real-time posting
- **Word count** — shown for each section

### PaytableEditor
- **Spreadsheet grid** — all symbols × pay columns rendered as editable inputs
- **Inline editing** — edit any cell, blur triggers PATCH to backend
- **RTP indicator** — live stat pill showing current RTP + delta
- **Edited cell highlighting** — purple border on modified cells
- **Warning display** — shows tolerance warnings from RTP estimate

### DiffViewer
- **Line-by-line diff** — simple but effective add/delete/context rendering
- **Color coding** — green for additions, red for deletions
- **File headers** — directory/filename with diff type labels
- **Adversarial review support** — shows adversarial review files as diffs
- **Scroll containment** — max 300px height per diff panel

### FileBrowser
- **Extension filter** — clickable buttons to filter by file type
- **File count badges** — per-extension counts
- **Monospace paths** — clean file listing with sizes
- **100-file cap** — performance protection for large outputs

---

## Backend API (13 new endpoints)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/review/{job_id}/interactive` | Serve React SPA with injected data |
| GET | `/api/review/{job_id}/data` | Review data as JSON (for refresh) |
| POST | `/api/review/{job_id}/comment` | Add a threaded comment |
| GET | `/api/review/{job_id}/comments` | Get all comments (optional section filter) |
| POST | `/api/review/{job_id}/comment/{id}/resolve` | Mark comment resolved |
| POST | `/api/review/{job_id}/section-approval` | Set section approval status |
| GET | `/api/review/{job_id}/section-approvals` | Get all section approvals |
| PATCH | `/api/review/{job_id}/paytable` | Edit a paytable cell |
| GET | `/api/review/{job_id}/rtp-estimate` | Get current RTP estimate |
| PATCH | `/api/review/{job_id}/gdd-section` | Edit GDD section content |
| GET | `/api/review/{job_id}/gdd-sections` | Get parsed GDD sections |
| GET | `/api/review/{job_id}/diffs` | Get OODA revision diffs |
| POST | `/api/review/{job_id}/bulk-approve` | Approve all sections + continue pipeline |

---

## Backend Logic (api/review_routes.py — 395 lines)

### GDD Operations
- `parse_gdd_sections()` — splits markdown on `## ` headers into sections with IDs, word counts
- `save_gdd_section()` — updates a section in the GDD file, creates timestamped backup

### Paytable Operations
- `load_paytable()` — reads paytable.json or paytable.csv from output
- `save_paytable()` — writes back with backup
- `update_paytable_cell()` — updates a single symbol/count/pay value
- `quick_rtp_estimate()` — returns RTP from simulation results with delta/warning

### Comments & Approvals
- `add_comment()` — threaded comments with author, parent_id support
- `get_comments()` — filtered by job and optional section
- `resolve_comment()` — marks resolved
- `set_section_approval()` — upsert with ON CONFLICT handling
- `get_section_approvals()` — all approvals for a job

### Diff Generation
- `get_ooda_diff()` — finds backup files and generates simple line diffs
- Supports adversarial review file detection

### Data Assembly
- `build_review_data()` — aggregates all data for the SPA (sections, paytable, sim, diffs, files)

---

## Database Schema (2 new tables)

### review_comments
- id, review_id, job_id, section, author, content, parent_id, resolved, created_at
- Indexes on job_id and section

### section_approvals
- id, job_id, section, status, reviewer, role, feedback, updated_at
- Unique constraint on (job_id, section, reviewer) for upsert
- Indexes on job_id

---

## UI Integration

### Job Files Page
- New **📋 Interactive Review** button (purple accent) next to Iterate button
- Only shown for completed pipeline/iterate/variant jobs

### Simple Review Page
- Added **📋 Open Interactive Review (Phase 8)** link
- Links to `/review/{job_id}/interactive`

### Reviews List
- Existing pending/resolved review system unchanged
- Interactive review accessible from any completed job

---

## Files Created/Modified

```
NEW:  api/__init__.py                        (1 line)
NEW:  api/review_routes.py                  (395 lines) — Backend review logic
NEW:  static/review-app/index.html          (441 lines) — React SPA
EDIT: config/database.py                    (+32 lines) — 2 new tables
EDIT: web_app.py                            (+195 lines) — 13 API routes + UI links
```

**Total new code: ~1,063 lines**

---

## How It Works

### First Review
1. User completes a pipeline → job has output_dir with GDD, paytable, sim results
2. User clicks **📋 Interactive Review** on the job files page
3. Flask reads all output files, parses GDD into sections
4. React SPA renders with 5 tabs: Overview, GDD, Paytable, Diffs, Files
5. User can:
   - Edit GDD sections inline (with auto-backup)
   - Edit paytable cells (with RTP recalculation)
   - Approve/request changes per section
   - Add threaded comments on any section
   - View OODA loop revision diffs
   - Browse all output files
6. **Approve All** → marks all sections approved, resolves pending HITL reviews

### Data Flow
```
User edits paytable cell → PATCH /api/review/{id}/paytable
    → Backend updates paytable.json (with backup)
    → Returns updated cell + new RTP estimate
    → Frontend updates RTP gauge + delta indicator
```

---

## Next: Phase 9 — Multi-Variant Generation (Enhanced)
