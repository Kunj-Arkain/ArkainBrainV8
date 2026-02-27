"""
Automated Slot Studio — Legal Research Tool

Multi-pass web search specialized for state gambling law research.
Searches statutes, case law, AG opinions, enforcement patterns, and
legislative activity to build a comprehensive legal picture of any
US state's gaming landscape.

Designed for the State Recon Agent to autonomously research new jurisdictions.
"""

import json
import os
from typing import Optional

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ============================================================
# Search Strategy Templates
# ============================================================

SEARCH_PASSES = {
    "statutes": {
        "description": "Core gambling statutes and definitions",
        "queries": [
            "{state} gambling statute definition",
            "{state} penal code gambling lottery definition",
            "{state} amusement device skill game exemption law",
            "{state} coin-operated amusement machine statute",
            "{state} sweepstakes promotion statute",
        ],
    },
    "definitions": {
        "description": "Legal definitions that determine what counts as gambling",
        "queries": [
            "{state} legal definition 'game of chance' vs 'game of skill'",
            "{state} gambling definition 'consideration' 'prize' 'chance'",
            "{state} skill game predominance test legal standard",
            "{state} amusement device definition law code",
        ],
    },
    "exemptions": {
        "description": "Carve-outs and exemptions from gambling prohibition",
        "queries": [
            "{state} gambling exemption amusement arcade skill",
            "{state} fraternal veterans organization gaming exemption",
            "{state} social gambling exception law",
            "{state} sweepstakes contest promotion exemption gambling",
            "{state} charitable gaming bingo exemption",
        ],
    },
    "case_law": {
        "description": "Court rulings defining skill vs chance, device classifications",
        "queries": [
            "{state} supreme court skill game gambling ruling",
            "{state} court ruling slot machine amusement device",
            "{state} gambling prosecution skill game case",
            "{state} attorney general opinion gaming device",
        ],
    },
    "enforcement": {
        "description": "How aggressively the state enforces and recent actions",
        "queries": [
            "{state} gaming enforcement action seizure 2024 2025",
            "{state} gambling crackdown skill game raid",
            "{state} attorney general gaming enforcement",
            "{state} gaming commission enforcement actions",
        ],
    },
    "legislation": {
        "description": "Pending and recent legislative activity",
        "queries": [
            "{state} gambling bill 2025 2026 legislature",
            "{state} skill game legislation pending",
            "{state} gaming expansion bill",
            "{state} video gaming terminal legalization",
        ],
    },
    "market": {
        "description": "Existing gray/legal market presence",
        "queries": [
            "{state} skill game market operators",
            "{state} amusement device gaming industry",
            "{state} gaming revenue statistics",
        ],
    },
}


# ============================================================
# Input Schema
# ============================================================

class LegalResearchInput(BaseModel):
    state: str = Field(description="US state to research, e.g. 'North Carolina'")
    search_pass: str = Field(
        default="all",
        description=(
            "Which search pass to execute: 'statutes', 'definitions', 'exemptions', "
            "'case_law', 'enforcement', 'legislation', 'market', or 'all' for full recon"
        ),
    )
    custom_query: Optional[str] = Field(
        default=None,
        description="Optional custom search query (overrides search_pass templates)",
    )


# ============================================================
# Legal Research Tool
# ============================================================

