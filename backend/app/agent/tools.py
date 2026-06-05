"""
LangChain tool definitions for the ReAct agent.

Each tool is a typed, documented function decorated with @tool.

CRITICAL: Tools must NEVER raise unhandled exceptions to the graph.
LangGraph checkpoints state after each node transition. If a tool raises,
the checkpoint contains an AIMessage with tool_calls but no ToolMessage,
leaving the graph in an INVALID_CHAT_HISTORY state that corrupts the
session permanently.

Every tool catches all exceptions and returns an error string instead.
This ensures LangGraph always gets a valid ToolMessage.
See: https://langchain-ai.github.io/langgraph/troubleshooting/errors/INVALID_CHAT_HISTORY/
"""

from __future__ import annotations

import logging
import sqlite3
import textwrap
from typing import Annotated

from langchain_core.tools import tool
from RestrictedPython import compile_restricted, safe_globals, safe_builtins
from RestrictedPython.PrintCollector import PrintCollector

from app.config import get_settings
from app.exceptions import CollectionNotFoundError
from app.rag.retriever import get_vector_store

logger = logging.getLogger(__name__)


# ── CRAG: Retrieval Quality Grader ────────────────────────────────────────────
#
# Implements the Corrective RAG (CRAG) pattern from Yan et al., 2024.
# After retrieval, a lightweight LLM call grades each result set as
# CORRECT / AMBIGUOUS / INCORRECT. On low confidence, the tool hints
# the ReAct agent to fall back to web_search.
#
# Score-based fast path: if the reranker's top score is clearly high
# (>0.75) or clearly low (<0.25), we skip the LLM call entirely.
# The LLM grader only fires for the ambiguous middle range.

def _grade_retrieval(query: str, results: list, top_score: float) -> str:
    """Grade retrieval quality using the CRAG pattern.

    Returns: 'CORRECT', 'AMBIGUOUS', or 'INCORRECT'.

    Fast path based on reranker confidence avoids unnecessary LLM calls:
    - top_score >= 0.75 → CORRECT (clearly relevant)
    - top_score <= 0.25 → INCORRECT (clearly irrelevant)
    - Otherwise → LLM grader decides
    """
    # Fast path: skip LLM for obvious cases
    if top_score >= 0.75:
        logger.debug("CRAG fast path: CORRECT (top_score=%.3f)", top_score)
        return "CORRECT"
    if top_score <= 0.25:
        logger.debug("CRAG fast path: INCORRECT (top_score=%.3f)", top_score)
        return "INCORRECT"

    # Ambiguous range — use LLM grader
    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage
        from pydantic import SecretStr
        from app.agent.prompts import RETRIEVAL_GRADER_PROMPT

        settings = get_settings()

        # Build a compact preview (first 200 chars of top 3 chunks)
        previews = []
        for i, r in enumerate(results[:3], 1):
            preview = r.content[:200].strip().replace("\n", " ")
            previews.append(f"Chunk {i}: {preview}")
        chunks_text = "\n".join(previews)

        prompt = RETRIEVAL_GRADER_PROMPT.format(query=query, chunks=chunks_text)

        llm = ChatAnthropic(
            model=settings.claude_model,
            api_key=SecretStr(settings.anthropic_api_key),
            max_tokens=10,
            temperature=0.0,
            timeout=10.0,
        )
        response = llm.invoke(
            [HumanMessage(content=prompt)],
            config={"tags": ["crag_grader"]},
        )
        grade = str(response.content).strip().upper()

        if grade not in ("CORRECT", "AMBIGUOUS", "INCORRECT"):
            logger.warning("CRAG grader returned unexpected value: '%s' — defaulting to AMBIGUOUS", grade)
            grade = "AMBIGUOUS"

        logger.info("CRAG grade: %s | query='%s' | top_score=%.3f", grade, query[:60], top_score)
        return grade

    except Exception as exc:
        # If the grader fails, don't block the pipeline — return results as-is
        logger.warning("CRAG grader failed: %s — defaulting to CORRECT", exc)
        return "CORRECT"


