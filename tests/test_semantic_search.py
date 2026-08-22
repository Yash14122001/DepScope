from src.call_graph import build_call_graph
from src.embed_store import FunctionStore
from src.semantic_search import find_indirect_matches


class FakeEmbedder:
    def encode(self, texts):
        return [[float(text.count("validate")), float(text.count("email")), float(text.count("save"))] for text in texts]


def test_removes_call_graph_matches_from_semantic_results():
    files = {
        "utils.py": "def validate_email(value):\n    return '@' in value\n",
        "caller.py": "from utils import validate_email\ndef check(value):\n    return validate_email(value)\n",
        "other.py": "def save_email(value):\n    return value\n",
    }
    store = FunctionStore(FakeEmbedder())
    store.index_repo(files)
    graph = build_call_graph(files)

    results = find_indirect_matches(store, graph, "validate email", "validate_email", threshold=0.0)

    assert [result.chunk.id for result in results] == ["other.py::save_email"]