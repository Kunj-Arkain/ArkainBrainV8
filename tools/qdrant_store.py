"""
Automated Slot Studio — Qdrant Jurisdiction Store

Single source of truth for ALL jurisdiction data (US states + international).
No static files. Everything lives in Qdrant, populated by:
  - State Recon Pipeline (US states)
  - Manual ingestion (international regs)

Usage:
    from tools.qdrant_store import JurisdictionStore
    store = JurisdictionStore()

    # Search
    results = store.search("North Carolina skill game exemption")

    # Search with jurisdiction filter
    results = store.search("prize limits", jurisdiction="Georgia")

    # Check if a state has been researched
    store.has_jurisdiction("North Carolina")  # True/False

    # List all researched jurisdictions
    store.list_jurisdictions()
"""

import json
import os
from typing import Optional

from dotenv import load_dotenv
load_dotenv()


class JurisdictionStore:
    """
    Qdrant-backed jurisdiction intelligence store.

    This is the ONLY place jurisdiction data should be read from.
    If a jurisdiction isn't in Qdrant, it needs to be researched first
    via the State Recon Pipeline.
    """

    def __init__(self):
        self.qdrant_url = os.getenv("QDRANT_URL", "")
        self.qdrant_key = os.getenv("QDRANT_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.collection = os.getenv("QDRANT_COLLECTION", "slot_regulations")
        self.embedding_model = "text-embedding-3-small"
        self._client = None

    @property
    def is_available(self) -> bool:
        """Check if Qdrant connection is configured."""
        return bool(self.qdrant_url and self.openai_key)

    def _get_client(self):
        """Lazy-init Qdrant client."""
        if self._client is None:
            from qdrant_client import QdrantClient
            if self.qdrant_key:
                self._client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_key)
            else:
                self._client = QdrantClient(url=self.qdrant_url)
        return self._client

    def _embed(self, text: str) -> list[float]:
        """Generate embedding for a query."""
        from openai import OpenAI
        client = OpenAI(api_key=self.openai_key)
        resp = client.embeddings.create(model=self.embedding_model, input=text)
        return resp.data[0].embedding

    def search(
        self,
        query: str,
        jurisdiction: Optional[str] = None,
        limit: int = 8,
        score_threshold: float = 0.3,
    ) -> list[dict]:
        """
        Semantic search across all jurisdiction data.

        Args:
            query: Natural language query
            jurisdiction: Optional filter to specific jurisdiction
            limit: Max results
            score_threshold: Minimum relevance score

        Returns:
            List of matching chunks with text, jurisdiction, score, source
        """
        if not self.is_available:
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            client = self._get_client()
            query_vec = self._embed(query)

            # Build filter
            filter_conditions = []
            if jurisdiction:
                filter_conditions.append(
                    FieldCondition(key="jurisdiction", match=MatchValue(value=jurisdiction))
                )
            search_filter = Filter(must=filter_conditions) if filter_conditions else None

            # qdrant-client >= 1.12 renamed .search() → .query_points()
            def _do_search(qf=None):
                if hasattr(client, "query_points"):
                    resp = client.query_points(
                        collection_name=self.collection,
                        query=query_vec,
                        query_filter=qf,
                        limit=limit,
                        score_threshold=score_threshold,
                    )
                    return resp.points
                else:
                    return client.search(
                        collection_name=self.collection,
                        query_vector=query_vec,
                        query_filter=qf,
                        limit=limit,
                        score_threshold=score_threshold,
                    )

            results = _do_search(search_filter)

            # If filtered search returns nothing, retry without filter
            if not results and jurisdiction:
                results = _do_search(None)

            return [{
                "score": round(hit.score, 3),
                "text": hit.payload.get("text", ""),
                "jurisdiction": hit.payload.get("jurisdiction", "unknown"),
                "source": hit.payload.get("source", "unknown"),
                "filename": hit.payload.get("filename", "unknown"),
                "category": hit.payload.get("category", "general"),
            } for hit in results]

        except Exception as e:
            return [{"error": str(e)}]

    def has_jurisdiction(self, jurisdiction: str) -> bool:
        """Check if any data exists for a jurisdiction in Qdrant."""
        if not self.is_available:
            return False

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            client = self._get_client()
            count = client.count(
                collection_name=self.collection,
                count_filter=Filter(must=[
                    FieldCondition(key="jurisdiction", match=MatchValue(value=jurisdiction))
                ]),
            )
            return count.count > 0
        except Exception:
            return False

    def list_jurisdictions(self) -> list[str]:
        """List all jurisdictions that have data in Qdrant."""
        if not self.is_available:
            return []

        try:
            client = self._get_client()

            # Scroll through all points and collect unique jurisdictions
            jurisdictions = set()
            offset = None
            while True:
                results, offset = client.scroll(
                    collection_name=self.collection,
                    limit=100,
                    offset=offset,
                    with_payload=["jurisdiction"],
                )
                for point in results:
                    j = point.payload.get("jurisdiction", "unknown")
                    if j != "unknown":
                        jurisdictions.add(j)
                if offset is None:
                    break

            return sorted(jurisdictions)
        except Exception:
            return []

    def get_jurisdiction_summary(self, jurisdiction: str) -> Optional[dict]:
        """
        Get a structured summary for a jurisdiction by searching for key topics.
        Returns None if no data exists.
        """
        if not self.has_jurisdiction(jurisdiction):
            return None

        summary = {"jurisdiction": jurisdiction, "sections": {}}

        search_topics = {
            "gambling_definition": f"{jurisdiction} gambling definition legal elements",
            "exemptions": f"{jurisdiction} exemption skill game amusement device",
            "enforcement": f"{jurisdiction} enforcement prosecution risk",
            "prize_rules": f"{jurisdiction} prize payout limits restrictions",
            "licensing": f"{jurisdiction} licensing requirements fees",
            "game_design": f"{jurisdiction} compliant game design mechanics",
        }

        for topic, query in search_topics.items():
            results = self.search(query, jurisdiction=jurisdiction, limit=3)
            if results and "error" not in results[0]:
                summary["sections"][topic] = [r["text"][:500] for r in results]

        return summary if summary["sections"] else None

    def get_status(self) -> dict:
        """Get store health and stats."""
        if not self.is_available:
            return {
                "status": "NOT_CONFIGURED",
                "message": "Set QDRANT_URL and OPENAI_API_KEY in .env",
                "jurisdictions": [],
                "total_vectors": 0,
            }

        try:
            client = self._get_client()
            info = client.get_collection(self.collection)
            jurisdictions = self.list_jurisdictions()

            return {
                "status": "ONLINE",
                "collection": self.collection,
                "total_vectors": info.points_count,
                "jurisdictions": jurisdictions,
                "jurisdiction_count": len(jurisdictions),
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "message": str(e),
                "jurisdictions": [],
                "total_vectors": 0,
            }
