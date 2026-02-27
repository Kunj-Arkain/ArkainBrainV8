"""
ArkainBrain — Context Window Guardian v2

Patches the OpenAI Python SDK to prevent context_length_exceeded AND
tool_calls pairing errors. The key insight: OpenAI requires that every
assistant message with tool_calls is immediately followed by tool messages
for each tool_call_id. Truncation must treat these as ATOMIC GROUPS.

Message structure constraint:
    assistant(tool_calls=[{id:"tc_1"},{id:"tc_2"}])
    tool(tool_call_id="tc_1", content="...")
    tool(tool_call_id="tc_2", content="...")
    ^--- these 3 messages are ONE atomic group. Drop all or none.

Usage:
    import config.context_guard  # auto-registers on import
"""

import json
import logging

logger = logging.getLogger("arkainbrain.context_guard")

# ── Model context limits (safe input budget) ──
MODEL_LIMITS = {
    "gpt-5": 200_000, "gpt-5-mini": 200_000,
    "gpt-5.1": 200_000, "gpt-5.2": 200_000,
    "gpt-4o": 96_000, "gpt-4o-mini": 96_000,
    "gpt-4-turbo": 96_000,
}
DEFAULT_LIMIT = 120_000


# ── Token estimation ──

def _est_tokens(text):
    if not text:
        return 0
    return len(text if isinstance(text, str) else str(text)) // 3


def _msg_tokens(msg):
    total = 4
    if isinstance(msg, dict):
        content = msg.get("content") or ""
        tc = msg.get("tool_calls")
    elif hasattr(msg, "content"):
        content = getattr(msg, "content", "") or ""
        tc = getattr(msg, "tool_calls", None)
    else:
        return _est_tokens(str(msg))

    if isinstance(content, str):
        total += _est_tokens(content)
    elif isinstance(content, list):
        for p in content:
            total += _est_tokens(str(p))
    if tc:
        total += _est_tokens(json.dumps(tc) if isinstance(tc, (list, dict)) else str(tc))
    return total


def _total_tokens(messages):
    return sum(_msg_tokens(m) for m in messages) if messages else 0


def _get_limit(model):
    if not model:
        return DEFAULT_LIMIT
    name = str(model).split("/")[-1] if "/" in str(model) else str(model)
    for key, lim in MODEL_LIMITS.items():
        if key in name:
            return lim
    return DEFAULT_LIMIT


# ── Message helpers ──

def _get(msg, key, default=""):
    if isinstance(msg, dict):
        return msg.get(key, default)
    return getattr(msg, key, default)


def _truncate_content(content, max_chars):
    if not isinstance(content, str) or len(content) <= max_chars:
        return content
    half = max_chars // 2
    cut = len(content) - max_chars
    return content[:half] + f"\n\n[...{cut:,} chars truncated...]\n\n" + content[-half:]


def _to_dict(msg):
    """Convert any message type to a plain mutable dict."""
    if isinstance(msg, dict):
        return dict(msg)
    try:
        if hasattr(msg, "model_dump"):
            return msg.model_dump()
        if hasattr(msg, "dict"):
            return msg.dict()
    except Exception:
        pass
    d = {}
    for key in ("role", "content", "tool_calls", "tool_call_id", "name", "function_call"):
        val = getattr(msg, key, None)
        if val is not None:
            d[key] = val
    return d if "role" in d else {"role": "user", "content": str(msg)}


def _has_tool_calls(msg):
    """Check if a message has tool_calls (assistant requesting tool use)."""
    tc = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
    return bool(tc)


# ── Atomic group identification ──

