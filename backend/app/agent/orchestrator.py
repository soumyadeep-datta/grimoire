"""
LangGraph ReAct agent orchestrator.

Uses langgraph.prebuilt.create_react_agent with SqliteSaver checkpointing
for durable, per-session conversation state.

Memory architecture:
    Both agent mode and direct RAG mode write to the same LangGraph SQLite
    checkpoint store, keyed by session_id. This gives a single source of truth
    for conversation history regardless of which query path was used.

State schema:
    GrimoireState extends MessagesState with ui_history — a list of per-turn
    block records that preserve thinking traces, tool execution metrics,
    source citations, and latency data across page reloads.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import GrimoireState
from app.agent.tools import ALL_TOOLS
from app.config import get_settings
from app.exceptions import AgentError, AgentTimeoutError

logger = logging.getLogger(__name__)

CHECKPOINT_DB_PATH = os.environ.get("CHECKPOINT_DB_PATH", "checkpoints.db")


@dataclass
class AgentResponse:
    """Structured response returned by the agent to the API layer."""
    answer: str
    tools_used: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)


class GrimoireAgent:
    """
    LangGraph ReAct agent with SqliteSaver checkpointing.

    Each session_id maps to a LangGraph thread_id, giving each user
    independent, persistent conversation state backed by SQLite.
    """

    def __init__(self):
        self._graph = None
        self._async_graph = None
        self._conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.commit()
        self._checkpointer = SqliteSaver(self._conn)

    def set_async_checkpointer(self, async_checkpointer) -> None:
        """Called from FastAPI lifespan with AsyncSqliteSaver instance."""
        self._async_graph = self._build_graph(async_checkpointer)
        logger.info("Async LangGraph agent built for streaming.")

    def _build_graph(self, checkpointer):
        s = get_settings()

        llm = ChatAnthropic(
            model=s.claude_model,
            api_key=s.anthropic_api_key,
            max_tokens=s.claude_max_tokens,
            temperature=s.claude_temperature,
            timeout=60.0,
        )

        graph = create_react_agent(
            model=llm,
            tools=ALL_TOOLS,
            prompt=SYSTEM_PROMPT,
            checkpointer=checkpointer,
            state_schema=GrimoireState,
        )

        logger.info(
            "LangGraph agent built | model=%s | tools=%s | state=GrimoireState",
            s.claude_model, [t.name for t in ALL_TOOLS]
        )
        return graph

    def get_graph(self):
        if self._graph is None:
            self._graph = self._build_graph(self._checkpointer)
        return self._graph

    def get_async_graph(self):
        if self._async_graph is None:
            self._async_graph = self._build_graph(self._async_checkpointer)
        return self._async_graph

    def run(self, question: str, session_id: str = "default") -> AgentResponse:
        graph = self.get_graph()
        config = {"configurable": {"thread_id": session_id}}

        logger.info("Running agent | session=%s | question='%s'", session_id, question[:100])

        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content=question)]},
                config=config,
            )
        except ValueError as exc:
            if "INVALID_CHAT_HISTORY" in str(exc) or "ToolMessage" in str(exc):
                logger.warning("Corrupted checkpoint for session '%s' — clearing and retrying", session_id)
                self.clear_session(session_id)
                result = graph.invoke(
                    {"messages": [HumanMessage(content=question)]},
                    config=config,
                )
            else:
                raise AgentError(f"Agent failed: {exc}") from exc
        except TimeoutError as exc:
            raise AgentTimeoutError() from exc
        except Exception as exc:
            err_str = str(exc)
            if "overloaded" in err_str.lower() or "529" in err_str:
                from app.exceptions import ServiceOverloadedError
                raise ServiceOverloadedError() from exc
            if "rate_limit" in err_str.lower() or "429" in err_str or "RateLimitError" in type(exc).__name__:
                from app.exceptions import RateLimitError
                raise RateLimitError() from exc
            logger.error("Agent failed: %s", exc, exc_info=True)
            raise AgentError(f"Agent failed: {exc}") from exc

        messages = result.get("messages", [])
        answer = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                answer = str(msg.content)
                break

        tools_used: list[dict[str, Any]] = []
        sources: set[str] = set()

        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    args = tc.get("args", {})
                    clean_input = args.get("query", args.get("code", str(args)))
                    tools_used.append({"tool": tc.get("name", "unknown"), "input": clean_input})
            if hasattr(msg, "content") and "| Source:" in str(msg.content):
                for line in str(msg.content).splitlines():
                    if "| Source:" in line:
                        sources.add(line.strip())

        return AgentResponse(answer=answer, tools_used=tools_used, sources=sorted(sources))

    async def arun(self, question: str, session_id: str = "default", **kwargs) -> AgentResponse:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.run, question, session_id)

    def add_to_checkpoint(self, session_id: str, question: str, answer: str) -> None:
        config = {"configurable": {"thread_id": session_id}}
        try:
            graph = self.get_graph()
            graph.update_state(config, {"messages": [HumanMessage(content=question), AIMessage(content=answer)]})
            logger.debug("Wrote direct RAG exchange to checkpoint | session=%s", session_id)
        except Exception as exc:
            logger.warning("Could not write to checkpoint for session %s: %s", session_id, exc)

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        """Return conversation history with optional rich UI blocks.

        Blocks are looked up by the AIMessage's unique ID — no index
        counting needed. This is immune to desync from direct RAG turns,
        state healing, or retries that modify the messages array.
        """
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = self.get_graph().get_state(config)
            messages = state.values.get("messages", [])
            ui_history: dict = state.values.get("ui_history", {})
            history: list[dict[str, Any]] = []

            for msg in messages:
                content = self._extract_text(msg.content)
                if not content.strip():
                    continue
                if isinstance(msg, HumanMessage):
                    history.append({"role": "user", "content": content, "blocks": []})
                elif isinstance(msg, AIMessage):
                    # Deterministic lookup by message ID — no index magic
                    blocks = ui_history.get(msg.id, [])
                    history.append({"role": "assistant", "content": content, "blocks": blocks})
            return history
        except Exception as exc:
            logger.warning("Could not retrieve history for session %s: %s", session_id, exc)
            return []

    @staticmethod
    def _extract_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        parts.append(text)
            return "".join(parts)
        return str(content)

    def get_history_string(self, session_id: str) -> str:
        history = self.get_history(session_id)
        if not history:
            return ""
        lines = []
        for msg in history:
            prefix = "User" if msg["role"] == "user" else "Grimoire"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)

    def clear_session(self, session_id: str) -> None:
        try:
            self._checkpointer.delete_thread(session_id)
            logger.info("Cleared session '%s'", session_id)
        except Exception as exc:
            logger.warning("Could not clear session '%s': %s", session_id, exc)


_agent: GrimoireAgent | None = None


def get_agent() -> GrimoireAgent:
    global _agent
    if _agent is None:
        _agent = GrimoireAgent()
    return _agent