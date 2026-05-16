"""
ReAct agent orchestrator.

Wires Claude Sonnet 4 + tools + prompts into a LangChain AgentExecutor.
LangSmith tracing activates automatically via LANGCHAIN_TRACING_V2 env var.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import ALL_TOOLS
from app.config import get_settings
from app.exceptions import AgentError, AgentTimeoutError

logger = logging.getLogger(__name__)

REACT_TEMPLATE = """{system}

You have access to the following tools:

{tools}

Use the following format EXACTLY:

Question: the input question you must answer
Thought: think about what information you need and which tool to use
Action: the action to take, must be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (Thought/Action/Action Input/Observation can repeat N times)
Thought: I now have enough information to answer
Final Answer: the comprehensive, well-cited answer to the original question

Begin!

{chat_history}
Question: {input}
Thought: {agent_scratchpad}"""


@dataclass
class AgentResponse:
    answer: str
    tools_used: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    intermediate_steps: list[tuple[Any, str]] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)


class GrimoireAgent:
    """Singleton AgentExecutor. Built lazily on first use."""

    _executor: AgentExecutor | None = None

    def _build_executor(self) -> AgentExecutor:
        s = get_settings()
        llm = ChatAnthropic(
            model=s.claude_model, api_key=s.anthropic_api_key,
            max_tokens=s.claude_max_tokens, temperature=s.claude_temperature,
        )
        prompt = PromptTemplate(
            input_variables=["tools", "tool_names", "input", "agent_scratchpad", "chat_history"],
            template=REACT_TEMPLATE,
            partial_variables={"system": SYSTEM_PROMPT},
        ).partial(chat_history="")  # safe default — avoids KeyError on first call

        executor = AgentExecutor(
            agent=create_react_agent(llm=llm, tools=ALL_TOOLS, prompt=prompt),
            tools=ALL_TOOLS,
            verbose=True,
            max_iterations=s.agent_max_iterations,
            max_execution_time=s.agent_max_execution_time,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
        )
        logger.info("Agent built | model=%s | tools=%s", s.claude_model, [t.name for t in ALL_TOOLS])
        return executor

    def get_executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = self._build_executor()
        return self._executor

    def run(self, question: str, chat_history: str = "") -> AgentResponse:
        logger.info("Running agent: '%s'", question[:100])
        try:
            result = self.get_executor().invoke({"input": question, "chat_history": chat_history})
        except TimeoutError as exc:
            raise AgentTimeoutError() from exc
        except Exception as exc:
            logger.error("Agent failed: %s", exc, exc_info=True)
            raise AgentError(f"Agent failed: {exc}") from exc

        answer = result.get("output", "")
        steps = result.get("intermediate_steps", [])
        tools_used, sources = [], set()

        for action, observation in steps:
            tools_used.append({
                "tool": getattr(action, "tool", "unknown"),
                "input": getattr(action, "tool_input", ""),
                "output_preview": str(observation)[:300],
            })
            if "Source:" in str(observation):
                for line in str(observation).splitlines():
                    if "Source:" in line:
                        sources.add(line.strip())

        return AgentResponse(
            answer=answer, tools_used=tools_used,
            sources=sorted(sources), intermediate_steps=steps,
        )

    async def arun(self, question: str, chat_history: str = "") -> AgentResponse:
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, self.run, question, chat_history)


_agent: GrimoireAgent | None = None

def get_agent() -> GrimoireAgent:
    global _agent
    if _agent is None:
        _agent = GrimoireAgent()
    return _agent
