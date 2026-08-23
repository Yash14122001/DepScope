import pytest

from src.repo_filter import filter_python_files, filter_repository_files


ENTRIES = [
    {"path": "src/app.py", "type": "blob"},
    {"path": "tests/test_app.py", "type": "blob"},
    {"path": "src/generated_pb2.py", "type": "blob"},
    {"path": "src/__pycache__/app.py", "type": "blob"},
    {"path": "README.md", "type": "blob"},
]


def test_filters_to_non_generated_python_source():
    assert filter_python_files(ENTRIES) == ["src/app.py"]
    assert filter_python_files(ENTRIES, include_tests=True) == ["src/app.py", "tests/test_app.py"]


def test_enforces_file_limit():
    with pytest.raises(ValueError, match="limit is 0"):
        filter_python_files([{"path": "app.py", "type": "blob"}], max_files=0)


def test_repository_filter_includes_supported_text_and_excludes_secrets():
    entries = [
        {"path": "README.md", "type": "blob"},
        {"path": "frontend/app.tsx", "type": "blob"},
        {"path": "config.yaml", "type": "blob"},
        {"path": ".env", "type": "blob"},
        {"path": "image.png", "type": "blob"},
        {"path": "large.json", "type": "blob", "size": 200001},
    ]

    assert filter_repository_files(entries) == ["README.md", "config.yaml", "frontend/app.tsx"]