"""
Conversation memory. Maintains the last K exchanges per session_id.
Multiple users get independent memory buffers.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from langchain.memory import ConversationBufferWindowMemory

from app.config import get_settings

logger = logging.getLogger(__name__)

_sessions: dict[str, ConversationBufferWindowMemory] = defaultdict(
    lambda: ConversationBufferWindowMemory(
        k=get_settings().memory_window_k,
        memory_key="chat_history",
        return_messages=False,
        human_prefix="User",
        ai_prefix="Grimoire",
    )
)


def add_exchange(session_id: str, human_input: str, ai_output: str) -> None:
    _sessions[session_id].save_context({"input": human_input}, {"output": ai_output})


def get_history_string(session_id: str) -> str:
    variables = _sessions[session_id].load_memory_variables({})
    return variables.get("chat_history", "")


def get_history_list(session_id: str) -> list[dict[str, str]]:
    messages = _sessions[session_id].chat_memory.messages
    return [
        {"role": "user" if msg.type == "human" else "assistant", "content": msg.content}
        for msg in messages
    ]


def clear_session(session_id: str) -> None:
    if session_id in _sessions:
        del _sessions[session_id]
        logger.info("Cleared session '%s'", session_id)

