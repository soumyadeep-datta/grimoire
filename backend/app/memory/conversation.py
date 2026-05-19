"""
Conversation memory management.

In LangGraph 1.x, session memory is managed via SqliteSaver checkpointing
in the agent itself (keyed by thread_id = session_id).

This module provides a thin compatibility layer for the API endpoints
that need to read/write conversation history independently of the agent.
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# Simple in-memory store for sessions not going through the agent
# (e.g. direct RAG mode which doesn't use LangGraph)
_sessions: dict[str, list[dict[str, str]]] = defaultdict(list)


def add_exchange(session_id: str, human_input: str, ai_output: str) -> None:
    """Persist a completed question-answer turn to the session."""
    _sessions[session_id].append({"role": "user", "content": human_input})
    _sessions[session_id].append({"role": "assistant", "content": ai_output})
    logger.debug("Saved exchange to session '%s'", session_id)


def get_history_string(session_id: str) -> str:
    """Return formatted conversation history for prompt injection."""
    messages = _sessions[session_id]
    if not messages:
        return ""
    lines = []
    for msg in messages:
        prefix = "User" if msg["role"] == "user" else "Grimoire"
        lines.append(f"{prefix}: {msg['content']}")
    return "\n".join(lines)


def get_history_list(session_id: str) -> list[dict[str, str]]:
    """Return a list of {role, content} dicts for the API /history endpoint."""
    return list(_sessions[session_id])


def clear_session(session_id: str) -> None:
    """Wipe the memory for a session."""
    if session_id in _sessions:
        del _sessions[session_id]
        logger.info("Cleared session '%s'", session_id)