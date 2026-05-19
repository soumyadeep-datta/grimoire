"""
LangGraph ReAct agent orchestrator.

Uses langgraph.prebuilt.create_react_agent with SqliteSaver checkpointing
for durable, per-session conversation state.

LangGraph 1.2 replaces the deprecated LangChain AgentExecutor pattern.
SqliteSaver provides thread-safe persistent checkpointing keyed by thread_id.

Note: create_react_agent from langgraph.prebuilt is deprecated in favour of
langchain.agents.create_agent but remains fully functional in LangGraph 1.2.
"""

from __future__ import annotations

import logging
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
    """

    def __init__(self):
        self._graph = None
        # SqliteSaver.from_conn_string is a context manager in LangGraph 0.2+
        # We use __enter__ to get the actual saver object
        self._cm = SqliteSaver.from_conn_string(CHECKPOINT_DB_PATH)
        self._checkpointer = self._cm.__enter__()

    def _build_graph(self):
        s = get_settings()

        # LangChain 1.x uses model= not model_name=, max_tokens= not max_tokens_to_sample=
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

        LangGraph uses thread_id in config to scope checkpoints —
        each session_id gets its own independent conversation history.
        """
        graph = self.get_graph()
        config = {"configurable": {"thread_id": session_id}}

        logger.info("Running agent | session=%s | question='%s'", session_id, question[:100])

        try:
            result = graph.invoke(
                {"messages": [HumanMessage(content=question)]},
                config=config,
            )
        except TimeoutError as exc:
            raise AgentTimeoutError() from exc
        except Exception as exc:
            logger.error("Agent failed: %s", exc, exc_info=True)
            raise AgentError(f"Agent failed: {exc}") from exc

        # Extract answer from last AI message
        messages = result.get("messages", [])
        answer = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                answer = str(msg.content)
                break

        # Extract tool calls and sources
        tools_used: list[dict[str, Any]] = []
        sources: set[str] = set()

        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tools_used.append({
                        "tool": tc.get("name", "unknown"),
                        "input": str(tc.get("args", "")),
                        "output_preview": "",
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

    async def arun(self, question: str, session_id: str = "default") -> AgentResponse:
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, self.run, question, session_id
        )

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Return conversation history for a session from the checkpoint."""
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

    def clear_session(self, session_id: str) -> None:
        """Clear checkpoint state for a session."""
        logger.info("Session clear requested for '%s'", session_id)

    def __del__(self):
        """Clean up the SqliteSaver context manager on shutdown."""
        try:
            self._cm.__exit__(None, None, None)
        except Exception:
            pass


_agent: GrimoireAgent | None = None


def get_agent() -> GrimoireAgent:
    global _agent
    if _agent is None:
        _agent = GrimoireAgent()
    return _agent