class LegalResearchTool(BaseTool):
    """
    Multi-pass web search for state gambling law research.

    Executes targeted search queries across legal databases, court records,
    AG opinions, and news sources. Returns structured results the agents
    can reason over.

    Requires SERPER_API_KEY env var.
    """

    name: str = "legal_research"
    description: str = (
        "Research any US state's gambling laws, definitions, exemptions, court rulings, "
        "and enforcement patterns. Use search_pass='all' for comprehensive recon on a new "
        "state, or target specific passes like 'statutes', 'definitions', 'exemptions', "
        "'case_law', 'enforcement', 'legislation', 'market'. Returns structured legal intelligence."
    )
    args_schema: type[BaseModel] = LegalResearchInput

    def _run(self, state: str, search_pass: str = "all", custom_query: Optional[str] = None) -> str:
        serper_key = os.getenv("SERPER_API_KEY")
        if not serper_key:
            return json.dumps({
                "error": "SERPER_API_KEY not set",
                "fallback_instruction": (
                    "Use your training knowledge about gambling law to analyze "
                    f"{state}'s gaming regulations. Focus on: (1) how {state} defines "
                    "'gambling', (2) what exemptions exist for skill games/amusement devices/"
                    "sweepstakes, (3) key court rulings, (4) enforcement posture."
                ),
            })

        try:
            import httpx
        except ImportError:
            return json.dumps({"error": "httpx not installed. Run: pip install httpx"})

        # Build query list
        if custom_query:
            queries = [custom_query]
            passes_used = ["custom"]
        elif search_pass == "all":
            queries = []
            passes_used = list(SEARCH_PASSES.keys())
            for pass_name, pass_data in SEARCH_PASSES.items():
                for qt in pass_data["queries"]:
                    queries.append(qt.format(state=state))
        elif search_pass in SEARCH_PASSES:
            passes_used = [search_pass]
            queries = [qt.format(state=state) for qt in SEARCH_PASSES[search_pass]["queries"]]
        else:
            return json.dumps({"error": f"Unknown search_pass: {search_pass}. Options: {list(SEARCH_PASSES.keys()) + ['all']}"})

        # Execute searches via Serper
        all_results = []
        seen_urls = set()

        for query in queries:
            try:
                resp = httpx.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
                    json={"q": query, "num": 5},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("organic", []):
                        url = item.get("link", "")
                        if url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append({
                                "query": query,
                                "title": item.get("title", ""),
                                "url": url,
                                "snippet": item.get("snippet", ""),
                                "source_type": self._classify_source(url, item.get("title", "")),
                            })
            except Exception as e:
                all_results.append({"query": query, "error": str(e)})

        # Score and prioritize results
        prioritized = self._prioritize_results(all_results, state)

        return json.dumps({
            "state": state,
            "search_passes_executed": passes_used,
            "total_queries": len(queries),
            "unique_results": len(prioritized),
            "results": prioritized[:40],  # Cap at 40 most relevant
            "analysis_instructions": (
                f"Analyze these results to build a legal profile for {state}. "
                "Extract: (1) EXACT statutory definitions of 'gambling', 'lottery', "
                "'game of chance', 'amusement device'; (2) ALL exemptions/carve-outs; "
                "(3) key court rulings with case names; (4) AG opinions; "
                "(5) enforcement posture (aggressive/moderate/lax); "
                "(6) pending legislation. "
                "For each exemption found, note the SPECIFIC requirements a game must "
                "meet to qualify."
            ),
        }, indent=2)

    def _classify_source(self, url: str, title: str) -> str:
        """Classify source reliability tier."""
        url_lower = url.lower()
        title_lower = title.lower()

        if any(d in url_lower for d in [".gov", "legislature.", "legis.", "law.", "courts."]):
            return "OFFICIAL_GOVERNMENT"
        if any(d in url_lower for d in ["westlaw", "lexis", "casetext", "courtlistener", "scholar.google"]):
            return "LEGAL_DATABASE"
        if any(d in url_lower for d in ["law.cornell", "findlaw", "justia"]):
            return "LEGAL_REFERENCE"
        if any(t in title_lower for t in ["attorney general", "ag opinion", "formal opinion"]):
            return "AG_OPINION"
        if any(d in url_lower for d in ["reuters", "law360", "bloomberg"]):
            return "LEGAL_NEWS"
        if any(d in url_lower for d in ["gaming", "igaming", "casino", "yogonet", "cdcgaming"]):
            return "INDUSTRY_SOURCE"
        return "GENERAL"

    def _prioritize_results(self, results: list, state: str) -> list:
        """Score results by relevance and source quality."""
        tier_scores = {
            "OFFICIAL_GOVERNMENT": 10,
            "LEGAL_DATABASE": 9,
            "AG_OPINION": 9,
            "LEGAL_REFERENCE": 7,
            "LEGAL_NEWS": 5,
            "INDUSTRY_SOURCE": 4,
            "GENERAL": 2,
        }

        state_lower = state.lower()
        for r in results:
            if "error" in r:
                r["priority_score"] = 0
                continue
            score = tier_scores.get(r.get("source_type", "GENERAL"), 2)
            # Boost if state name in title/snippet
            if state_lower in r.get("title", "").lower():
                score += 3
            if state_lower in r.get("snippet", "").lower():
                score += 1
            # Boost legal keywords
            text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
            for kw in ["skill game", "amusement", "exemption", "definition", "gambling",
                        "court ruled", "statute", "attorney general", "loophole"]:
                if kw in text:
                    score += 1
            # Boost recency markers
            for year in ["2025", "2026", "2024"]:
                if year in text:
                    score += 2
                    break
            r["priority_score"] = score

        return sorted(
            [r for r in results if "error" not in r],
            key=lambda x: x.get("priority_score", 0),
            reverse=True,
        )