# ── Tool 1: RAG Retrieval (with CRAG grading) ────────────────────────────────

@tool
def rag_retrieval(
    query: Annotated[str, "The search query to find relevant documentation chunks"],
    k: Annotated[int, "Number of chunks to retrieve (1-10)"] = 5,
) -> str:
    """
    Search the local knowledge base using semantic similarity.
    Use this FIRST for any question that might be in the ingested docs.
    Returns relevant chunks with source citations and similarity scores.

    Includes a CRAG (Corrective RAG) retrieval grader that evaluates result
    relevance. On low confidence, the response will suggest using web_search.
    """
    k = max(1, min(k, 10))
    try:
        results = get_vector_store().similarity_search(query, k=k)
    except CollectionNotFoundError:
        return "No documents ingested yet. Call POST /ingest with documentation first."
    except Exception as exc:
        err_msg = str(exc)
        logger.error("rag_retrieval failed: %s", err_msg)

        if "rate limit" in err_msg.lower() or "429" in err_msg:
            return (
                "Error: The retrieval system is temporarily rate-limited. "
                "Please wait a moment before trying again, or rephrase your query."
            )
        return f"Error: Retrieval failed — {err_msg}"

    if not results:
        return f"No relevant documents found for: '{query}'. Consider using web_search."

    # Format the raw retrieval results
    top_score = max(r.score for r in results)
    chunks = []
    for i, result in enumerate(results, start=1):
        meta = result.document.metadata
        chunks.append(
            f"[{i}] Source: {meta.get('source', 'unknown')} | "
            f"Chunk: {meta.get('chunk_index', '?')} | "
            f"Similarity: {result.score:.3f}\n"
            f"{textwrap.indent(result.content.strip(), '    ')}"
        )
    formatted = "\n\n".join(chunks)

    # ── CRAG: Grade retrieval quality ─────────────────────────────────
    grade = _grade_retrieval(query, results, top_score)

    if grade == "INCORRECT":
        return (
            f"No relevant results found for: '{query}' "
            f"(top similarity: {top_score:.3f}, CRAG assessment: INCORRECT). "
            "The retrieved documents do not appear to answer this question. "
            "Use web_search to find relevant information."
        )
    elif grade == "AMBIGUOUS":
        return (
            f"[CRAG Assessment: AMBIGUOUS — results may be partially relevant]\n\n"
            f"{formatted}\n\n"
            "Note: Retrieval confidence is moderate. Consider supplementing "
            "with web_search for more comprehensive coverage."
        )
    else:
        # CORRECT — return results as normal
        return formatted


# ── Tool 2: Web Search ────────────────────────────────────────────────────────

@tool
def web_search(
    query: Annotated[str, "The search query for current information from the web"],
    max_results: Annotated[int, "Number of search results to return (1-5)"] = 3,
) -> str:
    """
    Search the web using Tavily for current information, Stack Overflow answers,
    GitHub issues, or anything not in the local knowledge base.
    Use when local docs don't have the answer or the question needs current info.
    """
    max_results = max(1, min(max_results, 5))
    settings = get_settings()
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
            include_raw_content=False,
        )
    except Exception as exc:
        err_msg = str(exc)
        logger.error("Tavily search failed: %s", err_msg)

        if "rate limit" in err_msg.lower() or "429" in err_msg:
            return "Error: Web search is temporarily rate-limited. Please wait a moment."
        return f"Error: Web search failed — {err_msg}"

    results = response.get("results", [])
    if not results:
        return f"Web search returned no results for: '{query}'"

    lines = []
    if answer := response.get("answer"):
        lines.append(f"Web Answer: {answer}\n")
    for i, r in enumerate(results, start=1):
        lines.append(
            f"[{i}] {r.get('title', 'No title')}\n"
            f"    URL: {r.get('url', '')}\n"
            f"    {r.get('content', '')[:400]}"
        )
    return "\n\n".join(lines)


