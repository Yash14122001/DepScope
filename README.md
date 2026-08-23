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

## Weeks 7–8: Gemini Agent

`src/agent.py` binds four tools to one repository context: `get_callers`, `get_callees`, `semantic_search`, and `read_file`. The tools return ordinary dictionaries and line-numbered text so Gemini can inspect evidence rather than receiving opaque Python objects.

`run_agent()` uses Gemini manual function calling. It sends the model response back into the conversation, executes requested tools locally, returns their results, and repeats until Gemini answers or six steps have been reached. The step limit protects cost and prevents an accidental runaway loop. Each run reports answer text, tool-call count, and elapsed time.

To use the SDK, add a replacement key to your local `.env`:

```env
GEMINI_API_KEY=your_replacement_key
```

Then create a Gemini client with `genai.Client(api_key=...)` and pass it to `run_agent()`. The tests do not call Gemini and do not require a live API key.

Run the complete test suite with:

```powershell
py -m pytest -q
```

## Weeks 9–10: Evaluation

`eval/eval_dataset.json` defines the evaluation schema: each case stores in-memory source files, a target function, and hand-labeled expected direct callers and related functions. The included two cases are small development fixtures for validating the harness; they are not representative quality results. The planned next improvement is replacing or expanding them with 20–25 cases from three real repositories.

`eval/run_eval.py` scores predictions using set-based precision and recall. It evaluates the deterministic graph baseline first, which gives us a stable reference before measuring Gemini output. Run it with:

```powershell
py eval/run_eval.py
```

The command writes the recorded baseline to `eval/eval_results.md`. A prediction is a caller node such as `service.py::process`; precision measures how many predicted callers are correct, while recall measures how many expected callers were found. Keep the dataset fixed while comparing implementation changes.

## Weeks 11–12: Browser App and Design Notes

The product frontend lives in `web/` and is served by the FastAPI application in `src/main.py`. Start it with:

```powershell
py -m pip install -r requirements.txt
py -m uvicorn src.main:app --reload
```

Open `http://localhost:8000`. Enter a public GitHub repository, wait for the in-memory analysis to finish, and then ask general questions in the repository conversation. Examples include `How is authentication handled?`, `Where is the database configured?`, `Which files define the API routes?`, and `What calls the request function?`

The backend creates a repository session containing safe readable files and a Python call graph. It analyzes common code, documentation, configuration, SQL, and script files as text, while exact AST callers/callees remain Python-only. Gemini receives tools for listing files, searching source text, reading bounded line ranges, finding callers/callees, and semantic search when an embedding store is provided. The answer should cite paths and lines and distinguish evidence from inference. The frontend is plain HTML, CSS, and JavaScript so it stays lightweight and does not require Streamlit.

Repository files are limited to 2,500 entries by default and individual files are limited to 200 KB. Binary-looking content, secrets such as `.env` and private-key files, generated/vendor directories, and unsupported extensions are skipped before analysis.

The former `ui/app.py` Streamlit screen is retained as an experimental legacy view, but it is no longer the primary interface or required dependency.

The architecture is deliberately hybrid:

```text
GitHub URL -> tree filter -> in-memory files -> AST parser -> call graph -> direct evidence
												   \-> function chunks -> embeddings -> semantic matches
												   \-> Gemini tools -> bounded investigation
```

The graph is preferred for direct impact because imports and call edges are inspectable and line-citable. Semantic search is a second signal for behaviorally related code that static calls miss. Functions are the embedding unit because a complete function preserves local intent better than arbitrary character windows. Python is the MVP language because the standard AST module is available without a compiler service.

Known limitations: dynamic dispatch, monkey-patching, decorators with hidden behavior, dependency injection, and ambiguous duplicate function names are not fully resolvable statically. Large repositories can exceed GitHub tree/API limits, and the current UI fetches selected file contents sequentially. Production improvements would include commit-SHA caching, asynchronous fetches, repository indexing jobs, stronger symbol resolution, and a persistent multi-tenant vector store.

The current evaluation result is a two-case development fixture baseline. Replace it with the planned 20–25 hand-verified cases before using precision or recall in a resume claim. Keep API keys in `.env`; `.gitignore` excludes that file and generated `.depscope/` data.