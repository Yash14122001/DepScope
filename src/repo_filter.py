"""Rules for selecting safe, readable repository files."""

from pathlib import PurePosixPath
from typing import Any


EXCLUDED_DIRECTORIES = {".git", "__pycache__", "build", "dist", "migrations", "vendor", "venv"}
SUPPORTED_TEXT_EXTENSIONS = {
    ".bat", ".c", ".cfg", ".conf", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html", ".ini",
    ".java", ".js", ".jsx", ".json", ".md", ".ps1", ".py", ".rs", ".sh", ".sql", ".toml", ".ts", ".tsx",
    ".txt", ".xml", ".yaml", ".yml",
}
EXCLUDED_FILENAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
MAX_FILE_BYTES = 200_000


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


def is_relevant_text_file(path: str, size: int | None = None) -> bool:
    """Return whether a path looks like safe, readable source or text."""
    normalized = path.replace("\\", "/").strip("/")
    parsed = PurePosixPath(normalized)
    if not parsed.name or parsed.name in EXCLUDED_FILENAMES or any(part in EXCLUDED_DIRECTORIES for part in parsed.parts):
        return False
    if parsed.name.endswith((".pem", ".key", ".p12", ".pfx")) or parsed.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
        return False
    return size is None or size <= MAX_FILE_BYTES


def filter_repository_files(entries: list[dict[str, Any]], max_files: int = 2500) -> list[str]:
    """Select supported text files while skipping binaries, secrets, and oversized files."""
    paths = sorted(
        str(entry["path"])
        for entry in entries
        if entry.get("type") == "blob" and is_relevant_text_file(str(entry.get("path", "")), entry.get("size"))
    )
    if len(paths) > max_files:
        raise ValueError(f"Repository has {len(paths)} readable files; limit is {max_files}.")
    return paths