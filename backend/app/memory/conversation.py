"""
Conversation memory — superseded by LangGraph checkpointing.

This module previously managed in-memory conversation history.
It has been replaced by the LangGraph SqliteSaver checkpoint store
in app/agent/orchestrator.py, which provides:

    - Persistent storage across server restarts (SQLite-backed)
    - Unified memory across both agent mode and direct RAG mode
    - Per-session isolation via thread_id = session_id
    - Full message history accessible via agent.get_history(session_id)

This file is kept as a stub to avoid breaking any imports that reference it.
All history operations should go through GrimoireAgent methods:
    - agent.get_history(session_id)
    - agent.get_history_string(session_id)
    - agent.add_to_checkpoint(session_id, question, answer)
    - agent.clear_session(session_id)
"""


def add_exchange(session_id: str, human_input: str, ai_output: str) -> None:
    """Deprecated. History is managed by LangGraph checkpointer."""
    pass


def get_history_string(session_id: str) -> str:
    """Deprecated. Use agent.get_history_string(session_id) instead."""
    return ""


def get_history_list(session_id: str) -> list[dict[str, str]]:
    """Deprecated. Use agent.get_history(session_id) instead."""
    return []


def clear_session(session_id: str) -> None:
    """Deprecated. Use agent.clear_session(session_id) instead."""
    pass
