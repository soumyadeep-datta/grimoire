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


# ── Tool 1: RAG Retrieval ─────────────────────────────────────────────────────

@tool
def rag_retrieval(
    query: Annotated[str, "The search query to find relevant documentation chunks"],
    k: Annotated[int, "Number of chunks to retrieve (1-10)"] = 5,
) -> str:
    """
    Search the local knowledge base using semantic similarity.
    Use this FIRST for any question that might be in the ingested docs.
    Returns relevant chunks with source citations and similarity scores.
    """
    k = max(1, min(k, 10))
    try:
        results = get_vector_store().similarity_search(query, k=k)
    except CollectionNotFoundError:
        return "No documents ingested yet. Call POST /ingest with documentation first."
    except Exception as exc:
        # NEVER raise to the graph — return error string so LangGraph
        # creates a valid ToolMessage and the checkpoint stays clean.
        err_msg = str(exc)
        logger.error("rag_retrieval failed: %s", err_msg)

        if "rate limit" in err_msg.lower() or "429" in err_msg:
            return (
                "Error: The retrieval system is temporarily rate-limited. "
                "Please wait a moment before trying again, or rephrase your query."
            )
        return f"Error: Retrieval failed — {err_msg}"

    if not results:
        return f"No relevant documents found for: '{query}'"

    chunks = []
    for i, result in enumerate(results, start=1):
        meta = result.document.metadata
        chunks.append(
            f"[{i}] Source: {meta.get('source', 'unknown')} | "
            f"Chunk: {meta.get('chunk_index', '?')} | "
            f"Similarity: {result.score:.3f}\n"
            f"{textwrap.indent(result.content.strip(), '    ')}"
        )
    return "\n\n".join(chunks)


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
#
# How RestrictedPython's print works:
#   - compile_restricted rewrites print(x) → _print_(x)
#   - _print_ must be the PrintCollector CLASS in globals (not an instance)
#   - After exec(), local_vars["_print"] holds the instance
#   - Output lives in that instance's .txt list — join with ''.join(pc.txt)

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