def _identify_groups(msgs):
    """
    Partition messages into atomic groups that respect tool_call pairing.

    Returns list of groups, where each group is a list of indices.
    A tool-call group = [assistant_with_tool_calls, tool_result_1, tool_result_2, ...]
    All other messages are individual groups of size 1.
    """
    groups = []
    i = 0
    n = len(msgs)

    while i < n:
        msg = msgs[i]
        role = msg.get("role", "")

        # Check if this is an assistant message with tool_calls
        if role == "assistant" and _has_tool_calls(msg):
            # Start a group: this assistant + all following tool messages
            group = [i]
            j = i + 1
            while j < n and msgs[j].get("role") == "tool":
                group.append(j)
                j += 1
            groups.append(group)
            i = j
        else:
            groups.append([i])
            i += 1

    return groups


def _group_tokens(msgs, group):
    """Total tokens for a group of message indices."""
    return sum(_msg_tokens(msgs[i]) for i in group)


# ── Core truncation ──

def truncate_messages(messages, limit):
    """
    Truncate message list to fit within token limit while preserving
    tool_call/tool_result pairing integrity.

    Strategy (escalating):
    1. Shrink tool result content > 6K to 6K (head+tail)
    2. Shrink tool result content > 3K to 3K
    3. Drop oldest non-protected GROUPS (atomic tool-call groups)
    4. Nuclear: shrink ALL content > 1.5K
    5. Final validation: ensure structural integrity
    """
    if not messages:
        return messages

    msgs = [_to_dict(m) for m in messages]
    total = _total_tokens(msgs)
    if total <= limit:
        return msgs

    logger.warning(f"[GUARD] ~{total:,} tokens > {limit:,} limit. Truncating {len(msgs)} msgs...")

    # ── Pass 1: Shrink large tool/assistant content to 6K ──
    for msg in msgs:
        role = msg.get("role", "")
        content = msg.get("content") or ""
        if role in ("tool", "assistant") and isinstance(content, str) and len(content) > 8000:
            msg["content"] = _truncate_content(content, 6000)

    total = _total_tokens(msgs)
    if total <= limit:
        return _validate_structure(msgs)

    # ── Pass 2: Shrink to 3K ──
    for msg in msgs:
        role = msg.get("role", "")
        content = msg.get("content") or ""
        if role in ("tool", "assistant") and isinstance(content, str) and len(content) > 4000:
            msg["content"] = _truncate_content(content, 3000)

    total = _total_tokens(msgs)
    if total <= limit:
        return _validate_structure(msgs)

    # ── Pass 3: Drop oldest non-protected ATOMIC GROUPS ──
    groups = _identify_groups(msgs)

    # Classify groups as protected or droppable
    keep_tail_groups = min(6, len(groups))  # Protect last N groups
    protected_groups = set()

    # Protect: system messages, first user message
    for gi, group in enumerate(groups):
        for idx in group:
            if msgs[idx].get("role") == "system":
                protected_groups.add(gi)
                break
    for gi, group in enumerate(groups):
        for idx in group:
            if msgs[idx].get("role") == "user":
                protected_groups.add(gi)
                break  # Only protect FIRST user message
        if protected_groups:
            break

    # Protect last N groups
    for gi in range(max(0, len(groups) - keep_tail_groups), len(groups)):
        protected_groups.add(gi)

    # Drop entire groups from oldest first
    drop_indices = set()
    dropped_groups = 0
    for gi in range(len(groups)):
        if total <= limit:
            break
        if gi in protected_groups:
            continue
        for idx in groups[gi]:
            total -= _msg_tokens(msgs[idx])
            drop_indices.add(idx)
        dropped_groups += 1

    if drop_indices:
        msgs = [m for i, m in enumerate(msgs) if i not in drop_indices]
        logger.info(f"[GUARD] Pass 3: dropped {dropped_groups} groups ({len(drop_indices)} msgs), ~{total:,} tokens")

    if total <= limit:
        return _validate_structure(msgs)

    # ── Pass 4: Nuclear — truncate ALL content > 1.5K ──
    for msg in msgs:
        content = msg.get("content") or ""
        if isinstance(content, str) and len(content) > 2000:
            old_t = _msg_tokens(msg)
            msg["content"] = _truncate_content(content, 1500)
            total -= (old_t - _msg_tokens(msg))

    logger.warning(f"[GUARD] Pass 4 (nuclear): ~{total:,} tokens, {len(msgs)} msgs")
    return _validate_structure(msgs)


