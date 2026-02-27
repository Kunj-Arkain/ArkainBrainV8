# 🎰 Automated Slot Studio — PythonAnywhere Deployment Guide

## What You Need Before Starting

- **PythonAnywhere account** — Paid plan required (Hacker at $5/mo minimum; Battery at $12/mo recommended for more CPU and outbound network)
- **OpenAI API key** — For GPT-5 models and DALL-E 3
- **Serper API key** — For web search (free tier: 2,500 searches/mo at serper.dev)
- **The slot-studio.zip file** you just downloaded

> **Why paid plan?** Free PythonAnywhere accounts cannot make outbound HTTP requests (no API calls to OpenAI, no web scraping). You need at least the Hacker plan.

---

## PART 1: ACCOUNT & ENVIRONMENT SETUP

### Step 1: Create Your PythonAnywhere Account

1. Go to **https://www.pythonanywhere.com**
2. Click **"Pricing & signup"**
3. Sign up for the **Hacker** ($5/mo) or **Battery** ($12/mo) plan
   - Battery gives you more CPU seconds (useful for Monte Carlo simulations)
4. Verify your email and log in

### Step 2: Upload the Project

1. From your PythonAnywhere dashboard, click the **"Files"** tab
2. You'll see your home directory: `/home/yourusername/`
3. Click **"Upload a file"** and upload `slot-studio.zip`
4. Now open a **Bash console** (Dashboard → "Consoles" → "$ Bash")
5. Run these commands:

```bash
# Navigate to your home directory
cd ~

# Unzip the project
unzip slot-studio.zip

# Verify the contents
ls slot-studio/
# You should see: main.py  config/  flows/  models/  tools/  templates/  examples/  etc.
```

### Step 3: Set Up Python Virtual Environment

PythonAnywhere has Python pre-installed, but you need a virtual environment for your dependencies.

```bash
# Create a virtual environment with Python 3.10+
mkvirtualenv slot-studio --python=/usr/bin/python3.10

# The virtualenv should activate automatically. If not:
workon slot-studio

# Verify you're in the virtualenv (should show the venv path)
which python
# Output should be: /home/yourusername/.virtualenvs/slot-studio/bin/python
```

### Step 4: Install Dependencies

```bash
# Make sure you're in the project directory
cd ~/slot-studio

# Upgrade pip first
pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt

# This will take 2-5 minutes. You'll see a lot of output.
# If any package fails, install it individually:
# pip install crewai[tools]
# pip install openai
# etc.
```

**If you get errors with crewai:**
```bash
# CrewAI sometimes needs specific versions. Try:
pip install crewai==0.80.0 crewai-tools==0.14.0

# If still failing, install the core first, then tools:
pip install crewai
pip install crewai-tools
```

### Step 5: Configure Environment Variables

```bash
# Copy the template
cp .env.example .env

# Edit the file
nano .env
```

In the nano editor, update these values:

```
OPENAI_API_KEY=sk-your-actual-openai-key-here
SERPER_API_KEY=your-actual-serper-key-here
DALLE_API_KEY=sk-your-actual-openai-key-here
HITL_ENABLED=false
OUTPUT_DIR=./output
LOG_LEVEL=INFO
```

> **Important:** Set `HITL_ENABLED=false` for now since PythonAnywhere scheduled tasks and web apps can't do interactive prompts. You'll add a web-based HITL later.

Save the file: `Ctrl+O`, then `Enter`, then `Ctrl+X` to exit nano.

**Alternatively, you can set environment variables directly:**
```bash
# Add to your virtualenv's postactivate script
echo 'export OPENAI_API_KEY="sk-your-key-here"' >> ~/.virtualenvs/slot-studio/bin/postactivate
echo 'export SERPER_API_KEY="your-serper-key"' >> ~/.virtualenvs/slot-studio/bin/postactivate

# Reload the environment
deactivate
workon slot-studio
```

---

## PART 2: TEST RUN (COMMAND LINE)

### Step 6: Run Your First Test

```bash
# Make sure you're in the right directory and virtualenv
cd ~/slot-studio
workon slot-studio

# Run with the example Egyptian game in auto mode (no HITL pauses)
python main.py --from-json examples/egyptian_curse.json --auto
```

**What you should see:**
- Rich-formatted output showing the pipeline stages
- The Orchestrator dispatching tasks to agents
- Market research running (web searches)
- GDD being authored
- Math simulation executing
- Art generation (DALL-E calls)
- Compliance review
- Final package assembly

