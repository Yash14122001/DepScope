"""Gemini tools and a bounded manual function-calling loop."""

from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable

from .call_graph import CallGraph
from .embed_store import FunctionStore


@dataclass
class AnalysisContext:
    graph: CallGraph
    store: FunctionStore | None = None
    files: dict[str, str] = field(default_factory=dict)


def make_tools(context: AnalysisContext) -> list[Callable[..., Any]]:
    """Create Gemini-compatible tools bound to one in-memory repository."""
    def get_callers(function_name: str) -> list[dict[str, Any]]:
        """Find functions that directly call the target function."""
        return [_edge_dict(edge) for edge in context.graph.find_callers(function_name)]

    def get_callees(function_name: str) -> list[dict[str, Any]]:
        """Find functions directly called by the target function."""
        return [_edge_dict(edge) for edge in context.graph.find_callees(function_name)]

    def semantic_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Find functions that are conceptually related to a query."""
        if context.store is None:
            return []
        return [{
            "path": result.chunk.path,
            "function": result.chunk.function_name,
            "start_line": result.chunk.start_line,
            "end_line": result.chunk.end_line,
            "score": round(result.score, 4),
        } for result in context.store.search(query, top_k=top_k)]

    def read_file(path: str, start_line: int = 1, end_line: int = 40) -> str:
        """Read a bounded line range from an in-memory repository file."""
        if path not in context.files:
            return f"File not found: {path}"
        lines = context.files[path].splitlines()
        return "\n".join(f"{number}: {lines[number - 1]}" for number in range(max(1, start_line), min(len(lines), end_line) + 1))

    return [get_callers, get_callees, semantic_search, read_file]


def _edge_dict(edge: Any) -> dict[str, Any]:
    return {"caller": edge.caller, "callee": edge.callee, "line": edge.line, "dynamic": edge.dynamic}


@dataclass(frozen=True)
class AgentRun:
    answer: str
    tool_calls: int
    elapsed_seconds: float


def run_agent(
    client: Any,
    prompt: str,
    tools: list[Callable[..., Any]],
    model: str = "gemini-2.5-flash",
    max_steps: int = 6,
) -> AgentRun:
    """Run Gemini's manual tool-calling loop with a hard step limit."""
    from google.genai import types

    started = time.perf_counter()
    contents: list[Any] = [prompt]
    config = types.GenerateContentConfig(tools=tools, automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    tool_calls = 0
    for _ in range(max_steps):
        response = client.models.generate_content(model=model, contents=contents, config=config)
        function_calls = response.function_calls or []
        if not function_calls:
            return AgentRun(response.text or "", tool_calls, time.perf_counter() - started)
        contents.append(response.candidates[0].content)
        function_responses = []
        for function_call in function_calls:
            tool = next((candidate for candidate in tools if candidate.__name__ == function_call.name), None)
            if tool is None:
                result: Any = {"error": f"Unknown tool: {function_call.name}"}
            else:
                result = tool(**dict(function_call.args or {}))
            function_responses.append(types.Part.from_function_response(name=function_call.name, response={"result": result}))
            tool_calls += 1
        contents.append(types.Content(role="tool", parts=function_responses))
    return AgentRun("The analysis stopped after reaching the tool-call step limit.", tool_calls, time.perf_counter() - started)