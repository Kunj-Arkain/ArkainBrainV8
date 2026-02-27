"""
ARKAINBRAIN — Embedding Utilities (Phase 6)

Generates and compares vector embeddings for semantic search.
Uses OpenAI text-embedding-3-small (1536 dims).
Falls back to keyword-based similarity when API unavailable.
"""

import json
import logging
import math
import os
from typing import Optional

logger = logging.getLogger("arkainbrain.memory")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


def get_embedding(text: str) -> Optional[list[float]]:
    """Generate an embedding vector for the given text.
    Returns None if the API call fails (non-fatal)."""
    if not text or not text.strip():
        return None
    try:
        import openai
        client = openai.OpenAI()
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],  # Cap input to avoid token limits
        )
        return response.data[0].embedding
    except Exception as e:
        logger.debug(f"Embedding generation failed (non-fatal): {e}")
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_run_text(theme: str, volatility: str, features: list[str],
                   jurisdictions: list[str], grid: str = "",
                   gdd_summary: str = "", math_summary: str = "") -> str:
    """Build a text representation of a run for embedding."""
    parts = [
        f"Theme: {theme}",
        f"Volatility: {volatility}",
        f"Grid: {grid}" if grid else "",
        f"Features: {', '.join(features)}" if features else "",
        f"Markets: {', '.join(jurisdictions)}" if jurisdictions else "",
    ]
    if gdd_summary:
        parts.append(f"Design: {gdd_summary[:1000]}")
    if math_summary:
        parts.append(f"Math: {math_summary[:500]}")
    return "\n".join(p for p in parts if p)


def build_component_text(component_type: str, name: str,
                         description: str = "", tags: list[str] = None) -> str:
    """Build a text representation of a component for embedding."""
    parts = [
        f"Type: {component_type}",
        f"Name: {name}",
        f"Description: {description}" if description else "",
        f"Tags: {', '.join(tags)}" if tags else "",
    ]
    return "\n".join(p for p in parts if p)


def keyword_similarity(query: str, text: str) -> float:
    """Simple keyword-based similarity fallback when embeddings unavailable."""
    if not query or not text:
        return 0.0
    q_words = set(query.lower().split())
    t_words = set(text.lower().split())
    if not q_words:
        return 0.0
    overlap = q_words & t_words
    return len(overlap) / len(q_words)


def serialize_embedding(embedding: Optional[list[float]]) -> Optional[str]:
    """Serialize embedding to JSON string for storage."""
    if embedding is None:
        return None
    return json.dumps(embedding)


def deserialize_embedding(data: Optional[str]) -> Optional[list[float]]:
    """Deserialize embedding from JSON string."""
    if not data:
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None
