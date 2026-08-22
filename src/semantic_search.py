"""Semantic impact search layered on top of the function store."""

from .call_graph import CallGraph
from .embed_store import FunctionStore, SearchResult


def find_indirect_matches(
    store: FunctionStore,
    graph: CallGraph,
    query: str,
    direct_function: str,
    top_k: int = 5,
    threshold: float = 0.35,
) -> list[SearchResult]:
    """Return semantically related functions not already found by the call graph."""
    direct_edges = graph.find_callers(direct_function)
    direct_ids = {edge.caller for edge in direct_edges}
    direct_ids.update(edge.callee for edge in direct_edges)
    direct_ids.add(direct_function)
    results = store.search(query, top_k=top_k + len(direct_ids), threshold=threshold)
    return [result for result in results if result.chunk.id not in direct_ids][:top_k]