**If it works**, you'll get output in `~/slot-studio/output/<game_slug>/`

### Step 7: Troubleshoot Common Issues

**"No module named 'crewai'"**
```bash
workon slot-studio
pip install crewai[tools]
```

**"Connection refused" or network errors**
- You need a paid PythonAnywhere plan for outbound requests
- Check your plan: Dashboard → Account → Subscription

**"Rate limit exceeded" (OpenAI)**
- You've hit your OpenAI API rate limit
- Check your usage at https://platform.openai.com/usage
- Consider adding a retry mechanism or rate limiting

**"SERPER_API_KEY not configured"**
```bash
# Verify your .env file has the key
cat .env | grep SERPER
# If missing, add it
echo 'SERPER_API_KEY=your-key-here' >> .env
```

**Simulation timeout**
- PythonAnywhere Bash consoles have CPU limits
- Reduce simulation spins for testing:
```bash
# Edit config/settings.py temporarily
nano config/settings.py
# Change SIMULATION_SPINS = 1_000_000 to SIMULATION_SPINS = 100_000
```

---

## PART 3: WEB INTERFACE (FLASK APP)

Running from the command line works, but you'll want a web interface to submit game ideas and monitor pipeline progress. Here's how to set up a Flask frontend.

### Step 8: Create the Flask Web App

```bash
cd ~/slot-studio

# Install Flask (if not already installed)
pip install flask flask-socketio
```

Now create the web app file:

```bash
nano web_app.py
```

Paste this entire file:

