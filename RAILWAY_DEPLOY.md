# Arkain Slot Studio — Railway Deployment Guide

Step by step. Follow in order.

---

## WHAT YOU NEED

- A **GitHub account** (free) — https://github.com
- A **Railway account** (free to start, ~$5-10/mo usage) — https://railway.app
- The `slot-studio.zip` file you downloaded

---

## PART 1: PUSH CODE TO GITHUB

Railway deploys from a GitHub repo. You need to create one.

### Step 1 — Create a GitHub Account (skip if you have one)

1. Go to https://github.com
2. Sign up (free)
3. Verify your email

### Step 2 — Create a New Repository

1. Click the **+** button (top right) → **New repository**
2. Settings:
   - **Repository name:** `slot-studio`
   - **Visibility:** Private (your API keys won't be in the code, but keep it private anyway)
   - **DO NOT** check "Add a README" — leave everything unchecked
3. Click **Create repository**
4. You'll see a page with setup instructions. Leave this tab open.

### Step 3 — Upload Your Code

**Option A: From your computer (easiest)**

1. Unzip `slot-studio.zip` somewhere on your computer
2. **DELETE the `.env` file** from the unzipped folder (your keys go in Railway's dashboard, NOT in GitHub)
3. Go back to the GitHub repo page from Step 2
4. Click **"uploading an existing file"** link
5. Drag the entire contents of the `slot-studio/` folder into the upload area
6. Click **Commit changes**

**Option B: Using Git from terminal (if you know Git)**

```bash
# Unzip
unzip slot-studio.zip
cd slot-studio

# Remove .env (keys go in Railway dashboard, not GitHub)
rm .env

# Initialize git and push
git init
git add .
git commit -m "Initial commit - Arkain Slot Studio"
git branch -M main
git remote add origin https://github.com/YOURUSERNAME/slot-studio.git
git push -u origin main
```

Replace `YOURUSERNAME` with your actual GitHub username.

---

## PART 2: DEPLOY ON RAILWAY

### Step 4 — Create a Railway Account

1. Go to https://railway.app
2. Click **Login** → **Login with GitHub**
3. Authorize Railway to access your GitHub
4. You'll land on the Railway dashboard

### Step 5 — Create a New Project

1. Click **New Project**
2. Click **Deploy from GitHub repo**
3. Select your `slot-studio` repository
4. Railway will detect the `Dockerfile` and start building automatically
5. **Wait for the first build to finish** (2-3 minutes) — it will FAIL because there are no environment variables yet. That's fine.

### Step 6 — Add Your Environment Variables

This is where your API keys go (NOT in the code).

1. Click on your service (the box that appeared in the project)
2. Click the **Variables** tab
3. Click **Raw Editor** (top right of the variables section)
4. Paste ALL of this:

```
OPENAI_API_KEY=your-openai-key-here
SERPER_API_KEY=your-serper-key-here
QDRANT_URL=your-qdrant-cluster-url-here
QDRANT_API_KEY=your-qdrant-api-key-here
QDRANT_COLLECTION=slot_regulations
HITL_ENABLED=false
OUTPUT_DIR=./output
SIMULATION_SPINS=1000000
LOG_LEVEL=INFO
```

5. Click **Update variables**
6. Railway will automatically **redeploy** with the new variables

### Step 7 — Generate a Public URL

1. Click on your service
2. Click **Settings** tab
3. Scroll to **Networking** section
4. Click **Generate Domain**
5. You'll get a URL like: `slot-studio-production-xxxx.up.railway.app`
6. Click it — you should see the Arkain Slot Studio dashboard

**If the page loads, your web app is live.**

---

## PART 3: SET UP QDRANT

### Step 8 — Create the Qdrant Collection

You need to run one command to create the vector database collection. 

1. In Railway, click on your service
2. Click the **Settings** tab
3. Scroll down and find the **Railway Shell** button (or use the **Deploy** tab → three dots → **Attach Shell**)

If Railway Shell isn't available, you can do this from your local machine instead. Install Python and run:

```bash
pip install qdrant-client openai python-dotenv
```

Then create a file called `setup_qdrant.py` and paste:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import os
from dotenv import load_dotenv
load_dotenv()

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

# Check connection
collections = [c.name for c in client.get_collections().collections]
print(f"Connected! Existing collections: {collections}")

# Create collection
name = "slot_regulations"
if name not in collections:
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )
    print(f"Created collection: {name}")
else:
    info = client.get_collection(name)
    print(f"Collection '{name}' already exists ({info.points_count} vectors)")

print("Qdrant is ready.")
```

Run it:

```bash
python setup_qdrant.py
```

**Expected output:**
```
Connected! Existing collections: []
Created collection: slot_regulations
Qdrant is ready.
```

You only need to do this once. After this, the State Recon Pipeline auto-populates it.

---

## PART 4: RUN YOUR FIRST STATE RECON

### Step 9 — Run a Recon via the Railway Shell

In Railway: click your service → **three dots menu** → **Attach Shell**

```bash
python -m flows.state_recon --state "North Carolina" --auto
```

This takes 5-15 minutes. It will:
1. Research NC gambling laws live via web search
2. Analyze the legal definitions and find loopholes
3. Design a compliant game with statutory mapping
4. Write a legal defense brief
5. Auto-ingest everything into Qdrant

**Output appears in** `output/recon/north_carolina/`

### Step 10 — Verify Qdrant Got Populated

In the same shell:

```bash
python -c "
from tools.qdrant_store import JurisdictionStore
store = JurisdictionStore()
status = store.get_status()
print(f'Status: {status[\"status\"]}')
print(f'Vectors: {status[\"total_vectors\"]}')
print(f'Jurisdictions: {status[\"jurisdictions\"]}')
"
```

You should see `North Carolina` in the list.

---

## PART 5: RESEARCH MORE STATES

### From Railway Shell

```bash
python -m flows.state_recon --state "Florida" --auto
python -m flows.state_recon --state "California" --auto
python -m flows.state_recon --state "Ohio" --auto
```

### From the Web Dashboard

Your live URL (`slot-studio-production-xxxx.up.railway.app`) has the full web interface for submitting game concepts through the main pipeline.

---

## PART 6: RAILWAY SPECIFICS

### Costs

Railway gives you $5 free credit, then charges based on usage:
- **RAM:** $0.000231/GB/min
- **CPU:** $0.000463/vCPU/min
- Typical cost: **$5-10/month** for this project

Check usage: Railway dashboard → **Usage** tab

### Logs

Click your service → **Deployments** tab → click the latest deployment → see live logs

### Redeploy After Code Changes

If you push changes to GitHub, Railway auto-deploys. Or:
1. Click your service
2. **Deployments** tab
3. **Redeploy** button

### Persistent Storage (if needed)

Output files are stored in the container. If you need them to survive redeployments:
1. In your project, click **New** → **Volume**
2. Mount path: `/app/output`
3. This persists your recon results across deploys

### Custom Domain (optional)

Settings → Networking → **Custom Domain** → add your own domain name

---

## TROUBLESHOOTING

| Problem | Fix |
|---------|-----|
| Build fails | Check **Deploy Logs** for the error. Usually a missing package in requirements.txt |
| App crashes on start | Check that all 4 env vars are set in Variables tab |
| "502 Bad Gateway" | App is still starting — wait 30 seconds and refresh |
| Pipeline times out | Railway has no hard timeout. If it dies, check logs for OOM (upgrade to more RAM) |
| Qdrant connection fails | Verify QDRANT_URL and QDRANT_API_KEY in Variables tab |
| "No data found for state" | Run the recon pipeline for that state first |
| Need a shell | Service → three dots → Attach Shell |
| Costs too high | Railway dashboard → Usage. Scale down workers in Dockerfile if needed |

---

## QUICK REFERENCE

```
Your live app:     https://slot-studio-production-xxxx.up.railway.app
Railway dashboard: https://railway.app/dashboard
GitHub repo:       https://github.com/YOURUSERNAME/slot-studio

# Run recon (from Railway Shell)
python -m flows.state_recon --state "Georgia" --auto

# Check database
python -c "from tools.qdrant_store import JurisdictionStore; s=JurisdictionStore(); print(s.get_status())"

# Run main slot pipeline
python main.py --from-json examples/egyptian_curse.json --auto
```
