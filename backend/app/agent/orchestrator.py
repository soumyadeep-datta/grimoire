"""
ReAct agent orchestrator.

Uses LangChain's create_react_agent with Claude Sonnet 4 as the backbone.
LangSmith tracing is enabled transparently via environment variables.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from pydantic import SecretStr

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import ALL_TOOLS
from app.config import get_settings
from app.exceptions import AgentError, AgentTimeoutError

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Structured response returned by the agent to the API layer."""
    answer: str
    tools_used: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    intermediate_steps: list[tuple[Any, str]] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)


REACT_TEMPLATE = """{system}

You have access to the following tools:

{tools}

Use the following format EXACTLY — do not deviate:

Question: the input question you must answer
Thought: I need to think about what information is required
Action: the action to take, must be exactly one of [{tool_names}]
Action Input: the input to the action as a plain string
Observation: the result of the action
Thought: I now have the information I need to answer
Final Answer: the comprehensive answer to the original question with citations

IMPORTANT RULES:
- After 1-2 successful tool calls with good results, write Final Answer immediately
- Never repeat the same tool call with the same input
- Action Input must be a plain string only — no JSON formatting, no prefixes
- If the Observation contains relevant information, use it to write Final Answer right away

Begin!

{chat_history}
Question: {input}
Thought: {agent_scratchpad}"""


class GrimoireAgent:
    """Singleton wrapper around the LangChain ReAct AgentExecutor."""

    _executor: AgentExecutor | None = None

    def _build_executor(self) -> AgentExecutor:
        s = get_settings()

        llm = ChatAnthropic(
            model_name=s.claude_model,
            api_key=SecretStr(s.anthropic_api_key),
            max_tokens_to_sample=s.claude_max_tokens,
            temperature=s.claude_temperature,
            timeout=60.0,
            stop=None,
        )

        prompt = PromptTemplate(
            input_variables=["tools", "tool_names", "input", "agent_scratchpad", "chat_history"],
            template=REACT_TEMPLATE,
            partial_variables={"system": SYSTEM_PROMPT},
        ).partial(chat_history="")

        agent = create_react_agent(llm=llm, tools=ALL_TOOLS, prompt=prompt)

        executor = AgentExecutor(
            agent=agent,
            tools=ALL_TOOLS,
            verbose=True,
            max_iterations=5,
            max_execution_time=s.agent_max_execution_time,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
        )

        logger.info(
            "Agent built | model=%s | tools=%s",
            s.claude_model, [t.name for t in ALL_TOOLS]
        )
        return executor

    def get_executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = self._build_executor()
        return self._executor

    def run(self, question: str, chat_history: str = "") -> AgentResponse:
        executor = self.get_executor()
        logger.info("Running agent: '%s'", question[:100])

        try:
            result: dict[str, Any] = executor.invoke(
                {"input": question, "chat_history": chat_history}
            )
        except TimeoutError as exc:
            raise AgentTimeoutError() from exc
        except Exception as exc:
            logger.error("Agent failed: %s", exc, exc_info=True)
            raise AgentError(f"Agent failed: {exc}") from exc

        answer: str = result.get("output", "")
        intermediate_steps: list[tuple[Any, str]] = result.get("intermediate_steps", [])

        tools_used: list[dict[str, Any]] = []
        sources: set[str] = set()

        for action, observation in intermediate_steps:
            tools_used.append({
                "tool": getattr(action, "tool", "unknown"),
                "input": getattr(action, "tool_input", ""),
                "output_preview": str(observation)[:300],
            })
            if "Source:" in str(observation):
                for line in str(observation).splitlines():
                    if "| Source:" in line:
                        sources.add(line.strip())

        return AgentResponse(
            answer=answer,
            tools_used=tools_used,
            sources=sorted(sources),
            intermediate_steps=intermediate_steps,
        )

    async def arun(self, question: str, chat_history: str = "") -> AgentResponse:
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, self.run, question, chat_history
        )


_agent: GrimoireAgent | None = None


def get_agent() -> GrimoireAgent:
    global _agent
    if _agent is None:
        _agent = GrimoireAgent()
    return _agent