```python
"""
Automated Slot Studio - Web Interface

A Flask app that provides:
- Game idea submission form
- Pipeline status monitoring
- Output package browsing and download
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Track running pipelines
pipeline_jobs = {}

# ============================================================
# HTML Template (single-file for simplicity)
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎰 Automated Slot Studio</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, system-ui, sans-serif;
            background: #0f0f1a; color: #e2e8f0;
            min-height: 100vh; padding: 24px;
        }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { font-size: 28px; text-align: center; margin-bottom: 8px;
             background: linear-gradient(135deg, #6366f1, #ec4899);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { text-align: center; color: #64748b; margin-bottom: 32px; font-size: 14px; }
        .card {
            background: #1a1a2e; border-radius: 12px; padding: 24px;
            margin-bottom: 20px; border: 1px solid #334155;
        }
        .card h2 { font-size: 18px; color: #6366f1; margin-bottom: 16px; }
        label { display: block; font-size: 13px; color: #94a3b8;
                margin-bottom: 4px; font-weight: 600; }
        input, select, textarea {
            width: 100%; padding: 10px 14px; border-radius: 8px;
            border: 1px solid #334155; background: #0f0f1a;
            color: #e2e8f0; font-size: 14px; margin-bottom: 14px;
        }
        textarea { min-height: 80px; resize: vertical; }
        .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
        button {
            width: 100%; padding: 14px; border-radius: 10px;
            border: none; cursor: pointer; font-size: 16px; font-weight: 700;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: white; transition: opacity 0.2s;
        }
        button:hover { opacity: 0.9; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .status-card {
            background: #1a1a2e; border-radius: 12px; padding: 20px;
            border: 1px solid #334155; margin-bottom: 12px;
        }
        .status-running { border-color: #f59e0b; }
        .status-complete { border-color: #10b981; }
        .status-failed { border-color: #ef4444; }
        .badge {
            display: inline-block; padding: 3px 10px; border-radius: 20px;
            font-size: 11px; font-weight: 700; text-transform: uppercase;
        }
        .badge-running { background: #f59e0b20; color: #f59e0b; }
        .badge-complete { background: #10b98120; color: #10b981; }
        .badge-failed { background: #ef444420; color: #ef4444; }
        .log { background: #0f0f1a; border-radius: 8px; padding: 12px;
               font-family: monospace; font-size: 12px; color: #64748b;
               max-height: 200px; overflow-y: auto; margin-top: 12px; }
        a { color: #6366f1; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .file-list { list-style: none; padding: 0; }
        .file-list li { padding: 6px 0; border-bottom: 1px solid #1e1e2e; font-size: 13px; }
        .section-divider { border: 0; border-top: 1px solid #334155; margin: 24px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎰 Automated Slot Studio</h1>
        <p class="subtitle">AI-Powered Slot Game Development Pipeline</p>

        <!-- Submit New Game -->
        <div class="card">
            <h2>🎯 New Game Idea</h2>
            <form id="gameForm">
                <label>Theme / Concept *</label>
                <textarea name="theme" placeholder="e.g., Ancient Egypt - Curse of the Pharaoh with a dark, mystical twist..." required></textarea>

                <div class="row">
                    <div>
                        <label>Target Markets *</label>
                        <input name="markets" value="UK, Malta, Ontario" placeholder="UK, Malta, Ontario, NJ">
                    </div>
                    <div>
                        <label>Volatility</label>
                        <select name="volatility">
                            <option value="low">Low</option>
                            <option value="medium_low">Medium-Low</option>
                            <option value="medium">Medium</option>
                            <option value="medium_high">Medium-High</option>
                            <option value="high" selected>High</option>
                        </select>
                    </div>
                </div>

                <div class="row3">
                    <div>
                        <label>Target RTP %</label>
                        <input name="target_rtp" type="number" step="0.1" value="96.5" min="75" max="99">
                    </div>
                    <div>
                        <label>Grid Config</label>
                        <input name="grid" value="5x3" placeholder="5x3, 6x4, etc.">
                    </div>
                    <div>
                        <label>Max Win (x)</label>
                        <input name="max_win" type="number" value="5000" min="100">
                    </div>
                </div>

                <div class="row">
                    <div>
                        <label>Ways / Lines</label>
                        <input name="ways" value="243 ways" placeholder="243 ways, 25 lines, megaways">
                    </div>
                    <div>
                        <label>Art Style</label>
                        <input name="art_style" value="Dark, cinematic, AAA quality">
                    </div>
                </div>

                <label>Features (comma-separated)</label>
                <input name="features" value="free_spins, multipliers, expanding_wilds"
                       placeholder="free_spins, multipliers, expanding_wilds, cascading_reels">

                <label>Competitor References (comma-separated)</label>
                <input name="competitors" placeholder="Book of Dead, Legacy of Dead, Eye of Horus">

                <label>Special Requirements</label>
                <textarea name="special" placeholder="Any specific mechanics, constraints, or creative direction..."></textarea>

                <br>
                <button type="submit" id="submitBtn">🚀 Launch Pipeline</button>
            </form>
        </div>

        <!-- Active & Recent Jobs -->
        <div class="card">
            <h2>📊 Pipeline Jobs</h2>
            <div id="jobsList">
                <p style="color: #475569; font-size: 13px;">No jobs yet. Submit a game idea to get started.</p>
            </div>
        </div>
    </div>

    <script>
        const form = document.getElementById('gameForm');
        const jobsList = document.getElementById('jobsList');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('submitBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Launching...';

            const formData = new FormData(form);
            const data = Object.fromEntries(formData);

            try {
                const resp = await fetch('/api/launch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                const result = await resp.json();
                if (result.status === 'launched') {
                    btn.textContent = '✅ Launched!';
                    setTimeout(() => { btn.disabled = false; btn.textContent = '🚀 Launch Pipeline'; }, 2000);
                    refreshJobs();
                } else {
                    btn.textContent = '❌ Error: ' + (result.error || 'Unknown');
                    setTimeout(() => { btn.disabled = false; btn.textContent = '🚀 Launch Pipeline'; }, 3000);
                }
            } catch (err) {
                btn.textContent = '❌ Network Error';
                setTimeout(() => { btn.disabled = false; btn.textContent = '🚀 Launch Pipeline'; }, 3000);
            }
        });

        async function refreshJobs() {
            try {
                const resp = await fetch('/api/jobs');
                const jobs = await resp.json();
                if (jobs.length === 0) {
                    jobsList.innerHTML = '<p style="color: #475569; font-size: 13px;">No jobs yet.</p>';
                    return;
                }
                jobsList.innerHTML = jobs.map(job => `
                    <div class="status-card status-${job.status}">
                        <div style="display:flex; justify-content:space-between; align-items:center">
                            <strong>${job.theme}</strong>
                            <span class="badge badge-${job.status}">${job.status}</span>
                        </div>
                        <div style="font-size:12px; color:#64748b; margin-top:6px">
                            Started: ${job.started_at || 'N/A'}
                            ${job.output_dir ? ' | <a href="/browse/' + job.job_id + '">Browse Output</a>' : ''}
                        </div>
                        ${job.current_stage ? '<div style="font-size:12px; color:#f59e0b; margin-top:4px">Stage: ' + job.current_stage + '</div>' : ''}
                        ${job.error ? '<div style="font-size:12px; color:#ef4444; margin-top:4px">Error: ' + job.error + '</div>' : ''}
                    </div>
                `).join('');
            } catch (err) {
                console.error('Failed to refresh jobs:', err);
            }
        }

        // Poll for updates every 5 seconds
        setInterval(refreshJobs, 5000);
        refreshJobs();
    </script>
</body>
</html>
"""


# ============================================================
# Routes
# ============================================================

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/launch", methods=["POST"])
def launch_pipeline():
    """Launch a new pipeline job in a background thread."""
    try:
        data = request.json

        # Parse form data
        theme = data.get("theme", "").strip()
        if not theme:
            return jsonify({"status": "error", "error": "Theme is required"}), 400

        markets = [m.strip() for m in data.get("markets", "UK, Malta").split(",")]
        features = [f.strip() for f in data.get("features", "free_spins").split(",") if f.strip()]
        competitors = [c.strip() for c in data.get("competitors", "").split(",") if c.strip()]

        grid = data.get("grid", "5x3")
        try:
            cols, rows = grid.lower().split("x")
            cols, rows = int(cols), int(rows)
        except ValueError:
            cols, rows = 5, 3

        # Create job
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        job = {
            "job_id": job_id,
            "theme": theme,
            "status": "starting",
            "started_at": datetime.now().isoformat(),
            "current_stage": "Initializing",
            "output_dir": None,
            "error": None,
            "params": {
                "theme": theme,
                "target_markets": markets,
                "volatility": data.get("volatility", "high"),
                "target_rtp": float(data.get("target_rtp", 96.5)),
                "grid_cols": cols,
                "grid_rows": rows,
                "ways_or_lines": data.get("ways", "243 ways"),
                "max_win_multiplier": int(data.get("max_win", 5000)),
                "art_style": data.get("art_style", "Cinematic"),
                "requested_features": features,
                "competitor_references": competitors,
                "special_requirements": data.get("special") or None,
            }
        }

        pipeline_jobs[job_id] = job

        # Launch in background thread
        thread = threading.Thread(
            target=run_pipeline_job,
            args=(job_id,),
            daemon=True
        )
        thread.start()

        return jsonify({"status": "launched", "job_id": job_id})

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/jobs")
def get_jobs():
    """Return all pipeline jobs sorted by most recent."""
    jobs = sorted(
        pipeline_jobs.values(),
        key=lambda j: j.get("started_at", ""),
        reverse=True
    )
    return jsonify(jobs[:20])  # Last 20 jobs


@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    """Return details for a specific job."""
    job = pipeline_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/browse/<job_id>")
def browse_output(job_id):
    """Browse the output directory for a completed job."""
    job = pipeline_jobs.get(job_id)
    if not job or not job.get("output_dir"):
        return "Job not found or not complete", 404

    output_path = Path(job["output_dir"])
    if not output_path.exists():
        return "Output directory not found", 404

    files = []
    for f in sorted(output_path.rglob("*")):
        if f.is_file():
            rel = f.relative_to(output_path)
            files.append({
                "path": str(rel),
                "size": f.stat().st_size,
                "download_url": f"/download/{job_id}/{rel}",
            })

    html = f"""
    <html><head><title>Output: {job['theme']}</title>
    <style>
        body {{ font-family: monospace; background: #0f0f1a; color: #e2e8f0; padding: 24px; }}
        a {{ color: #6366f1; }} h1 {{ font-size: 20px; }}
        .file {{ padding: 6px 0; border-bottom: 1px solid #1e1e2e; }}
        .size {{ color: #64748b; font-size: 12px; }}
    </style></head><body>
    <h1>📦 {job['theme']}</h1>
    <p><a href="/">&larr; Back to Dashboard</a></p><br>
    {''.join(f'<div class="file"><a href="{f["download_url"]}">{f["path"]}</a> <span class="size">({f["size"]:,} bytes)</span></div>' for f in files)}
    </body></html>
    """
    return html


@app.route("/download/<job_id>/<path:filepath>")
def download_file(job_id, filepath):
    """Download a specific output file."""
    job = pipeline_jobs.get(job_id)
    if not job or not job.get("output_dir"):
        return "Not found", 404

    output_path = Path(job["output_dir"])
    return send_from_directory(output_path, filepath)


# ============================================================
# Background Pipeline Runner
# ============================================================

def run_pipeline_job(job_id: str):
    """Run the pipeline in a background thread."""
    job = pipeline_jobs[job_id]

    try:
        from models.schemas import GameIdeaInput, Volatility, FeatureType
        from flows.pipeline import SlotStudioFlow, PipelineState

        job["status"] = "running"
        job["current_stage"] = "Parsing input"

        # Parse features
        features = []
        for f in job["params"]["requested_features"]:
            try:
                features.append(FeatureType(f))
            except ValueError:
                pass  # Skip unknown features

        # Build input
        game_idea = GameIdeaInput(
            theme=job["params"]["theme"],
            target_markets=job["params"]["target_markets"],
            volatility=Volatility(job["params"]["volatility"]),
            target_rtp=job["params"]["target_rtp"],
            grid_cols=job["params"]["grid_cols"],
            grid_rows=job["params"]["grid_rows"],
            ways_or_lines=job["params"]["ways_or_lines"],
            max_win_multiplier=job["params"]["max_win_multiplier"],
            art_style=job["params"]["art_style"],
            requested_features=features,
            competitor_references=job["params"]["competitor_references"],
            special_requirements=job["params"]["special_requirements"],
        )

        # Initialize flow
        initial_state = PipelineState(game_idea=game_idea)
        flow = SlotStudioFlow(auto_mode=True)  # Always auto on web
        flow.state = initial_state

        job["current_stage"] = "Running pipeline"

        # Execute
        final_state = flow.kickoff()

        job["status"] = "complete"
        job["current_stage"] = "Complete"
        job["output_dir"] = getattr(final_state, "output_dir", None)
        job["completed_at"] = datetime.now().isoformat()

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["current_stage"] = "Failed"
        import traceback
        traceback.print_exc()


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    # For local testing only. On PythonAnywhere, use WSGI.
    app.run(debug=True, port=5000)
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### Step 9: Configure PythonAnywhere Web App

1. Go to the **"Web"** tab on your PythonAnywhere dashboard
2. Click **"Add a new web app"**
3. Choose **"Manual configuration"** (NOT Flask — we need more control)
4. Select **Python 3.10**
5. You'll get a web app at: `yourusername.pythonanywhere.com`

### Step 10: Configure the WSGI File

1. On the Web tab, click the link to your **WSGI configuration file**
   (it'll be something like `/var/www/yourusername_pythonanywhere_com_wsgi.py`)
2. **Delete everything** in the file and replace with:

```python
import sys
import os

