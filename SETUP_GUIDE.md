# Arkain Slot Studio — Complete Setup Guide

Everything you need to get this running on PythonAnywhere from scratch.
Follow every step in order. Don't skip anything.

---

## WHAT YOU NEED

- **PythonAnywhere paid account** — Hacker ($5/mo) minimum, Battery ($12/mo) recommended
  - Free accounts block all outbound HTTP — none of the APIs will work
- **The `slot-studio.zip` file** you downloaded from Claude
- Your API keys (already in the `.env` inside the zip)

---

## PART 1: PYTHONANYWHERE ACCOUNT

### Step 1 — Sign Up

1. Go to https://www.pythonanywhere.com
2. Click **Pricing & signup**
3. Pick **Hacker** ($5/mo) or **Battery** ($12/mo)
   - Battery gives 2x CPU seconds — matters for Monte Carlo simulations
4. Verify email, log in

---

## PART 2: UPLOAD & INSTALL

### Step 2 — Upload the Zip

1. On your dashboard, click the **Files** tab
2. You'll see `/home/yourusername/`
3. Click **Upload a file** → select `slot-studio.zip`

### Step 3 — Unzip

Click the **Consoles** tab → start a new **Bash** console. Run:

```bash
cd ~
unzip slot-studio.zip
ls slot-studio/
```

You should see: `main.py`, `web_app.py`, `.env`, `config/`, `flows/`, `tools/`, etc.

### Step 4 — Create Virtual Environment

```bash
mkvirtualenv slot-studio --python=/usr/bin/python3.10
```

It activates automatically. If you ever need to reactivate later:

```bash
workon slot-studio
```

### Step 5 — Install Dependencies

```bash
cd ~/slot-studio
pip install --upgrade pip
pip install -r requirements.txt
```

This takes 3-5 minutes. If anything fails:

```bash
# Install core packages individually if needed
pip install crewai crewai-tools openai qdrant-client
pip install httpx flask reportlab rich python-dotenv pyyaml
pip install numpy scipy pandas matplotlib
pip install pymupdf pdfplumber litellm pydantic jinja2
```

### Step 6 — Verify Your .env

The zip already has your live `.env` with all API keys. Confirm it's there:

```bash
cat ~/slot-studio/.env
```

You should see your OpenAI key, Serper key, Qdrant URL, and Qdrant API key all filled in.
If anything is missing, edit it:

```bash
nano ~/slot-studio/.env
```

Save: `Ctrl+O` → `Enter` → `Ctrl+X`

---

## PART 3: SET UP QDRANT (YOUR LIVE DATABASE)

This is the single source of truth for all jurisdiction data. No static files —
everything lives here. You already have a Qdrant Cloud cluster, you just need
to create the collection.

### Step 7 — Create the Qdrant Collection

In your Bash console:

```bash
cd ~/slot-studio
workon slot-studio
python -c "
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import os
from dotenv import load_dotenv
load_dotenv()

client = QdrantClient(
    url=os.getenv('QDRANT_URL'),
    api_key=os.getenv('QDRANT_API_KEY'),
)

# Check connection
collections = [c.name for c in client.get_collections().collections]
print(f'Connected! Existing collections: {collections}')

# Create collection if it doesn't exist
name = os.getenv('QDRANT_COLLECTION', 'slot_regulations')
if name not in collections:
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )
    print(f'Created collection: {name}')
else:
    info = client.get_collection(name)
    print(f'Collection {name} already exists ({info.points_count} vectors)')

print('Qdrant is ready.')
"
```

**Expected output:**
```
Connected! Existing collections: []
Created collection: slot_regulations
Qdrant is ready.
```

### Step 8 — Verify the Full Connection (Embed + Search)

This tests OpenAI embeddings → Qdrant upsert → Qdrant search — the whole chain:

```bash
python -c "
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from openai import OpenAI
import os, hashlib
from dotenv import load_dotenv
load_dotenv()

# Connect
qd = QdrantClient(url=os.getenv('QDRANT_URL'), api_key=os.getenv('QDRANT_API_KEY'))
oai = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
collection = os.getenv('QDRANT_COLLECTION', 'slot_regulations')

# Test embed
test_text = 'Georgia COAM skill game exemption requires player decision affecting outcome'
resp = oai.embeddings.create(model='text-embedding-3-small', input=test_text)
vec = resp.data[0].embedding
print(f'Embedding generated: {len(vec)} dimensions')

# Test upsert
pid = int(hashlib.md5(test_text.encode()).hexdigest()[:12], 16)
qd.upsert(collection_name=collection, points=[
    PointStruct(id=pid, vector=vec, payload={
        'text': test_text,
        'jurisdiction': 'Georgia',
        'source': 'test',
        'category': 'test',
        'filename': 'test.md',
        'chunk_index': 0,
    })
])
print('Test vector upserted')

# Test search
results = qd.search(collection_name=collection, query_vector=vec, limit=1)
print(f'Search returned: {results[0].payload[\"text\"][:60]}...')

# Clean up test data
qd.delete(collection_name=collection, points_selector=[pid])
print('Test data cleaned up')

print()
print('ALL SYSTEMS GO — OpenAI + Qdrant fully operational')
"
```

