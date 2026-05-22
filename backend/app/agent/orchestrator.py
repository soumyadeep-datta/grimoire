"""
LangGraph ReAct agent orchestrator.

Uses langgraph.prebuilt.create_react_agent with SqliteSaver checkpointing
for durable, per-session conversation state.

LangGraph 1.2 replaces the deprecated LangChain AgentExecutor pattern.
SqliteSaver provides thread-safe persistent checkpointing keyed by thread_id.

Memory architecture:
    Both agent mode and direct RAG mode write to the same LangGraph SQLite
    checkpoint store, keyed by session_id. This gives a single source of truth
    for conversation history regardless of which query path was used.

SQLite connection:
    Using explicit sqlite3.connect(check_same_thread=False) + SqliteSaver(conn)
    instead of the context manager pattern. This is safer in FastAPI with
    hot-reloading — the context manager pattern can have its connections
    severed during Uvicorn lifecycle events, causing lock errors.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import ALL_TOOLS
from app.config import get_settings
from app.exceptions import AgentError, AgentTimeoutError

logger = logging.getLogger(__name__)

CHECKPOINT_DB_PATH = "checkpoints.db"


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

    Both agent mode and direct RAG mode use this class as the single
    source of truth for conversation history.
    """

    def __init__(self):
        self._graph = None
        # Explicit connection — safer than context manager in FastAPI/uvicorn
        self._conn = sqlite3.connect(CHECKPOINT_DB_PATH, check_same_thread=False)
        self._checkpointer = SqliteSaver(self._conn)

    def _build_graph(self):
        s = get_settings()

        # LangChain 1.x: model= not model_name=, max_tokens= not max_tokens_to_sample=
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
            checkpointer=self._checkpointer,
        )

        logger.info(
            "LangGraph agent built | model=%s | tools=%s",
            s.claude_model, [t.name for t in ALL_TOOLS]
        )
        return graph

    def get_graph(self):
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    def run(self, question: str, session_id: str = "default") -> AgentResponse:
        """
        Run the agent for a question, keyed by session_id.

        LangGraph checkpointing automatically loads prior conversation history
        for this thread_id and appends the new exchange.
        """
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
                # Corrupted checkpoint — clear and retry once
                logger.warning(
                    "Corrupted checkpoint for session '%s' — clearing and retrying",
                    session_id
                )
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
                    # Extract just the query string from args for clean output
                    args = tc.get("args", {})
                    clean_input = args.get("query", args.get("code", str(args)))
                    tools_used.append({
                        "tool": tc.get("name", "unknown"),
                        "input": clean_input,
                    })
            if hasattr(msg, "content") and "| Source:" in str(msg.content):
                for line in str(msg.content).splitlines():
                    if "| Source:" in line:
                        sources.add(line.strip())

        return AgentResponse(
            answer=answer,
            tools_used=tools_used,
            sources=sorted(sources),
        )

    async def arun(self, question: str, session_id: str = "default", **kwargs) -> AgentResponse:
        """Async wrapper — offloads to thread executor, non-blocking."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.run, question, session_id)

    def add_to_checkpoint(self, session_id: str, question: str, answer: str) -> None:
        """
        Write a direct RAG exchange into the LangGraph checkpoint store.

        Keeps the checkpoint store as the single source of truth regardless
        of which query path (agent vs direct RAG) was used.
        """
        config = {"configurable": {"thread_id": session_id}}
        try:
            graph = self.get_graph()
            graph.update_state(
                config,
                {"messages": [
                    HumanMessage(content=question),
                    AIMessage(content=answer),
                ]},
            )
            logger.debug("Wrote direct RAG exchange to checkpoint | session=%s", session_id)
        except Exception as exc:
            logger.warning("Could not write to checkpoint for session %s: %s", session_id, exc)

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Return full conversation history for a session from the checkpoint."""
        config = {"configurable": {"thread_id": session_id}}
        try:
            state = self.get_graph().get_state(config)
            messages = state.values.get("messages", [])
            history = []
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    history.append({"role": "user", "content": str(msg.content)})
                elif isinstance(msg, AIMessage):
                    history.append({"role": "assistant", "content": str(msg.content)})
            return history
        except Exception as exc:
            logger.warning("Could not retrieve history for session %s: %s", session_id, exc)
            return []

    def get_history_string(self, session_id: str) -> str:
        """Return conversation history as a formatted string for prompt injection."""
        history = self.get_history(session_id)
        if not history:
            return ""
        lines = []
        for msg in history:
            prefix = "User" if msg["role"] == "user" else "Grimoire"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)

    def clear_session(self, session_id: str) -> None:
        """Clear checkpoint state for a session using SqliteSaver.delete_thread."""
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