def _validate_structure(msgs):
    """
    Ensure the message array is structurally valid for the OpenAI API.

    Rules:
    - Every assistant message with tool_calls must be followed by
      tool messages for each tool_call_id
    - No orphan tool messages (tool without preceding assistant+tool_calls)

    If broken, repair by removing the offending group.
    """
    result = []
    i = 0
    n = len(msgs)

    while i < n:
        msg = msgs[i]
        role = msg.get("role", "")

        if role == "assistant" and _has_tool_calls(msg):
            # Collect expected tool_call_ids
            tc = msg.get("tool_calls", [])
            if isinstance(tc, list):
                expected_ids = set()
                for call in tc:
                    if isinstance(call, dict):
                        cid = call.get("id")
                    else:
                        cid = getattr(call, "id", None)
                    if cid:
                        expected_ids.add(cid)
            else:
                expected_ids = set()

            # Collect following tool messages
            tool_msgs = []
            j = i + 1
            while j < n and msgs[j].get("role") == "tool":
                tool_msgs.append(msgs[j])
                j += 1

            found_ids = set()
            for tm in tool_msgs:
                tcid = tm.get("tool_call_id")
                if tcid:
                    found_ids.add(tcid)

            if expected_ids and not expected_ids.issubset(found_ids):
                # Broken pair — drop entire group
                missing = expected_ids - found_ids
                logger.warning(
                    f"[GUARD] Dropping broken tool group: "
                    f"{len(expected_ids)} calls, {len(found_ids)} results, "
                    f"missing: {missing}"
                )
                i = j  # Skip past this broken group
                continue

            # Valid group — keep all
            result.append(msg)
            result.extend(tool_msgs)
            i = j

        elif role == "tool":
            # Orphan tool message (no preceding assistant+tool_calls)
            # Check if the previous message in result is the right assistant
            if result and result[-1].get("role") == "assistant" and _has_tool_calls(result[-1]):
                result.append(msg)
            else:
                logger.warning(f"[GUARD] Dropping orphan tool message (tool_call_id={msg.get('tool_call_id', '?')})")
            i += 1
        else:
            result.append(msg)
            i += 1

    return result


# ── Error detection ──

def _is_context_error(exc):
    s = str(exc).lower()
    return any(k in s for k in [
        "context_length_exceeded", "maximum context length",
        "input tokens exceed", "too many tokens",
    ])


def _is_tool_pairing_error(exc):
    s = str(exc).lower()
    return any(k in s for k in [
        "tool_calls", "tool_call_id",
        "must be followed by tool messages",
        "an assistant message with",
    ])


# ════════════════════════════════════════════════════════════
# OpenAI SDK monkey-patch
# ════════════════════════════════════════════════════════════

_patched = False


