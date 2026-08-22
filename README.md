# DepScope

DepScope predicts which Python code may be affected when a function changes. The first two weeks build the GitHub ingestion layer: it reads a public repository through the GitHub REST API, keeps responses in memory, and never clones or writes repository files to disk.

## Setup

```powershell
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`GITHUB_TOKEN` is optional for public repositories. A token gives GitHub API clients a higher rate limit. Do not commit a real token to `.env`.

## Try It

```powershell
py fetch_repo.py https://github.com/psf/requests
py fetch_repo.py https://github.com/psf/requests --include-tests
```

The CLI prints the branch used, the total tree entries, the filtered Python file count, and the first 500 characters of one file. File filtering excludes tests by default, generated protobuf files, common build/vendor directories, and Python cache directories. The default limit is 2,500 relevant files.

## Test It

```powershell
py -m pytest -q
```

The tests mock HTTP responses, so they are deterministic and do not spend GitHub API requests. The live CLI check is separate from the unit suite.

## What We Learned in Weeks 1–2

- The GitHub tree endpoint gives paths and metadata; file contents are fetched only when needed.
- Caching both trees and file contents prevents duplicate requests during one analysis session.
- API failures are translated into clear application errors instead of leaking HTTP details everywhere.
- Filtering is isolated as pure Python logic, making its rules easy to test and change.

## Weeks 3–4: AST Call Graph

`src/code_parser.py` parses one in-memory Python file into structured function, call, and import records. Each function includes its qualified name, start/end lines, and docstring. Each call includes its caller, spelling, and line number.

`src/call_graph.py` combines those records across files. The current static resolver supports same-file functions, `from module import function`, module aliases such as `import package.api as api`, and basic `self.method()` calls. Use `find_callers("function_name")` for blast-radius edges and `find_callees("function_name")` for outgoing edges.

Dynamic calls are kept as `unknown/dynamic` edges with `dynamic=True`. This is intentional: Python features such as `getattr`, monkey-patching, and dependency injection cannot be resolved reliably from syntax alone. The graph reports that uncertainty instead of inventing a dependency.

Run the complete test suite with:

```powershell
py -m pytest -q
```

## Weeks 5–6: Semantic Search

`src/embed_store.py` extracts one searchable chunk per function, preserving the path, qualified function name, source lines, decorators, and complete function body. `FunctionStore` accepts any compatible embedder and ranks results with cosine similarity. `SentenceTransformerEmbedder` is the production adapter for `all-MiniLM-L6-v2`; its first use downloads the model, so tests use a small fake embedder instead.

`ChromaFunctionStore` provides the planned persistent local Chroma backend. It stores embeddings, source text, and line metadata under `.depscope/chroma` when explicitly used. This generated directory should not be committed.

`src/semantic_search.py` exposes `find_indirect_matches()`. It searches by meaning and removes functions already connected by the call graph, leaving a separate indirect signal. The `threshold` argument prevents low-similarity matches from being presented as meaningful evidence; it should be calibrated during the evaluation weeks rather than treated as universally correct.

Run the complete test suite with:

```powershell
py -m pytest -q
```

Next, Weeks 7–8 can expose graph, semantic search, and file-reading operations as Gemini function-calling tools.