# ============================================================
# Statute Fetcher Tool (follows up on specific URLs)
# ============================================================

class StatuteFetchInput(BaseModel):
    url: str = Field(description="URL to fetch full text from (statute page, court opinion, etc)")
    extract_sections: Optional[str] = Field(
        default=None,
        description="Optional: specific section numbers to extract, e.g. '14-292, 14-306'",
    )


class StatuteFetchTool(BaseTool):
    """
    Fetches full text from legal URLs found by LegalResearchTool.
    Extracts and cleans statute text, court opinions, and AG letters.
    """

    name: str = "fetch_statute"
    description: str = (
        "Fetch full text of a statute, court opinion, or AG opinion from a URL. "
        "Use after legal_research tool identifies relevant sources. "
        "Extracts and cleans the legal text for analysis."
    )
    args_schema: type[BaseModel] = StatuteFetchInput

    def _run(self, url: str, extract_sections: Optional[str] = None) -> str:
        try:
            import httpx
        except ImportError:
            return json.dumps({"error": "httpx not installed"})

        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (research bot)"},
                timeout=20.0,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return json.dumps({"error": f"HTTP {resp.status_code}", "url": url})

            text = resp.text

            # Strip HTML if needed
            if "<html" in text.lower()[:200]:
                text = self._strip_html(text)

            # Truncate to reasonable size
            if len(text) > 30000:
                text = text[:30000] + "\n\n[... TRUNCATED — full text exceeds 30KB ...]"

            # Extract specific sections if requested
            if extract_sections:
                sections = [s.strip() for s in extract_sections.split(",")]
                extracted = self._extract_sections(text, sections)
                if extracted:
                    text = extracted

            return json.dumps({
                "url": url,
                "length_chars": len(text),
                "text": text,
                "extraction_note": (
                    f"Sections requested: {extract_sections}" if extract_sections
                    else "Full document returned"
                ),
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e), "url": url})

    def _strip_html(self, html: str) -> str:
        """Basic HTML to text conversion."""
        import re
        # Remove script/style blocks
        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Convert block elements to newlines
        text = re.sub(r'</(p|div|h[1-6]|li|tr|br)>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
        # Remove all remaining tags
        text = re.sub(r'<[^>]+>', '', text)
        # Clean up whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    def _extract_sections(self, text: str, sections: list) -> Optional[str]:
        """Extract specific statute section numbers from text."""
        import re
        extracted = []
        for section in sections:
            # Try to find section marker and grab surrounding context
            patterns = [
                rf'(§\s*{re.escape(section)}[.\s].*?)(?=§\s*\d|\Z)',
                rf'(Section\s+{re.escape(section)}[.\s].*?)(?=Section\s+\d|\Z)',
                rf'({re.escape(section)}[.\s—\-].*?)(?=\n\d+[\-.]|\Z)',
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                if match:
                    extracted.append(match.group(1).strip()[:3000])
                    break

        if extracted:
            return "\n\n---\n\n".join(extracted)
        return None
