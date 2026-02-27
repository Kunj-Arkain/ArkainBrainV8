"""
ARKAINBRAIN — Advanced Research Tools

UPGRADE 1: WebFetchTool — Read FULL web pages, not just snippets
UPGRADE 2: DeepResearchTool — Multi-pass research planner (search → fetch → gap → refine)
UPGRADE 3: CompetitorTeardownTool — Structured game data extraction from slot databases
UPGRADE 4: KnowledgeBaseTool — Save/retrieve past game designs across pipeline runs
"""

import json
import os
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ============================================================
# UPGRADE 1: Web Fetch — Read Full Pages
# ============================================================
# This is the SINGLE BIGGEST improvement. Currently agents get
# ~200 char Serper snippets. Now they can read entire articles,
# regulatory pages, competitor reviews, stat sheets, etc.

class WebFetchInput(BaseModel):
    url: str = Field(description="Full URL to fetch, e.g. 'https://example.com/page'")
    extract_mode: str = Field(
        default="smart",
        description="Extraction mode: 'smart' (auto-detect), 'text' (strip HTML), 'tables' (extract tables), 'full' (raw HTML)"
    )
    max_chars: int = Field(default=15000, description="Max characters to return (default 15000)")


class WebFetchTool(BaseTool):
    """
    Fetches and reads the FULL content of any web page.

    USE THIS whenever you find a promising URL from a search result.
    Instead of relying on the 200-char snippet, fetch the full page
    to get complete regulatory text, full game reviews, detailed
    stat sheets, case law, etc.
    """

    name: str = "fetch_web_page"
    description: str = (
        "Fetch and read the FULL content of a web page. Use this after finding a URL "
        "from a search result to read the complete article, regulation, game review, "
        "or data sheet. Extracts clean text from HTML automatically. "
        "Supports smart extraction (auto-detect content type), plain text, tables, or raw HTML. "
        "CRITICAL: Use this to get the complete picture — search snippets are NOT enough."
    )
    args_schema: type[BaseModel] = WebFetchInput

    def _run(self, url: str, extract_mode: str = "smart", max_chars: int = 15000) -> str:
        try:
            import httpx
        except ImportError:
            return json.dumps({"error": "httpx not installed"})

        # Validate URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = httpx.get(url, headers=headers, timeout=20.0, follow_redirects=True)
            resp.raise_for_status()
            html = resp.text

            # Extract based on mode
            if extract_mode == "full":
                content = html[:max_chars]
            elif extract_mode == "tables":
                content = self._extract_tables(html)
            else:
                content = self._smart_extract(html)

            # Truncate
            content = content[:max_chars]

            return json.dumps({
                "status": "success",
                "url": url,
                "content_length": len(content),
                "extract_mode": extract_mode,
                "content": content,
            }, indent=2)

        except httpx.HTTPStatusError as e:
            return json.dumps({"status": "error", "url": url, "error": f"HTTP {e.response.status_code}"})
        except httpx.TimeoutException:
            return json.dumps({"status": "error", "url": url, "error": "Timeout (20s)"})
        except Exception as e:
            return json.dumps({"status": "error", "url": url, "error": str(e)})

    def _smart_extract(self, html: str) -> str:
        """Extract readable text from HTML, preserving structure."""
        # Remove scripts, styles, nav, footer, header, ads
        for tag in ["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]:
            html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML comments
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Convert common block elements to newlines
        for tag in ["p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"]:
            html = re.sub(rf"</?{tag}[^>]*>", "\n", html, flags=re.IGNORECASE)

        # Convert table cells to tabs
        html = re.sub(r"</?t[dh][^>]*>", "\t", html, flags=re.IGNORECASE)

        # Strip all remaining HTML tags
        text = re.sub(r"<[^>]+>", "", html)

        # Decode HTML entities
        import html as html_module
        text = html_module.unescape(text)

        # Clean up whitespace
        lines = []
        for line in text.split("\n"):
            cleaned = " ".join(line.split())
            if cleaned and len(cleaned) > 3:
                lines.append(cleaned)

        return "\n".join(lines)

    def _extract_tables(self, html: str) -> str:
        """Extract tabular data from HTML."""
        tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)
        if not tables:
            return self._smart_extract(html)

        result = []
        for i, table in enumerate(tables):
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL | re.IGNORECASE)
            table_data = []
            for row in rows:
                cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL | re.IGNORECASE)
                cleaned = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
                if any(cleaned):
                    table_data.append(cleaned)
            if table_data:
                result.append(f"\n--- Table {i+1} ---")
                for row in table_data:
                    result.append(" | ".join(row))

        return "\n".join(result) if result else self._smart_extract(html)


