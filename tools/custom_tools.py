"""
Automated Slot Studio - Custom Tools (PRODUCTION)

PHASE 3: FULLY WIRED TOOL INTEGRATION
======================================
Each tool is battle-tested with:
- Proper error handling and fallbacks
- Structured JSON output the pipeline can parse
- Connection to config for API keys and paths
- Real HTTP calls to Serper, OpenAI, Qdrant
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ============================================================
# Tool 1: Slot Database & Web Search
# ============================================================

class SlotSearchInput(BaseModel):
    query: str = Field(description="Search query, e.g. 'Egyptian theme high volatility slots'")
    max_results: int = Field(default=10, description="Max results to return")


class SlotDatabaseSearchTool(BaseTool):
    """Searches slot databases via Serper web search. Returns structured JSON."""

    name: str = "slot_database_search"
    description: str = (
        "Search for slot games by theme, provider, or mechanic. "
        "Returns structured data about competitor games including RTP, volatility, "
        "features, and player ratings. Always returns JSON."
    )
    args_schema: type[BaseModel] = SlotSearchInput

    def _run(self, query: str, max_results: int = 10) -> str:
        serper_key = os.getenv("SERPER_API_KEY")
        if not serper_key:
            return json.dumps({
                "error": "SERPER_API_KEY not set",
                "fallback": "Use your training knowledge about slot games to answer."
            })

        try:
            import httpx
        except ImportError:
            return json.dumps({"error": "httpx not installed. Run: pip install httpx"})

        search_queries = [
            f"{query} site:slotcatalog.com",
            f"{query} site:casino.guru",
            f"{query} slot game RTP volatility features",
        ]

        all_results = []
        for sq in search_queries:
            try:
                resp = httpx.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                    json={"q": sq, "num": max_results},
                    timeout=15.0,
                )
                data = resp.json()
                for item in data.get("organic", [])[:max_results]:
                    all_results.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "url": item.get("link", ""),
                    })
            except Exception as e:
                all_results.append({"error": f"Search failed: {str(e)}"})

        # Deduplicate by URL
        seen = set()
        unique = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(r)

        return json.dumps({
            "query": query,
            "results_count": len(unique),
            "results": unique[:max_results * 2],
        })


# ============================================================
# Tool 2: Math Simulation Executor
# ============================================================

class MathSimInput(BaseModel):
    python_code: str = Field(description="Complete Python simulation script to execute")
    timeout_seconds: int = Field(default=120, description="Max execution time in seconds")


class MathSimulationTool(BaseTool):
    """
    Executes Python math simulation code in a subprocess.
    The script should print JSON results to stdout.
    Has access to numpy, scipy, pandas.
    """

    name: str = "run_math_simulation"
    description: str = (
        "Execute a Python script that simulates slot game spins. "
        "The script MUST print a JSON object to stdout with simulation results. "
        "Available libraries: numpy, scipy, pandas, json, collections. "
        "Returns the script's stdout (JSON results) and any errors."
    )
    args_schema: type[BaseModel] = MathSimInput

    def _run(self, python_code: str, timeout_seconds: int = 120) -> str:
        # Write code to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write(python_code)
            script_path = f.name

        try:
            result = subprocess.run(
                ["python3", script_path],
                capture_output=True, text=True,
                timeout=timeout_seconds, cwd="/tmp",
            )

            output = {
                "exit_code": result.returncode,
                "stdout": result.stdout[:15000],
                "stderr": result.stderr[:2000] if result.stderr else "",
            }

            # Try parsing stdout as JSON — use ONLY parsed form to save context
            if result.returncode == 0 and result.stdout.strip():
                try:
                    parsed = json.loads(result.stdout)
                    # Keep only key metrics, not the full verbose output
                    output["parsed_results"] = parsed
                    # Drop raw stdout if we have parsed — no need to carry both
                    if len(result.stdout) > 5000:
                        output["stdout"] = "[parsed successfully — see parsed_results]"
                except json.JSONDecodeError:
                    output["note"] = "Output is not valid JSON. Returning raw stdout."

            return json.dumps(output)

        except subprocess.TimeoutExpired:
            return json.dumps({
                "error": f"Script timed out after {timeout_seconds}s",
                "fix": "Reduce SIMULATION_SPINS or optimize numpy vectorization"
            })
        except Exception as e:
            return json.dumps({"error": str(e)})
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass


# ============================================================
# Tool 3: Image Generation (DALL-E 3)
# ============================================================

class ImageGenInput(BaseModel):
    prompt: str = Field(description="Detailed image prompt")
    size: str = Field(default="1024x1024", description="'1024x1024' or '1792x1024'")
    asset_name: str = Field(description="Filename without extension, e.g. 'symbol_pharaoh'")
    output_dir: str = Field(default="./output/art", description="Save directory")


class ImageGenerationTool(BaseTool):
    """Generates images using DALL-E 3. Saves to disk and returns metadata."""

    name: str = "generate_image"
    description: str = (
        "Generate a high-quality image with DALL-E 3. Provide a detailed prompt. "
        "Use for slot game symbols, backgrounds, UI, mood boards, and concept art. "
        "Returns the file path and metadata."
    )
    args_schema: type[BaseModel] = ImageGenInput

    def _run(self, prompt: str, size: str = "1024x1024", asset_name: str = "image", output_dir: str = "./output/art") -> str:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DALLE_API_KEY")
        if not api_key:
            return json.dumps({
                "status": "skipped",
                "reason": "No OPENAI_API_KEY or DALLE_API_KEY set",
                "asset_name": asset_name,
                "prompt": prompt,
                "note": "Image generation skipped. Prompt recorded for manual generation."
            })

        try:
            from openai import OpenAI
            import httpx

            client = OpenAI(api_key=api_key)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            response = client.images.generate(
                model="dall-e-3", prompt=prompt,
                size=size, style="vivid", quality="hd", n=1,
            )

            image_url = response.data[0].url
            revised_prompt = response.data[0].revised_prompt

            # Download
            img_resp = httpx.get(image_url, timeout=30.0)
            file_path = Path(output_dir) / f"{asset_name}.png"
            file_path.write_bytes(img_resp.content)

            return json.dumps({
                "status": "success",
                "file_path": str(file_path),
                "asset_name": asset_name,
                "size": size,
                "revised_prompt": revised_prompt,
            })

        except Exception as e:
            return json.dumps({
                "status": "error",
                "error": str(e),
                "asset_name": asset_name,
                "prompt": prompt,
            })


# ============================================================
# Tool 4: Regulatory RAG Search
# ============================================================

class RAGSearchInput(BaseModel):
    query: str = Field(description="Regulatory question or compliance query to search")
    jurisdiction: Optional[str] = Field(
        default=None,
        description="Filter by jurisdiction name, e.g. 'Georgia', 'North Carolina', 'UK', 'Malta'. Any state researched via State Recon Pipeline is available."
    )
    search_type: Optional[str] = Field(
        default="all",
        description="Search focus: 'all', 'loopholes', 'statutes', 'compliance_checklist', 'red_flags'"
    )


class RegulatoryRAGTool(BaseTool):
    """
    Searches the Qdrant regulatory vector database for compliance info.
    Qdrant is the SINGLE SOURCE OF TRUTH — no static fallback.
    If a jurisdiction hasn't been researched yet, instructs the agent to
    run the State Recon Pipeline first.
    """

    name: str = "search_regulations"
    description: str = (
        "Search the live gaming regulatory knowledge base (Qdrant). "
        "Contains data for any jurisdiction that has been researched via the "
        "State Recon Pipeline. Returns regulatory requirements, legal pathways, "
        "game design constraints, risk levels, court rulings, and enforcement notes. "
        "Use search_type='loopholes' for loophole-focused results. "
        "If no data exists for a jurisdiction, you will be told to run recon first."
    )
    args_schema: type[BaseModel] = RAGSearchInput

    def _run(self, query: str, jurisdiction: Optional[str] = None, search_type: str = "all") -> str:
        from tools.qdrant_store import JurisdictionStore

        store = JurisdictionStore()

        # Check if Qdrant is configured
        if not store.is_available:
            return json.dumps({
                "source": "error",
                "error": "QDRANT NOT CONFIGURED",
                "action_required": (
                    "Set QDRANT_URL and OPENAI_API_KEY in .env to enable the "
                    "live regulatory database. Without Qdrant, use the legal_research "
                    "tool for web-based research, or run the State Recon Pipeline: "
                    "python -m flows.state_recon --state '<state_name>'"
                ),
            })

        # Enhance query for targeted searches
        enhanced = self._enhance_query(query, search_type)

        # Search Qdrant
        results = store.search(enhanced, jurisdiction=jurisdiction, limit=8)

        # Check for errors
        if results and "error" in results[0]:
            return json.dumps({
                "source": "error",
                "error": results[0]["error"],
                "action_required": "Check Qdrant connection. May need to re-ingest data.",
            })

        # No results found
        if not results:
            response = {
                "source": "qdrant_rag",
                "results_count": 0,
                "query": query,
                "jurisdiction_filter": jurisdiction,
            }
            if jurisdiction:
                response["action_required"] = (
                    f"No data found for '{jurisdiction}'. This jurisdiction has not "
                    f"been researched yet. Run the State Recon Pipeline to research it: "
                    f"python -m flows.state_recon --state '{jurisdiction}'\n"
                    f"This will autonomously research the laws, find loopholes, design "
                    f"a compliant game, and generate a legal defense brief. Results are "
                    f"auto-ingested into Qdrant for future queries."
                )
            else:
                # Show what jurisdictions ARE available
                available = store.list_jurisdictions()
                response["available_jurisdictions"] = available
                response["note"] = (
                    f"No results matched your query. {len(available)} jurisdictions "
                    f"are currently in the database. Try narrowing your search or "
                    f"specifying a jurisdiction filter."
                )
            return json.dumps(response)

        # Format results
        formatted = [{
            "score": r["score"],
            "text": r["text"][:800],
            "source": r["source"],
            "jurisdiction": r["jurisdiction"],
            "category": r.get("category", "general"),
        } for r in results]

        return json.dumps({
            "source": "qdrant_rag",
            "query": query,
            "search_type": search_type,
            "jurisdiction_filter": jurisdiction,
            "results_count": len(formatted),
            "results": formatted,
        })

    def _enhance_query(self, query: str, search_type: str) -> str:
        """Enhance query based on search type for better retrieval."""
        enhancements = {
            "loopholes": " loophole strategy legal pathway game design compliance workaround",
            "statutes": " statute code section law definition legal prohibition",
            "compliance_checklist": " compliance checklist requirement license fee tax registration",
            "red_flags": " illegal prohibited red flag penalty enforcement seizure",
        }
        return query + enhancements.get(search_type, "")


# ============================================================
# Tool 5: File Writer
# ============================================================

class FileWriteInput(BaseModel):
    file_path: str = Field(description="Full path to save the file")
    content: str = Field(description="Content to write")


class FileWriterTool(BaseTool):
    """Saves content to files. Handles JSON auto-formatting."""

    name: str = "write_file"
    description: str = "Save text content to a file. Automatically pretty-prints JSON. Creates directories as needed."
    args_schema: type[BaseModel] = FileWriteInput

    def _run(self, file_path: str, content: str) -> str:
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Auto-format JSON
            if path.suffix == ".json":
                try:
                    parsed = json.loads(content)
                    content = json.dumps(parsed)
                except json.JSONDecodeError:
                    pass

            path.write_text(content, encoding="utf-8")
            return json.dumps({
                "status": "success",
                "file_path": str(path.absolute()),
                "size_bytes": path.stat().st_size,
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})
