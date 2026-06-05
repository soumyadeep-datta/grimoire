"""
Extended LangGraph state schema for Grimoire.

Adds ui_history alongside the default AgentState (which includes both
messages and remaining_steps — required by create_react_agent).

Using a dict keyed by message ID prevents index-mismatch from direct
RAG turns, state healing, or retries. Dict merges are idempotent.
"""

from __future__ import annotations

from typing import Annotated

from langgraph.prebuilt.chat_agent_executor import AgentState


def _merge_ui_history(left: dict, right: dict) -> dict:
    """Shallow merge — new keys are added, existing keys are overwritten."""
    return {**left, **right}


class GrimoireState(AgentState):
    """Agent state with polymorphic UI history blocks.

    Extends AgentState (messages + remaining_steps) with ui_history — a dict
    mapping AIMessage IDs to their block arrays.
    """
    ui_history: Annotated[dict[str, list[dict]], _merge_ui_history]
