"""
ARKAINBRAIN — Pipeline Memory & Component Library (Phase 6)

Gives agents memory of past pipeline runs and reusable components.
Indexes completed runs with vector embeddings for semantic search.
Extracts paytables, feature configs, and RTP budgets as reusable components.

Usage:
    from memory import index_completed_run, get_memory_context

    # After pipeline completes:
    index_completed_run(job_id, pipeline_state, output_dir)

    # Before pipeline starts (inject into agent prompts):
    context = get_memory_context(game_idea)
"""

from memory.run_indexer import index_completed_run
from memory.query_engine import get_memory_context, search_similar_runs, search_components
from memory.component_extractor import extract_components
from memory.prompt_injector import build_memory_prompt

__all__ = [
    "index_completed_run",
    "get_memory_context",
    "search_similar_runs",
    "search_components",
    "extract_components",
    "build_memory_prompt",
]