# Add your project to the path
project_home = '/home/yourusername/slot-studio'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(project_home, '.env'))

# Import the Flask app
from web_app import app as application
```

> **Replace `yourusername`** with your actual PythonAnywhere username in BOTH places.

3. Save the file

### Step 11: Set the Virtual Environment Path

1. Back on the **Web** tab, scroll to the **"Virtualenv"** section
2. Enter: `/home/yourusername/.virtualenvs/slot-studio`
3. Click the checkmark to save

### Step 12: Set the Source Code Directory

1. On the Web tab, in the **"Code"** section
2. Set **Source code** to: `/home/yourusername/slot-studio`
3. Set **Working directory** to: `/home/yourusername/slot-studio`

### Step 13: Reload and Test

1. Click the green **"Reload"** button at the top of the Web tab
2. Visit: `https://yourusername.pythonanywhere.com`
3. You should see the Slot Studio dashboard with the submission form

---

## PART 4: SCHEDULED TASKS (OPTIONAL)

If you want to run pipelines on a schedule or as batch jobs:

### Step 14: Set Up Scheduled Tasks

1. Go to the **"Tasks"** tab on your dashboard
2. Click **"Create a new scheduled task"**
3. Set the time and frequency
4. Command:

```bash
/home/yourusername/.virtualenvs/slot-studio/bin/python /home/yourusername/slot-studio/main.py --from-json /home/yourusername/slot-studio/examples/egyptian_curse.json --auto >> /home/yourusername/slot-studio/pipeline.log 2>&1
```