**Expected output:**
```
Embedding generated: 1536 dimensions
Test vector upserted
Search returned: Georgia COAM skill game exemption requires player decision ...
Test data cleaned up

ALL SYSTEMS GO — OpenAI + Qdrant fully operational
```

If this works, your entire backend is wired up correctly.

---

## PART 4: TEST THE PIPELINES

### Step 9 — Test the Slot Studio Pipeline (Core Product)

```bash
cd ~/slot-studio
workon slot-studio

python main.py --from-json examples/egyptian_curse.json --auto
```

This runs the full 6-agent pipeline: market research → game design → math model → art → compliance → PDF package.

**First run takes 5-15 minutes** depending on your PythonAnywhere plan. Output goes to `output/`.

If it works, you'll see a folder like `output/ancient_egypt_20250225_143022/` with PDFs.

### Step 10 — Test the State Recon Pipeline (Legal Intelligence)

This is the new pipeline. Point it at any US state and it autonomously researches the laws,
finds loopholes, designs a compliant game, and writes a legal defense brief:

```bash
cd ~/slot-studio
workon slot-studio

python -m flows.state_recon --state "North Carolina" --auto
```

**What happens:**
1. Legal Recon Agent searches for NC gambling statutes, definitions, exemptions, case law
2. Definition Analyzer maps the legal elements and identifies which can be negated
3. Game Architect designs specific mechanics that fit inside the legal safe harbor
4. Defense Counsel writes a legal defense brief with statutory mapping

**Output:** `output/recon/north_carolina/`
- `01_raw_research.json` — everything the legal researcher found
- `02_legal_profile.json` — definition analysis, exemptions, risk tier
- `03_game_architecture.json` — compliant game design with legal justification
- `04_defense_brief.json` — courtroom-grade defense mapping each mechanic to statute
- `recon_package.json` — summary

**Auto-ingest:** After completing, results are automatically embedded into Qdrant.
Next time any agent queries "North Carolina", the data is already there.

### Step 11 — Verify Qdrant Got Populated

After the recon run, check that the data landed in Qdrant:

```bash
python -c "
from tools.qdrant_store import JurisdictionStore
store = JurisdictionStore()
status = store.get_status()
print(f'Status: {status[\"status\"]}')
print(f'Total vectors: {status[\"total_vectors\"]}')
print(f'Jurisdictions: {status[\"jurisdictions\"]}')
"
```

You should see `North Carolina` (or whichever state you ran) in the jurisdictions list.

---

## PART 5: WEB INTERFACE

### Step 12 — Create the Web App

1. Go to the **Web** tab on your PythonAnywhere dashboard
2. Click **Add a new web app**
3. Choose **Manual configuration** (NOT the Flask shortcut)
4. Select **Python 3.10**
5. You'll get a URL: `yourusername.pythonanywhere.com`

### Step 13 — Configure WSGI

1. On the Web tab, click the link to your **WSGI configuration file**
   (something like `/var/www/yourusername_pythonanywhere_com_wsgi.py`)
2. **Delete everything** in the file
3. Paste this (change `YOURUSERNAME` to your actual username):

```python
import sys
import os

USERNAME = 'YOURUSERNAME'  # ← CHANGE THIS

project_home = f'/home/{USERNAME}/slot-studio'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_home, '.env'))

os.chdir(project_home)

from web_app import app as application
```

4. Save the file

### Step 14 — Set Virtual Environment Path

1. On the **Web** tab, scroll to **Virtualenv**
2. Enter: `/home/YOURUSERNAME/.virtualenvs/slot-studio`
3. Click the checkmark

### Step 15 — Set Source Code Directory

1. On the Web tab, in **Code** section
2. **Source code:** `/home/YOURUSERNAME/slot-studio`
3. **Working directory:** `/home/YOURUSERNAME/slot-studio`

### Step 16 — Reload & Test

1. Click the green **Reload** button
2. Visit: `https://yourusername.pythonanywhere.com`
3. You should see the Arkain Slot Studio dashboard

---

## PART 6: RUNNING RECON ON MORE STATES

Every state you research makes the system smarter. Here are the commands:

```bash
cd ~/slot-studio
workon slot-studio

# Research a single state
python -m flows.state_recon --state "Florida" --auto

# Research multiple states (run one at a time)
python -m flows.state_recon --state "California" --auto
python -m flows.state_recon --state "New York" --auto
python -m flows.state_recon --state "Pennsylvania" --auto
python -m flows.state_recon --state "Ohio" --auto

# Check what's in your database
python -c "
from tools.qdrant_store import JurisdictionStore
store = JurisdictionStore()
status = store.get_status()
for j in status['jurisdictions']:
    print(f'  ✓ {j}')
print(f'Total vectors: {status[\"total_vectors\"]}')
"
```

