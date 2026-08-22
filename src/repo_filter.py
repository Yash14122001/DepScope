"""Rules for selecting Python source files worth analyzing."""

from pathlib import PurePosixPath
from typing import Any


EXCLUDED_DIRECTORIES = {".git", "__pycache__", "build", "dist", "migrations", "vendor", "venv"}


def is_relevant_python_file(path: str, include_tests: bool = False) -> bool:
    normalized = path.replace("\\", "/").strip("/")
    parsed = PurePosixPath(normalized)
    if parsed.suffix != ".py" or any(part in EXCLUDED_DIRECTORIES for part in parsed.parts):
        return False
    if parsed.name.endswith("_pb2.py"):
        return False
    if not include_tests and ("tests" in parsed.parts or parsed.name.startswith("test_")):
        return False
    return True


def filter_python_files(entries: list[dict[str, Any]], include_tests: bool = False, max_files: int = 2500) -> list[str]:
    paths = sorted(
        str(entry["path"])
        for entry in entries
        if entry.get("type") == "blob" and is_relevant_python_file(str(entry.get("path", "")), include_tests)
    )
    if len(paths) > max_files:
        raise ValueError(f"Repository has {len(paths)} relevant Python files; limit is {max_files}.")
    return paths