This runs the pipeline and logs output to `pipeline.log`.

---

## PART 5: QDRANT VECTOR DATABASE (FOR COMPLIANCE RAG)

PythonAnywhere can't run Docker, so you have two options for the vector database:

### Option A: Qdrant Cloud (Recommended)

1. Go to **https://cloud.qdrant.io**
2. Create a free cluster (1GB free tier)
3. Get your **cluster URL** and **API key**
4. Update your `.env`:

```bash
nano ~/slot-studio/.env
```
```
QDRANT_URL=https://your-cluster-id.us-east4-0.gcp.cloud.qdrant.io:6333
QDRANT_API_KEY=your-qdrant-cloud-api-key
```

5. Ingest your regulatory documents:

```bash
cd ~/slot-studio
workon slot-studio

# Create the regulations directory and add your PDFs
mkdir -p data/regulations/gli data/regulations/ukgc data/regulations/mga

# Upload your PDFs via the PythonAnywhere Files tab to these directories
# Then run ingestion:
python -m tools.ingest_regulations --source data/regulations/ --collection slot_regulations
```

### Option B: Skip RAG (Use Static Fallback)

The Compliance Agent has a built-in fallback that uses the static jurisdiction database in `config/settings.py`. This works for basic compliance checks without needing Qdrant at all. The RAG just makes it more thorough.