Each recon run:
- Searches live web for current statutes, court rulings, AG opinions
- Auto-ingests results into Qdrant
- Creates output files in `output/recon/<state_name>/`

**Re-run a state** any time laws change. New data overwrites old vectors.

---

## PART 7: SCHEDULED TASKS (OPTIONAL)

Auto-refresh jurisdiction data on a schedule:

1. Go to **Tasks** tab on PythonAnywhere
2. Create a new scheduled task
3. Command:

```bash
/home/YOURUSERNAME/.virtualenvs/slot-studio/bin/python -m flows.state_recon --state "Georgia" --auto >> /home/YOURUSERNAME/slot-studio/recon.log 2>&1
```

Set it monthly to keep your state data fresh.

---

## PART 8: MONITORING

### Check API Costs

```bash
# After a pipeline run, check estimated spend:
cat output/recon/north_carolina/recon_package.json | python -m json.tool
```

Monitor your API dashboards:
- **OpenAI:** https://platform.openai.com/usage
- **Serper:** https://serper.dev/dashboard
- **Qdrant Cloud:** https://cloud.qdrant.io (check storage usage)

### Check Logs

```bash
# Pipeline logs
tail -100 ~/slot-studio/recon.log

# Web app errors — on the Web tab, click "Error log"
```

### PythonAnywhere CPU Limits

| Plan | CPU Seconds/Day | Good For |
|------|----------------|----------|
| Hacker ($5/mo) | 2,000 | ~2-3 recon runs/day |
| Battery ($12/mo) | 4,000 | ~5-6 recon runs/day |

Each state recon uses ~300-500 CPU seconds. If you're hitting limits, space them out
or upgrade to Battery.

---

## TROUBLESHOOTING

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | `workon slot-studio` then `pip install -r requirements.txt` |
| `Connection refused` / network errors | You need a **paid** PythonAnywhere plan |
| `Rate limit exceeded` (OpenAI) | Wait 60 seconds, or check https://platform.openai.com/usage |
| `Collection not found` (Qdrant) | Re-run Step 7 to create the collection |
| Web app shows 500 error | Web tab → click **Error log** to see what broke |
| `No data found for 'X'` | That state hasn't been researched yet — run `python -m flows.state_recon --state "X" --auto` |
| Pipeline hangs | Check CPU quota on dashboard; reduce `SIMULATION_SPINS` in `.env` |
| `Permission denied` on output | `chmod -R 755 ~/slot-studio/output` |

---

## QUICK REFERENCE

```bash
# Always start with these two lines
cd ~/slot-studio
workon slot-studio

# Run the main slot pipeline
python main.py --from-json examples/egyptian_curse.json --auto

# Research a state's gambling laws
python -m flows.state_recon --state "North Carolina" --auto

# Check what jurisdictions are in your database
python -c "from tools.qdrant_store import JurisdictionStore; [print(f'  ✓ {j}') for j in JurisdictionStore().list_jurisdictions()]"

# Check Qdrant health
python -c "from tools.qdrant_store import JurisdictionStore; print(JurisdictionStore().get_status())"

# Reload web app after changes
# Go to Web tab → click Reload
```

---

## FILE STRUCTURE

```
/home/yourusername/slot-studio/
├── .env                          ← Live API keys (already configured)
├── main.py                       ← CLI for slot game pipeline
├── web_app.py                    ← Flask web dashboard
├── requirements.txt
├── config/
│   ├── settings.py               ← LLM routing, pipeline config (no static state data)
│   ├── agents.yaml               ← Agent roles
│   └── tasks.yaml                ← Task templates
├── flows/
│   ├── pipeline.py               ← Main slot game pipeline (6 agents)
│   └── state_recon.py            ← State Recon Pipeline (4 agents)
├── tools/
│   ├── custom_tools.py           ← Search, math sim, image gen, RAG tool
│   ├── qdrant_store.py           ← Qdrant connection (single source of truth)
│   ├── legal_research_tool.py    ← Multi-pass web search for state laws
│   ├── auto_ingest.py            ← Converts recon output → Qdrant vectors
│   ├── ingest_regulations.py     ← Bulk document ingestion
│   └── pdf_generator.py          ← Branded PDF output
├── models/
│   └── schemas.py                ← Pydantic data models
├── templates/
│   └── math_simulation.py        ← Monte Carlo template
├── data/
│   └── regulations/
│       └── us_states/            ← Empty — Qdrant is the database now
└── output/
    ├── recon/                    ← State recon results land here
    │   └── north_carolina/
    │       ├── 01_raw_research.json
    │       ├── 02_legal_profile.json
    │       ├── 03_game_architecture.json
    │       ├── 04_defense_brief.json
    │       └── recon_package.json
    └── sample_pdfs/              ← Example PDF output
```