# ============================================================
# UPGRADE 2: Deep Research Planner — Multi-Pass Intelligence
# ============================================================
# Instead of a single search, this tool:
# 1. Takes a research objective
# 2. Generates multiple search angles
# 3. Executes searches for each angle
# 4. Fetches the most promising URLs
# 5. Synthesizes findings
# 6. Identifies gaps and recommends follow-up queries

class DeepResearchInput(BaseModel):
    objective: str = Field(description="Research objective, e.g. 'Analyze the Georgia gambling statutes and find legal pathways for skill-based slot games'")
    search_angles: list[str] = Field(
        default_factory=list,
        description="Specific search angles to pursue. If empty, the tool generates its own."
    )
    max_sources: int = Field(default=8, description="Max web pages to fetch in full (default 8)")
    depth: str = Field(default="deep", description="'quick' (2 searches), 'standard' (4), 'deep' (8), 'exhaustive' (12)")


class DeepResearchTool(BaseTool):
    """
    Multi-pass research engine. Plans research angles, executes searches,
    fetches full pages, and synthesizes findings with gap analysis.

    THIS IS YOUR PRIMARY RESEARCH TOOL. Use it instead of basic search
    for any substantive research task. It reads full web pages, not just
    snippets.
    """

    name: str = "deep_research"
    description: str = (
        "Conduct deep multi-pass research on any topic. Give it a research objective "
        "and it will: (1) generate multiple search angles, (2) execute targeted searches, "
        "(3) fetch and read full web pages, (4) compile structured findings, and "
        "(5) identify gaps needing follow-up. Use for: regulatory research, competitor "
        "analysis, market intelligence, legal analysis. Returns comprehensive research "
        "dossier. ALWAYS prefer this over basic search for substantive research tasks."
    )
    args_schema: type[BaseModel] = DeepResearchInput

    def _run(self, objective: str, search_angles: list[str] = None, max_sources: int = 8, depth: str = "deep") -> str:
        serper_key = os.getenv("SERPER_API_KEY")
        if not serper_key:
            return json.dumps({"error": "SERPER_API_KEY not set"})

        import httpx

        depth_map = {"quick": 2, "standard": 4, "deep": 8, "exhaustive": 12}
        max_searches = depth_map.get(depth, 8)

        # Generate search angles if not provided
        if not search_angles:
            search_angles = self._generate_angles(objective)

        search_angles = search_angles[:max_searches]

        # Phase 1: Execute all searches
        all_urls = {}  # url -> {title, snippet, angle}
        for angle in search_angles:
            try:
                resp = httpx.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                    json={"q": angle, "num": 8},
                    timeout=15.0,
                )
                data = resp.json()
                for item in data.get("organic", [])[:6]:
                    url = item.get("link", "")
                    if url and url not in all_urls and not self._is_junk_url(url):
                        all_urls[url] = {
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", ""),
                            "angle": angle,
                        }
            except Exception:
                continue

        # Phase 2: Rank and select top URLs to fetch
        ranked = self._rank_urls(all_urls, objective)
        to_fetch = ranked[:max_sources]

        # Phase 3: Fetch full content from top sources
        fetcher = WebFetchTool()
        sources = []
        for url_info in to_fetch:
            url = url_info["url"]
            try:
                result = json.loads(fetcher._run(url=url, max_chars=8000))
                if result.get("status") == "success":
                    sources.append({
                        "url": url,
                        "title": url_info["title"],
                        "angle": url_info["angle"],
                        "content": result["content"][:8000],
                        "content_length": result["content_length"],
                    })
            except Exception:
                continue

        # Phase 4: Compile research dossier
        dossier = {
            "objective": objective,
            "search_angles": search_angles,
            "total_urls_found": len(all_urls),
            "sources_fetched": len(sources),
            "sources": sources,
            "gap_analysis": self._identify_gaps(objective, sources, search_angles),
            "follow_up_queries": self._suggest_followups(objective, sources),
        }

        return json.dumps(dossier, indent=2)

    def _generate_angles(self, objective: str) -> list[str]:
        """Generate diverse search angles from an objective."""
        # Extract key terms
        terms = objective.lower()
        angles = [objective[:80]]  # Start with the raw objective

        # Regulatory research patterns
        if any(w in terms for w in ["statute", "law", "legal", "regulation", "gambling", "gaming"]):
            # Extract state name if present
            import re
            state_match = re.search(r'\b(Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming)\b', objective, re.IGNORECASE)
            state = state_match.group(0) if state_match else ""

            if state:
                angles.extend([
                    f"{state} gambling statute definition crime code",
                    f"{state} skill game amusement device exemption law",
                    f"{state} sweepstakes promotion legal requirements",
                    f"{state} gaming enforcement actions attorney general opinions",
                    f"{state} gambling case law court ruling precedent",
                    f"{state} pending gambling legislation 2024 2025 2026",
                    f"{state} coin operated amusement machine regulations",
                    f"{state} gaming commission rules license requirements",
                    f'"{state}" "predominant factor test" OR "material element" gambling',
                    f"{state} social gaming free play no purchase necessary law",
                    f"{state} fantasy sports daily betting regulation",
                ])
            else:
                angles.extend([
                    f"{objective} statute code section",
                    f"{objective} court ruling case law",
                    f"{objective} enforcement actions",
                    f"{objective} exemptions loopholes",
                ])

        # Competitor/market research patterns
        elif any(w in terms for w in ["slot", "game", "competitor", "market", "rtp", "volatility"]):
            angles.extend([
                f"{objective} site:slotcatalog.com",
                f"{objective} site:bigwinboard.com",
                f"{objective} RTP volatility max win features",
                f"{objective} game review 2024 2025",
                f"{objective} provider studio developer",
                f"{objective} hit frequency bonus mechanics",
                f"{objective} player reception community review",
            ])

        # General research
        else:
            angles.extend([
                f"{objective} research analysis",
                f"{objective} data statistics",
                f"{objective} expert opinion",
                f"{objective} case study",
            ])

        return angles[:12]

    def _rank_urls(self, urls: dict, objective: str) -> list[dict]:
        """Rank URLs by likely relevance to objective."""
        scored = []
        obj_lower = objective.lower()
        obj_words = set(obj_lower.split())

        # Priority domains for different research types
        priority_domains = {
            "law": ["legislature.gov", "legis.gov", "courts.gov", "law.justia.com", "casetext.com", "law.cornell.edu", "westlaw.com", "lexisnexis.com", "ago.gov", "attorney.general"],
            "gaming": ["slotcatalog.com", "bigwinboard.com", "casino.guru", "casinomeister.com", "askgamblers.com"],
            "regulation": [".gov", "gaming.commission", "gamingcontrol", "lottery.gov"],
        }

        for url, info in urls.items():
            score = 0
            url_lower = url.lower()
            title_lower = info["title"].lower()
            snippet_lower = info["snippet"].lower()

            # Domain priority
            for category, domains in priority_domains.items():
                if any(d in url_lower for d in domains):
                    score += 30
                    if any(w in obj_lower for w in category.split()):
                        score += 20

            # .gov gets extra boost
            if ".gov" in url_lower:
                score += 25

            # Title keyword overlap
            title_words = set(title_lower.split())
            overlap = len(obj_words & title_words)
            score += overlap * 8

            # Snippet keyword overlap
            snippet_words = set(snippet_lower.split())
            score += len(obj_words & snippet_words) * 3

            # Penalize junk
            if any(j in url_lower for j in ["pinterest", "youtube", "facebook", "twitter", "reddit", "quora", "tiktok"]):
                score -= 50

            # Recency bonus (year in title)
            if any(y in title_lower for y in ["2025", "2026", "2024"]):
                score += 10

            scored.append({"url": url, "title": info["title"], "angle": info["angle"], "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def _is_junk_url(self, url: str) -> bool:
        """Filter out low-value URLs."""
        junk = ["youtube.com", "facebook.com", "twitter.com", "instagram.com",
                "tiktok.com", "pinterest.com", "linkedin.com", "amazon.com",
                ".pdf", ".doc", ".mp4", ".mp3"]
        url_lower = url.lower()
        return any(j in url_lower for j in junk)

    def _identify_gaps(self, objective: str, sources: list, angles: list) -> list[str]:
        """Identify gaps in the research."""
        gaps = []
        all_content = " ".join(s["content"][:2000] for s in sources).lower()

        # Check for common gaps based on research type
        if any(w in objective.lower() for w in ["law", "statute", "regulation", "gambling"]):
            checks = [
                ("specific statute section numbers", "§"),
                ("court case citations", "v." ),
                ("penalty provisions", "penalty" ),
                ("enforcement history", "enforcement" ),
                ("exemption language", "exempt"),
                ("definition of gambling", "definition"),
                ("skill vs chance test", "predominant" ),
                ("pending legislation", "bill" ),
            ]
            for label, keyword in checks:
                if keyword.lower() not in all_content:
                    gaps.append(f"Missing: {label} — search specifically for this")

        if any(w in objective.lower() for w in ["slot", "competitor", "game"]):
            checks = [
                ("specific RTP values", "96."),
                ("hit frequency data", "hit frequency"),
                ("max win multiplier", "max win"),
                ("feature mechanics details", "free spin"),
                ("release dates", "released"),
            ]
            for label, keyword in checks:
                if keyword.lower() not in all_content:
                    gaps.append(f"Missing: {label}")

        if not sources:
            gaps.append("CRITICAL: No sources were successfully fetched. Try different search angles.")

        return gaps

    def _suggest_followups(self, objective: str, sources: list) -> list[str]:
        """Suggest follow-up queries based on initial research."""
        followups = []
        all_content = " ".join(s["content"][:1000] for s in sources).lower()

        # Extract specific statute references to look up
        import re
        statutes = re.findall(r'§\s*[\d\-\.]+', " ".join(s["content"][:3000] for s in sources))
        for statute in set(statutes[:3]):
            followups.append(f"Full text of {statute}")

        # Extract case names
        cases = re.findall(r'[A-Z][a-z]+ v\. [A-Z][a-z]+', " ".join(s["content"][:3000] for s in sources))
        for case in set(cases[:2]):
            followups.append(f"Full ruling: {case}")

        # If we mention a bill number, look it up
        bills = re.findall(r'(?:HB|SB|AB|HR|SR)\s*\d+', " ".join(s["content"][:3000] for s in sources))
        for bill in set(bills[:2]):
            followups.append(f"Current status and text of {bill}")

        return followups


# ============================================================
# UPGRADE 3: Competitor Teardown — Structured Game Intelligence
# ============================================================

class CompetitorTeardownInput(BaseModel):
    game_name: str = Field(default="", description="Specific game name to analyze, e.g. 'Book of Dead'")
    theme: str = Field(default="", description="Theme to search for, e.g. 'Egyptian', 'Aztec', 'Norse'")
    provider: str = Field(default="", description="Provider filter, e.g. 'Play n GO', 'Pragmatic Play'")
    max_games: int = Field(default=5, description="Number of games to analyze")


class CompetitorTeardownTool(BaseTool):
    """
    Deep competitive intelligence on specific slot games.
    Goes beyond basic search — fetches full game review pages and extracts
    structured data: RTP, volatility, max win, grid, features, release date,
    player sentiment, and design elements.
    """

    name: str = "competitor_teardown"
    description: str = (
        "Conduct a deep teardown of competitor slot games. Provide a game name, theme, "
        "or provider. Returns structured data including: RTP, volatility, max win, "
        "grid layout, bonus features, art style, player sentiment, and competitive "
        "positioning. Use this to understand what works in the market and identify "
        "differentiation opportunities."
    )
    args_schema: type[BaseModel] = CompetitorTeardownInput

    def _run(self, game_name: str = "", theme: str = "", provider: str = "", max_games: int = 5) -> str:
        serper_key = os.getenv("SERPER_API_KEY")
        if not serper_key:
            return json.dumps({"error": "SERPER_API_KEY not set"})

        import httpx

        # Build targeted queries
        queries = []
        if game_name:
            queries.extend([
                f'"{game_name}" slot review RTP volatility features site:slotcatalog.com',
                f'"{game_name}" slot review site:bigwinboard.com',
                f'"{game_name}" slot game specifications max win',
            ])
        if theme:
            queries.extend([
                f"best {theme} themed slot games 2024 2025 RTP",
                f"{theme} slot games high volatility features site:slotcatalog.com",
            ])
        if provider:
            queries.extend([
                f"{provider} slot games 2024 2025 new releases",
                f"{provider} best slot games RTP",
            ])
        if not queries:
            queries = ["top slot games 2025 RTP features mechanics"]

        # Collect URLs
        all_urls = {}
        for q in queries[:6]:
            try:
                resp = httpx.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                    json={"q": q, "num": 8},
                    timeout=15.0,
                )
                for item in resp.json().get("organic", [])[:5]:
                    url = item.get("link", "")
                    if url and url not in all_urls:
                        all_urls[url] = {"title": item.get("title",""), "snippet": item.get("snippet","")}
            except Exception:
                continue

        # Prioritize slot review sites
        priority = ["slotcatalog.com", "bigwinboard.com", "casino.guru", "casinomeister.com"]
        ranked = sorted(
            all_urls.items(),
            key=lambda x: sum(10 for p in priority if p in x[0].lower()),
            reverse=True
        )

        # Fetch top sources
        fetcher = WebFetchTool()
        game_data = []
        for url, info in ranked[:max_games * 2]:
            try:
                result = json.loads(fetcher._run(url=url, extract_mode="smart", max_chars=6000))
                if result.get("status") == "success":
                    extracted = self._extract_game_data(result["content"], info["title"], url)
                    if extracted:
                        game_data.append(extracted)
                        if len(game_data) >= max_games:
                            break
            except Exception:
                continue

        return json.dumps({
            "query": {"game_name": game_name, "theme": theme, "provider": provider},
            "games_analyzed": len(game_data),
            "urls_found": len(all_urls),
            "games": game_data,
            "competitive_summary": self._build_summary(game_data),
        }, indent=2)

    def _extract_game_data(self, content: str, title: str, url: str) -> dict:
        """Extract structured game data from page content."""
        data = {"title": title, "url": url}

        # Extract RTP
        rtp_match = re.search(r'RTP[:\s]*(\d{2}\.?\d{0,2})\s*%', content, re.IGNORECASE)
        if rtp_match:
            data["rtp"] = float(rtp_match.group(1))

        # Extract volatility
        vol_match = re.search(r'volatil(?:ity|e)[:\s]*(low|medium|high|very high|extreme)', content, re.IGNORECASE)
        if vol_match:
            data["volatility"] = vol_match.group(1).title()

        # Extract max win
        maxwin_match = re.search(r'max(?:imum)?\s*win[:\s]*(?:up to\s*)?(\d[\d,]*)\s*x', content, re.IGNORECASE)
        if maxwin_match:
            data["max_win"] = maxwin_match.group(1).replace(",", "")

        # Extract grid
        grid_match = re.search(r'(\d)\s*x\s*(\d)\s*(?:grid|reel|layout)', content, re.IGNORECASE)
        if grid_match:
            data["grid"] = f"{grid_match.group(1)}x{grid_match.group(2)}"

        # Extract ways/paylines
        ways_match = re.search(r'(\d[\d,]*)\s*(?:ways|paylines|lines|win ways)', content, re.IGNORECASE)
        if ways_match:
            data["ways_or_lines"] = ways_match.group(1).replace(",", "")

        # Extract provider
        provider_match = re.search(r'(?:provider|developer|studio|by)[:\s]*([A-Z][A-Za-z\s\']+?)(?:\.|,|\n|<)', content)
        if provider_match:
            data["provider"] = provider_match.group(1).strip()[:30]

        # Extract features mentioned
        features = []
        feature_patterns = [
            "free spins", "bonus buy", "multiplier", "cascading", "expanding wild",
            "sticky wild", "respins", "progressive jackpot", "scatter", "megaways",
            "cluster pays", "tumble", "hold and spin", "pick bonus", "gamble feature",
            "ante bet", "mystery symbol", "walking wild", "split symbol", "avalanche",
        ]
        content_lower = content.lower()
        for fp in feature_patterns:
            if fp in content_lower:
                features.append(fp.title())
        data["features"] = features

        # Extract a content snippet for context
        data["excerpt"] = content[:500]

        return data if len(data) > 3 else None  # Only return if we extracted something

    def _build_summary(self, games: list) -> dict:
        """Build competitive landscape summary."""
        if not games:
            return {"note": "No games extracted. Try more specific queries."}

        rtps = [g["rtp"] for g in games if "rtp" in g]
        summary = {
            "total_games": len(games),
            "avg_rtp": round(sum(rtps) / len(rtps), 2) if rtps else None,
            "rtp_range": f"{min(rtps):.2f}% - {max(rtps):.2f}%" if rtps else None,
            "common_features": {},
            "volatility_distribution": {},
        }

        # Feature frequency
        all_features = {}
        for g in games:
            for f in g.get("features", []):
                all_features[f] = all_features.get(f, 0) + 1
        summary["common_features"] = dict(sorted(all_features.items(), key=lambda x: x[1], reverse=True)[:10])

        # Volatility distribution
        for g in games:
            v = g.get("volatility", "Unknown")
            summary["volatility_distribution"][v] = summary["volatility_distribution"].get(v, 0) + 1

        return summary


# ============================================================
# UPGRADE 4: Cross-Run Knowledge Base
# ============================================================
# Saves completed game designs to Qdrant so future pipeline runs
# can reference past work. "What symbols worked for Egyptian themes?"
# "What RTP did we use for the last high-vol game?" etc.

class KBStoreInput(BaseModel):
    action: str = Field(description="'save' to store a game design, 'search' to find past designs, 'list' to list all stored designs")
    game_slug: str = Field(default="", description="For 'save': the game identifier")
    game_data: str = Field(default="", description="For 'save': JSON string of the game design data to store")
    query: str = Field(default="", description="For 'search': what to search for")
    max_results: int = Field(default=5, description="For 'search': max results")


class KnowledgeBaseTool(BaseTool):
    """
    ARKAINBRAIN's institutional memory.

    Stores completed game designs in Qdrant so future pipeline runs
    can learn from past work. Search for past designs by theme, mechanic,
    feature, market, or any game attribute.

    Use 'save' after a pipeline completes to store the game package.
    Use 'search' at the START of new pipelines to learn from history.
    Use 'list' to see all stored designs.
    """

    name: str = "knowledge_base"
    description: str = (
        "Access ARKAINBRAIN's institutional memory — a database of all past game designs. "
        "ALWAYS search this at the start of a new pipeline to learn from past work. "
        "'save': store a completed game design. 'search': find past designs by theme, "
        "mechanic, feature, or market. 'list': show all stored designs. "
        "This helps you avoid repeating mistakes and build on what worked."
    )
    args_schema: type[BaseModel] = KBStoreInput

    _collection: str = "arkainbrain_knowledge"

    def _run(self, action: str, game_slug: str = "", game_data: str = "", query: str = "", max_results: int = 5) -> str:
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_key = os.getenv("QDRANT_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if not all([qdrant_url, qdrant_key, openai_key]):
            return json.dumps({"error": "Qdrant or OpenAI not configured. Knowledge base unavailable."})

        try:
            from qdrant_client import QdrantClient
            from openai import OpenAI

            client = QdrantClient(url=qdrant_url, api_key=qdrant_key)
            oai = OpenAI(api_key=openai_key)

            # Ensure collection exists
            self._ensure_collection(client)

            if action == "save":
                return self._save(client, oai, game_slug, game_data)
            elif action == "search":
                return self._search(client, oai, query, max_results)
            elif action == "list":
                return self._list_all(client)
            else:
                return json.dumps({"error": f"Unknown action: {action}. Use 'save', 'search', or 'list'."})

        except Exception as e:
            return json.dumps({"error": str(e)})

    def _ensure_collection(self, client):
        """Create the knowledge base collection if it doesn't exist."""
        from qdrant_client.models import VectorParams, Distance
        try:
            client.get_collection(self._collection)
        except Exception:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

    def _embed(self, oai, text: str) -> list[float]:
        resp = oai.embeddings.create(input=text[:8000], model="text-embedding-3-small")
        return resp.data[0].embedding

    def _save(self, client, oai, game_slug: str, game_data: str) -> str:
        from qdrant_client.models import PointStruct
        import uuid

        # Parse game data
        try:
            data = json.loads(game_data) if isinstance(game_data, str) else game_data
        except json.JSONDecodeError:
            data = {"raw": game_data}

        # Create searchable text
        searchable = f"""
Game: {game_slug}
Theme: {data.get('theme', '')}
Markets: {data.get('target_markets', '')}
Volatility: {data.get('volatility', '')}
RTP: {data.get('target_rtp', '')}
Features: {data.get('features', '')}
Grid: {data.get('grid', '')}
Art Style: {data.get('art_style', '')}
Summary: {json.dumps(data)[:3000]}
"""
        vector = self._embed(oai, searchable)

        point_id = str(uuid.uuid4())
        client.upsert(
            collection_name=self._collection,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "game_slug": game_slug,
                    "data": data,
                    "searchable_text": searchable[:2000],
                    "saved_at": datetime.now().isoformat(),
                },
            )],
        )

        return json.dumps({
            "status": "saved",
            "game_slug": game_slug,
            "point_id": point_id,
            "collection": self._collection,
        })

    def _search(self, client, oai, query: str, limit: int) -> str:
        vector = self._embed(oai, query)

        # qdrant-client >= 1.12 renamed .search() → .query_points()
        if hasattr(client, "query_points"):
            resp = client.query_points(
                collection_name=self._collection,
                query=vector,
                limit=limit,
            )
            results = resp.points
        else:
            results = client.search(
                collection_name=self._collection,
                query_vector=vector,
                limit=limit,
            )

        hits = []
        for r in results:
            hits.append({
                "game_slug": r.payload.get("game_slug", ""),
                "score": round(r.score, 3),
                "data": r.payload.get("data", {}),
                "saved_at": r.payload.get("saved_at", ""),
            })

        return json.dumps({
            "query": query,
            "results_count": len(hits),
            "past_designs": hits,
        }, indent=2)

    def _list_all(self, client) -> str:
        try:
            info = client.get_collection(self._collection)
            # Scroll through all points
            records, _ = client.scroll(
                collection_name=self._collection,
                limit=50,
                with_payload=True,
                with_vectors=False,
            )
            designs = [{
                "game_slug": r.payload.get("game_slug", ""),
                "saved_at": r.payload.get("saved_at", ""),
                "theme": r.payload.get("data", {}).get("theme", ""),
            } for r in records]

            return json.dumps({
                "total_designs": info.points_count,
                "designs": designs,
            }, indent=2)
        except Exception as e:
            return json.dumps({"total_designs": 0, "designs": [], "note": str(e)})