---

## PART 6: FILE STRUCTURE ON PYTHONANYWHERE

After setup, your file tree should look like this:

```
/home/yourusername/
├── slot-studio/
│   ├── .env                    ← Your API keys (DO NOT commit to git)
│   ├── main.py                 ← CLI entry point
│   ├── web_app.py              ← Flask web interface
│   ├── requirements.txt
│   ├── config/
│   │   ├── settings.py         ← LLM routing, pipeline config
│   │   ├── agents.yaml         ← Agent role definitions
│   │   └── tasks.yaml          ← Task templates
│   ├── models/
│   │   └── schemas.py          ← Pydantic structured outputs
│   ├── flows/
│   │   └── pipeline.py         ← CrewAI Flow state machine
│   ├── tools/
│   │   ├── custom_tools.py     ← Agent tools (search, sim, art, RAG)
│   │   └── ingest_regulations.py
│   ├── templates/
│   │   └── math_simulation.py  ← Monte Carlo template
│   ├── examples/
│   │   └── egyptian_curse.json ← Test input
│   ├── data/
│   │   └── regulations/        ← Your regulatory PDFs (for RAG)
│   └── output/                 ← Generated game packages go here
│       └── ancient_egypt_20250225_143022/
│           ├── 01_research/
│           ├── 02_design/
│           ├── 03_math/
│           ├── 04_art/
│           ├── 05_legal/
│           └── PACKAGE_MANIFEST.json
└── .virtualenvs/
    └── slot-studio/            ← Your Python virtual environment
```

---

## PART 7: MONITORING & MAINTENANCE

### Check Logs

```bash
# Flask error log (on PythonAnywhere)
# Go to Web tab → click "Error log" link

# Or check your pipeline logs:
tail -f ~/slot-studio/pipeline.log
```

### Monitor API Costs

After each run, check the `PACKAGE_MANIFEST.json` in the output directory. It tracks token usage and estimated costs.

Also monitor:
- **OpenAI usage**: https://platform.openai.com/usage
- **Serper usage**: https://serper.dev/dashboard

### Update the Code

```bash
cd ~/slot-studio
workon slot-studio

# If you upload a new zip:
cd ~
unzip -o slot-studio.zip

# Then reload the web app:
# Go to Web tab → click "Reload"
```

### PythonAnywhere CPU Limits

- **Hacker plan**: 2000 CPU-seconds/day
- **Battery plan**: 4000 CPU-seconds/day
- Monte Carlo simulations are CPU-intensive
- If you hit limits, reduce `SIMULATION_SPINS` in settings or upgrade your plan

---

## QUICK REFERENCE — COMMON COMMANDS

```bash
# Activate your environment
workon slot-studio

# Run a pipeline from CLI
cd ~/slot-studio
python main.py --from-json examples/egyptian_curse.json --auto

# Run the Flask app locally (for testing in console)
python web_app.py

# Check what's in your output
ls -la output/

# View a specific output package
ls -la output/ancient_egypt_*/

# Tail logs
tail -100 pipeline.log

# Install a missing package
pip install package-name

# Check your Python version
python --version
```

---

## TROUBLESHOOTING CHECKLIST

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | Run `workon slot-studio` then `pip install -r requirements.txt` |
| Web app shows "Something went wrong" | Check error log: Web tab → Error log link |
| API calls failing | Verify paid plan + check `.env` keys |
| Pipeline hangs | Check CPU quota on Dashboard; reduce simulation spins |
| "No such file or directory" | Make sure paths use `/home/yourusername/` not `~` in WSGI |
| Images not generating | Check OpenAI API key has DALL-E access + sufficient credits |
| Qdrant connection refused | Use Qdrant Cloud URL or disable RAG (static fallback works) |
| `Permission denied` on output/ | Run `chmod 755 ~/slot-studio/output` |