def _patch_openai():
    global _patched
    if _patched:
        return
    _patched = True

    try:
        import openai
    except ImportError:
        logger.debug("[GUARD] openai not installed — skipped")
        return

    # ── Sync patch ──
    try:
        from openai.resources.chat.completions import Completions
        _orig_create = Completions.create

        def _guarded_create(self, *args, **kwargs):
            messages = kwargs.get("messages")
            model = str(kwargs.get("model", ""))

            if messages:
                limit = _get_limit(model)
                est = _total_tokens(messages)

                # Always validate structure (even under token limit)
                if est > limit * 0.80:
                    logger.warning(f"[GUARD] Pre-flight: ~{est:,} tokens for {model} (limit {limit:,})")
                    kwargs["messages"] = truncate_messages(messages, limit)
                else:
                    # Still validate tool pairing even if under token limit
                    kwargs["messages"] = _validate_structure(
                        [_to_dict(m) for m in messages]
                    )

            try:
                return _orig_create(self, *args, **kwargs)
            except Exception as e:
                # Retry on context overflow
                if _is_context_error(e):
                    logger.error(f"[GUARD] Context overflow for {model}. Retrying at 60%...")
                    msgs = kwargs.get("messages", [])
                    kwargs["messages"] = truncate_messages(msgs, _get_limit(model) * 6 // 10)
                    return _orig_create(self, *args, **kwargs)

                # Retry on tool pairing error — re-validate structure
                if _is_tool_pairing_error(e):
                    logger.error(f"[GUARD] Tool pairing error. Re-validating structure...")
                    msgs = kwargs.get("messages", [])
                    clean = _validate_structure([_to_dict(m) for m in msgs])
                    kwargs["messages"] = clean
                    return _orig_create(self, *args, **kwargs)

                raise

        Completions.create = _guarded_create
        logger.info("[GUARD] Patched openai Completions.create")
    except Exception as e:
        logger.warning(f"[GUARD] Failed to patch sync: {e}")

    # ── Async patch ──
    try:
        from openai.resources.chat.completions import AsyncCompletions
        _orig_acreate = AsyncCompletions.create

        async def _guarded_acreate(self, *args, **kwargs):
            messages = kwargs.get("messages")
            model = str(kwargs.get("model", ""))

            if messages:
                limit = _get_limit(model)
                est = _total_tokens(messages)
                if est > limit * 0.80:
                    kwargs["messages"] = truncate_messages(messages, limit)
                else:
                    kwargs["messages"] = _validate_structure(
                        [_to_dict(m) for m in messages]
                    )

            try:
                return await _orig_acreate(self, *args, **kwargs)
            except Exception as e:
                if _is_context_error(e):
                    msgs = kwargs.get("messages", [])
                    kwargs["messages"] = truncate_messages(msgs, _get_limit(model) * 6 // 10)
                    return await _orig_acreate(self, *args, **kwargs)
                if _is_tool_pairing_error(e):
                    msgs = kwargs.get("messages", [])
                    kwargs["messages"] = _validate_structure([_to_dict(m) for m in msgs])
                    return await _orig_acreate(self, *args, **kwargs)
                raise

        AsyncCompletions.create = _guarded_acreate
        logger.info("[GUARD] Patched openai AsyncCompletions.create")
    except Exception as e:
        logger.warning(f"[GUARD] Failed to patch async: {e}")


# ════════════════════════════════════════════════════════════
# litellm monkey-patch (secondary)
# ════════════════════════════════════════════════════════════

def _patch_litellm():
    try:
        import litellm
        _orig = litellm.completion

        def _guarded(*args, **kwargs):
            messages = kwargs.get("messages") or (args[1] if len(args) > 1 else None)
            model = str(kwargs.get("model") or (args[0] if args else ""))
            if messages and isinstance(messages, list):
                limit = _get_limit(model)
                est = _total_tokens(messages)
                if est > limit * 0.80:
                    truncated = truncate_messages(messages, limit)
                    kwargs["messages"] = truncated
                    if len(args) > 1:
                        args = (args[0], truncated) + args[2:]
                else:
                    clean = _validate_structure([_to_dict(m) for m in messages])
                    kwargs["messages"] = clean
                    if len(args) > 1:
                        args = (args[0], clean) + args[2:]
            try:
                return _orig(*args, **kwargs)
            except Exception as e:
                if _is_context_error(e):
                    msgs = kwargs.get("messages", [])
                    kwargs["messages"] = truncate_messages(msgs, _get_limit(model) * 6 // 10)
                    return _orig(*args, **kwargs)
                if _is_tool_pairing_error(e):
                    msgs = kwargs.get("messages", [])
                    kwargs["messages"] = _validate_structure([_to_dict(m) for m in msgs])
                    return _orig(*args, **kwargs)
                raise

        litellm.completion = _guarded
        logger.info("[GUARD] Patched litellm.completion")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[GUARD] Failed to patch litellm: {e}")


# Auto-register
_patch_openai()
_patch_litellm()
