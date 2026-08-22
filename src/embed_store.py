"""Function-level code chunks and local semantic search."""

from dataclasses import dataclass
import ast
import math
from typing import Protocol

from .code_parser import FunctionInfo, parse_file


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class FunctionChunk:
    id: str
    path: str
    function_name: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class SearchResult:
    chunk: FunctionChunk
    score: float


def extract_function_chunks(files: dict[str, str]) -> list[FunctionChunk]:
    """Extract complete function source, including decorators, by AST boundaries."""
    chunks: list[FunctionChunk] = []
    for path, source in files.items():
        tree = ast.parse(source)
        lines = source.splitlines()
        result = parse_file(source)
        for function in result.functions:
            node = _find_function(tree, function)
            start_line = min([decorator.lineno for decorator in node.decorator_list] + [function.line])
            text = "\n".join(lines[start_line - 1 : function.end_line])
            chunks.append(FunctionChunk(
                id=f"{path}::{function.qualified_name}",
                path=path,
                function_name=function.qualified_name,
                start_line=start_line,
                end_line=function.end_line,
                text=text,
            ))
    return chunks


def _find_function(tree: ast.AST, function: FunctionInfo) -> ast.FunctionDef | ast.AsyncFunctionDef:
    candidates = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno == function.line]
    if not candidates:
        raise ValueError(f"Could not locate function node: {function.qualified_name}")
    return candidates[0]


class FunctionStore:
    """Search function chunks with an embedder, using cosine similarity."""

    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self._chunks: list[FunctionChunk] = []
        self._vectors: list[list[float]] = []

    def index_repo(self, files: dict[str, str]) -> int:
        self._chunks = extract_function_chunks(files)
        self._vectors = self.embedder.encode([chunk.text for chunk in self._chunks])
        return len(self._chunks)

    def search(self, query: str, top_k: int = 5, threshold: float = 0.0) -> list[SearchResult]:
        if not self._chunks:
            return []
        query_vector = self.embedder.encode([query])[0]
        results = [SearchResult(chunk, _cosine(query_vector, vector)) for chunk, vector in zip(self._chunks, self._vectors)]
        return sorted((result for result in results if result.score >= threshold), key=lambda result: result.score, reverse=True)[:top_k]


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


class SentenceTransformerEmbedder:
    """Adapter for the CPU-friendly all-MiniLM-L6-v2 model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, convert_to_numpy=False).tolist()


class ChromaFunctionStore:
    """Persistent Chroma adapter for the same function chunks."""

    def __init__(self, embedder: Embedder, persist_directory: str = ".depscope/chroma"):
        import chromadb

        self.embedder = embedder
        client = chromadb.PersistentClient(path=persist_directory)
        self.collection = client.get_or_create_collection("functions")

    def index_repo(self, files: dict[str, str]) -> int:
        chunks = extract_function_chunks(files)
        if not chunks:
            return 0
        vectors = self.embedder.encode([chunk.text for chunk in chunks])
        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            embeddings=vectors,
            documents=[chunk.text for chunk in chunks],
            metadatas=[{
                "path": chunk.path,
                "function_name": chunk.function_name,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            } for chunk in chunks],
        )
        return len(chunks)

    def search(self, query: str, top_k: int = 5, threshold: float = 0.0) -> list[SearchResult]:
        query_vector = self.embedder.encode([query])[0]
        result = self.collection.query(query_embeddings=[query_vector], n_results=top_k)
        matches: list[SearchResult] = []
        for document, metadata, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
            score = 1.0 - distance
            if score >= threshold:
                matches.append(SearchResult(FunctionChunk(
                    id=f"{metadata['path']}::{metadata['function_name']}",
                    path=metadata["path"],
                    function_name=metadata["function_name"],
                    start_line=int(metadata["start_line"]),
                    end_line=int(metadata["end_line"]),
                    text=document,
                ), score))
        return matches