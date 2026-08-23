from ui.app import evidence_for_edge
from src.call_graph import CallEdge


def test_evidence_for_edge_returns_numbered_source_line():
    edge = CallEdge("main.py::run", "utils.py::helper", 2)

    assert evidence_for_edge(edge, {"main.py": "def run():\n    helper()\n"}) == "helper()"