from src.embed_store import FunctionStore, extract_function_chunks


FILES = {
    "validation.py": "def validate_email(value):\n    \"\"\"Validate an email address.\"\"\"\n    return '@' in value\n",
    "service.py": "class Service:\n    @staticmethod\n    def save(value):\n        return value\n",
}


class FakeEmbedder:
    def encode(self, texts):
        return [[float(len(text)), float(text.count("email")), float(text.count("save"))] for text in texts]


def test_extracts_function_boundaries_and_decorators():
    chunks = extract_function_chunks(FILES)

    assert [(chunk.id, chunk.start_line, chunk.end_line) for chunk in chunks] == [
        ("validation.py::validate_email", 1, 3),
        ("service.py::Service.save", 2, 4),
    ]
    assert "@staticmethod" in chunks[1].text


def test_indexes_and_returns_ranked_results():
    store = FunctionStore(FakeEmbedder())

    assert store.index_repo(FILES) == 2
    results = store.search("email", top_k=1)

    assert len(results) == 1
    assert results[0].chunk.function_name == "validate_email"