# ── Tool 3: SQLite Database Query ─────────────────────────────────────────────

@tool
def database_query(
    natural_language_query: Annotated[str, "What data to retrieve in plain English"],
    sql_query: Annotated[str, "The SQL SELECT statement — no writes allowed"],
) -> str:
    """
    Execute a SQL SELECT query against the local SQLite knowledge database.
    Use for structured data: API endpoint lists, config tables, changelogs.
    Only SELECT statements are permitted — no INSERT, UPDATE, DELETE, or DROP.
    """
    if not sql_query.strip().upper().startswith("SELECT"):
        return f"Error: Only SELECT statements permitted. Received: '{sql_query[:60]}'"

    db_path = get_settings().sqlite_db_path
    if not db_path.exists():
        return "Database not found. No structured data has been loaded yet."

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql_query)
            rows = cursor.fetchmany(50)
            if not rows:
                return f"Query returned no rows.\nSQL: {sql_query}"
            columns = [desc[0] for desc in cursor.description]
            header = " | ".join(columns)
            row_lines = [" | ".join(str(row[col]) for col in columns) for row in rows]
            return (
                f"Query Results ({len(rows)} rows):\n{header}\n"
                f"{'-' * len(header)}\n" + "\n".join(row_lines)
            )
    except sqlite3.Error as exc:
        logger.error("SQLite error: %s | Query: %s", exc, sql_query)
        return f"Error: SQL query failed — {exc}"


# ── Tool 4: Python Code Executor ──────────────────────────────────────────────

@tool
def code_executor(
    code: Annotated[str, "Python code to execute for calculations or analysis"],
    description: Annotated[str, "One-sentence description of what this code does"],
) -> str:
    """
    Execute Python code in a sandboxed environment.
    Available: math, json, re, statistics, collections, itertools.
    NOT available: file I/O, network requests, os, sys imports.
    Use for calculations, sorting, data transformations, algorithm tracing.
    """
    import json
    import math
    import re
    import statistics
    from collections import Counter, defaultdict, deque
    from itertools import combinations, permutations, product

    allowed_globals = {
        **safe_globals,
        "__builtins__": {**safe_builtins},
        "_print_": PrintCollector,
        "_getiter_": iter,
        "_getattr_": getattr,
        "_write_": lambda x: x,
        "math": math,
        "json": json,
        "re": re,
        "statistics": statistics,
        "Counter": Counter,
        "defaultdict": defaultdict,
        "deque": deque,
        "combinations": combinations,
        "permutations": permutations,
        "product": product,
        "range": range, "len": len, "str": str, "int": int, "float": float,
        "list": list, "dict": dict, "set": set, "tuple": tuple,
        "abs": abs, "max": max, "min": min, "sum": sum, "round": round,
        "sorted": sorted, "enumerate": enumerate, "zip": zip, "map": map,
        "filter": filter, "bool": bool, "isinstance": isinstance,
        "type": type, "repr": repr, "hash": hash, "any": any, "all": all,
    }

    local_vars: dict = {}
    try:
        byte_code = compile_restricted(code, "<string>", "exec")
        exec(byte_code, allowed_globals, local_vars)  # noqa: S102
    except SyntaxError as exc:
        return f"Syntax error: {exc}"
    except Exception as exc:
        return f"Runtime error: {type(exc).__name__}: {exc}"

    collector = local_vars.get("_print")
    output = "".join(collector.txt).strip() if collector else ""
    return output if output else "Code executed (no output produced)."


# ── Tool registry ─────────────────────────────────────────────────────────────

def _build_tools() -> list:
    """Build tool list based on available API keys."""
    settings = get_settings()
    tools = [rag_retrieval, database_query, code_executor]
    if settings.tavily_api_key:
        tools.insert(1, web_search)
    else:
        logger.info("Web search disabled — set TAVILY_API_KEY to enable")
    return tools


ALL_TOOLS = _build_tools()