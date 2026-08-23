# DepScope — 12-Week Build Plan

**The pitch:** Give it a public GitHub repo URL and a function you're planning to change. It tells you what else in the codebase might break — with exact file/line evidence and a confidence level — without ever downloading the repo to your machine.

**Why it's worth building:** It combines a reliable rule-based map ("who calls who") with AI-based semantic search ("what's conceptually related"), wrapped in an agent that reasons in steps rather than answering in one shot. That hybrid design + a real evaluation suite is what separates this from a tutorial-level "chat with your repo" demo.

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Backend | Python + FastAPI | Standard, lightweight, easy to reason about |
| Repo access | GitHub REST API (`requests`) | No cloning — fetch file tree + individual files on demand |
| Call graph | Python's built-in `ast` module | Exact, rule-based, no AI needed, fast on CPU |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2` or `bge-small-en-v1.5`) | Small, CPU-friendly, good enough quality |
| Vector store | Chroma (local) | Zero-infra, persists locally, easy to swap later |
| Agent reasoning | Gemini API via `google-genai` SDK (function calling) | Only the "big model" step — runs on Google's servers, not yours. Free tier is generous, good for a portfolio project |
| UI | Streamlit | Fastest way to get a usable, demoable interface |
| Testing | `pytest` | Standard unit testing for the non-AI parts |
| Eval | Custom Python script + hand-labeled JSON | You need ground truth you trust, not an off-the-shelf metric |

---

## Proposed Repo Structure

```
depscope/
├── src/
│   ├── github_client.py     # fetch file tree + file contents, no clone
│   ├── code_parser.py       # AST parsing, per-file function/call extraction
│   ├── call_graph.py        # cross-file graph building + queries
│   ├── embed_store.py       # chunking, embeddings, Chroma indexing
│   ├── semantic_search.py   # indirect/conceptual impact search
│   ├── agent.py             # tool definitions + multi-step reasoning loop
│   └── main.py               # FastAPI app tying it all together
├── ui/
│   └── app.py                # Streamlit interface
├── eval/
│   ├── eval_dataset.json     # your hand-labeled ground truth
│   ├── run_eval.py           # runs agent against dataset, scores it
│   └── eval_results.md       # your recorded metrics, before/after
├── tests/
│   └── test_*.py              # pytest unit tests for non-AI components
├── README.md
└── requirements.txt
```

---

## Week 1 — GitHub Fetching, Part 1 (no cloning)

**Goal:** Be able to pull any public repo's file list and individual file contents purely via API calls, nothing written to disk.

- Day 1–2: Set up the project skeleton, virtual environment, install `fastapi`, `uvicorn`, `requests`, `python-dotenv`, and `google-genai` (Google's current official SDK — note: the older `google-generativeai` package is deprecated, don't follow tutorials that use it). Create a free GitHub personal access token (raises your rate limit from 60/hr to 5,000/hr — this is *your* token, not the repo owner's) and a free Gemini API key from Google AI Studio.
- Day 3–4: Build `github_client.py` with two core functions:
  - `get_repo_tree(owner, repo, branch)` → calls `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1`, returns the full file list.
  - `get_file_content(owner, repo, branch, path)` → calls the raw content URL, returns the file's text.
- Day 5: Add error handling — repo not found (404), rate limit hit (403), private repo (can't access without owner permission, handle gracefully), branch not found (try `main`, fall back to `master`).
- Day 6–7: Add a simple in-memory cache (a dict keyed by `owner/repo/branch`) so re-querying the same repo in a session doesn't refetch everything. Manually test against 2–3 real public repos in a Python REPL.

**Definition of done:** You can run `get_repo_tree("psf", "requests", "main")` and get back a real file list, and `get_file_content(...)` for any path in it, with zero files written to your disk.

---

## Week 2 — GitHub Fetching, Part 2 (filtering + size limits)

**Goal:** Go from "every file in the repo" to "just the Python files worth analyzing."

- Filter the file tree to `.py` files only for the MVP. Exclude `tests/`, `test_*.py` (or keep them separately — decide and document why), `__pycache__`, `migrations/`, vendored/generated code (e.g. `_pb2.py`, `dist/`, `build/`).
- Add a size cap: if a repo has more than ~2,000–3,000 relevant files, either reject with a clear message or sample intelligently (e.g., prioritize files closest to the repo root, deprioritize deeply nested test fixtures).
- Handle default branch detection properly (`main` vs `master` vs custom).
- Write `fetch_repo.py`, a small CLI script: `python fetch_repo.py https://github.com/owner/repo` prints total file count, filtered file count, and a content sample.
- Write your first `pytest` tests for the fetch + filter logic (mock the API calls so tests don't hit real GitHub every run).

**Definition of done:** Tested end-to-end on 3 real repos of different sizes; filtering logic is correct; caching demonstrably avoids duplicate API calls (log and count requests to confirm).

---

## Week 3 — AST Call Graph, Part 1 (single file)

**Goal:** For one Python file, extract every function, and which other functions each one calls.

- Learn Python's built-in `ast` module: `ast.parse(source)` gives you a tree; `ast.walk()` lets you visit every node.
- For each `ast.FunctionDef` (and `ast.AsyncFunctionDef`), record its name, line number, and docstring.
- Inside each function's body, find every `ast.Call` node and extract the called function/method's name.
- Also record `ast.Import` and `ast.ImportFrom` statements — you'll need these in Week 4 to resolve cross-file calls.
- Build `code_parser.py` with a function like `parse_file(source_code) -> {functions: [...], calls: [...], imports: [...]}`.
- Test it manually on a simple file first, then a file with classes and methods (methods need `self`-aware handling — `self.foo()` should resolve to the class's `foo` method).

**Definition of done:** Given any single Python file's source, you get back an accurate list of its functions and, for each, what it calls — verified by hand against 3–4 real files.

---

## Week 4 — AST Call Graph, Part 2 (cross-file, whole repo)

**Goal:** Merge per-file graphs into one graph for the whole repo, correctly linking calls across files.

- This is the hardest part of the whole project — budget extra time here.
- Merge all per-file results into one graph structure (nodes = functions, identified by `file_path::function_name`; edges = calls).
- Resolve imports: when `file1.py` does `from utils import helper` and later calls `helper()`, you need to link that call to `utils.py::helper`, not treat it as unknown.
- Handle what you can't resolve honestly — dynamic calls (`getattr(obj, name)()`), decorators, and metaprogramming should be flagged as `"unknown/dynamic"` rather than silently dropped or guessed at. This honesty is actually a good engineering signal, not a weakness.
- Build the two query functions that matter most:
  - `find_callers(graph, function_name)` → everything that calls this function (this is the core of "blast radius" — if I change X, everything that *calls* X might break).
  - `find_callees(graph, function_name)` → everything this function calls (useful context).
- Optional: visualize a small graph with `networkx` + `matplotlib` or Graphviz, just to sanity-check visually.

**Definition of done:** Run on a real repo of ~50–100 files. Pick 5–10 functions, manually verify (by reading the code yourself) that the graph's callers/callees are correct.

---

## Week 5 — Embeddings & Vector Search, Part 1 (indexing)

**Goal:** Turn the repo's functions into searchable embeddings.

- Chunk code by function boundaries (not arbitrary character chunks) — use the AST parsing from Week 3 to extract each function as a complete, self-contained chunk including its docstring/comments.
- Set up `sentence-transformers` with `all-MiniLM-L6-v2` (fast, CPU-friendly, ~80MB). Benchmark embedding speed on a batch of ~200 functions to confirm it's fast enough (should be seconds, not minutes).
- Set up Chroma locally, store each function's embedding with metadata: file path, function name, start/end line numbers.
- Build `embed_store.py` with `index_repo(functions)` and `search(query, top_k)`.

**Definition of done:** Index a real repo end-to-end, run a few test queries (e.g., "function that validates user input"), confirm the top results are semantically reasonable.

---

## Week 6 — Embeddings & Vector Search, Part 2 (indirect impact)

**Goal:** Find code that's *conceptually* related to your target function but not connected in the call graph — this is what the graph alone would miss.

- Given the target function's code + docstring, search the vector index for related functions elsewhere — things like duck-typed usage, string-based dispatch, or tests that reference the function's *behavior* without calling it directly by name in a way the AST would catch.
- If time allows, index non-code text too: README sections, docstrings, comments — as separately searchable chunks, so the agent can also flag "the docs mention this behavior" as a soft signal.
- Dedupe: don't show a result the call graph already found — this search is specifically for the *indirect* signal.
- Add a simple relevance threshold so you're not returning near-random low-similarity matches.
- Manually test quality: pick 5 functions, eyeball whether the "conceptually related" results actually make sense.

**Definition of done:** `semantic_search.py` returns genuinely useful indirect matches on a real repo, verified by your own judgment on a handful of cases.

---

## Week 7 — The Agent, Part 1 (tools + single-step calls)

**Goal:** Wire your graph and search functions up as "tools" Gemini can call, and get one working round trip.

- Define each tool as a plain Python function with a clear docstring and type hints (this doubles as the description Gemini sees): `get_callers(function_name)`, `get_callees(function_name)`, `semantic_search(query)`, `read_file(path, start_line, end_line)`.
- Use the `google-genai` SDK: `from google import genai`, `client = genai.Client(api_key=...)`. Gemini supports **automatic Python function calling** — you can pass your plain Python functions directly in `config=types.GenerateContentConfig(tools=[...])` and it handles the call/response wiring for you, which saves you writing manual dispatch code.
- Build the first version: given "I'm changing function X in file Y," the model automatically decides to call `get_callers`, gets results back, and produces an initial answer — just one tool call for now, not a full loop yet.
- Test that the model reliably picks the right tool and forms correct arguments. If you want more control later, Gemini also supports manual function calling mode (you inspect the function-call response and execute it yourself) — worth switching to this once you build the multi-step loop in Week 8, since automatic mode is convenient but harder to log/control step-by-step.

**Definition of done:** `agent.py` v1 — a real API round trip where the model correctly calls a tool and uses the result in its answer.

---

## Week 8 — The Agent, Part 2 (multi-step reasoning loop)

**Goal:** Let the agent chain multiple tool calls and reason across them, like a person investigating code.

- Build the loop: the model reasons → picks a tool → sees the result → decides whether to call another tool or give a final answer. Repeat until it's done or hits a step limit (cap at ~6 steps to control cost and avoid runaway loops). Switch to Gemini's **manual** function calling mode for this — inspect `response.function_calls` yourself, execute the matching Python function, append the result back into the conversation via a function response part, and call `generate_content` again. This gives you full visibility into each step, which you'll want for logging and for the eval work in Weeks 9–10.
- Add the "verify by reading" behavior: after the graph finds a caller, the agent should be able to call `read_file` to actually look at the surrounding code before deciding it's a real risk — this is what makes it feel like investigation, not just a lookup.
- Define a structured final output: affected files/functions, a plain-language reason for each, a confidence level (direct call graph match = high; semantic-only match = medium/low), and the exact line number as evidence.
- Log cost/latency per query: number of tool calls, tokens used, total time — you'll want this for your "scalability" talking points later.

**Definition of done:** `agent.py` v2 — full loop working end-to-end on real questions against real repos, giving structured, cited answers.

---

## Week 9 — Building Your Evaluation Set

**Goal:** Create ground truth you personally trust — this is the single most valuable artifact in the whole project.

- Pick 3 real, medium-sized open-source Python repos (roughly 50–300 relevant files each — avoid huge monorepos; pick things you can reasonably read).
- For each repo, select 6–8 functions spanning different roles: a widely-used utility, a function with few callers, a core piece of business logic, something with likely indirect/conceptual connections.
- For each, manually read the code (use `grep`/your editor's "find references") and determine the real answer: what actually depends on this function, both directly (calls it) and indirectly (tests, docs, related-but-unconnected code).
- Record all of this in `eval_dataset.json`: `{repo, function, expected_direct_callers: [...], expected_related: [...]}`.
- Aim for 20–25 total test cases across the 3 repos.

**Definition of done:** A hand-verified, defensible ground-truth file you could explain and justify line-by-line in an interview.

---

## Week 10 — Running Evals & Measuring Quality

**Goal:** Turn "it seems to work" into real, measurable numbers — and improve them.

- Build `run_eval.py`: for each test case, run the agent, compare its output against your ground truth.
- Define your metrics:
  - **Precision** — of everything it flagged, how much was actually correct?
  - **Recall** — of everything that should have been flagged, how much did it actually find?
  - **Confidence calibration** (optional but impressive) — did its "high confidence" answers tend to be more correct than its "low confidence" ones?
- Run the full suite, record results in `eval_results.md`.
- Look closely at failures: bad chunking? An import-resolution bug in the call graph? Agent stopping too early? Fix the most impactful issue, re-run, and record the before/after numbers.
- This iteration — "found X was causing missed cases, fixed it, recall went from A% to B%" — is exactly the kind of story that makes an interview conversation land well.

**Definition of done:** A results file with real precision/recall numbers, and at least one documented before/after improvement.

---

## Week 11 — Web Interface & Demo Prep

**Goal:** Make it something you can actually show someone in 30 seconds.

- Build a minimal Streamlit UI: repo URL input, "function I'm changing" input, a run button, results shown clearly with file/line citations and confidence levels.
- Handle the obvious failure cases gracefully in the UI: invalid URL, private repo, function not found, repo too large.
- Add a loading indicator (indexing takes a little time — be upfront about it rather than looking frozen).
- Add a one-click example (a pre-filled known repo + function) so anyone — including an interviewer — can try it in 10 seconds without typing anything.

**Definition of done:** A working local Streamlit app you'd be comfortable demoing live, unscripted.

---

## Week 12 — Documentation, Polish, and Your Story

**Goal:** Package the project so it's easy to understand and easy to talk about.

- Write a thorough `README.md`: the problem statement, a simple architecture diagram, how to run it, your eval methodology and results, known limitations, and what you'd change to make it production-scale.
- Write a short "design decisions" section: why hybrid (graph + semantic) instead of pure semantic search, why function-level chunking instead of fixed-size chunks, why Python-only for the MVP, what tradeoffs the no-GPU constraint forced.
- Record a 2–3 minute demo video walking through one real example, start to finish.
- Clean up the code: consistent naming, docstrings, basic type hints, remove dead code and stray debug prints.
- Push a clean version to GitHub and pin it where recruiters/interviewers will actually see it.

**Definition of done:** A project you could hand someone cold and have them understand what it does, why it's hard, and how well it works — without you in the room.

---

## Turning This Into Resume Bullets

Fill these in with your real numbers once you have them:

- *"Built a hybrid code-analysis agent combining AST-based call graphs with semantic search to predict change impact across public repositories — achieved __% precision / __% recall on a 25-case hand-labeled evaluation set spanning 3 real repos."*
- *"Designed a no-clone ingestion pipeline using GitHub's REST API, reducing repo analysis to on-demand file fetches with in-memory caching."*
- *"Built a multi-step tool-using agent (search → verify → cite) rather than single-shot RAG, with structured, confidence-scored, line-cited output."*
- *"Iterated on retrieval quality using a self-built eval harness, improving recall from __% to __% by fixing import-resolution gaps in the call graph."*

## How This Maps to Real Job Descriptions

- "Build and evaluate agentic systems with tool use" → your multi-step agent loop
- "Design hybrid retrieval combining structured and unstructured data" → call graph + embeddings
- "Own evaluation methodology for LLM-based features" → your hand-labeled eval set + precision/recall tracking
- "Work with real-world, messy data" → arbitrary public repos, not a clean dataset
- "Make architecture tradeoffs under constraints" → your no-GPU, no-clone, CPU-only design decisions

---

## If You Have Extra Time (stretch goals, optional)

- Support a second language (JavaScript/TypeScript) to show your parser design generalizes.
- Add a simple caching layer keyed by commit SHA so re-analyzing an unchanged repo is instant.
- Add a basic cost dashboard (tokens + $ per query) — a small but real "production thinking" touch.
- Deploy it (Render/Fly.io free tier) so it's a live link, not just something reviewers have to run locally.

---

## Future Roadmap — Multi-Language and Whole-Repository Support

The 12-week MVP focuses on Python because Python's standard `ast` module gives us a reliable starting point. The next version should expand in layers rather than pretending every file type can be analyzed with the same parser.

### Layer 1 — Support More Text Files

Add a generic repository file pipeline for files that can be read and searched but do not yet have exact dependency analysis:

- Markdown: `README.md`, documentation, design notes
- JSON and YAML: configuration and deployment files
- TOML and INI: project and tool configuration
- SQL: queries, migrations, and schema references
- Shell scripts: `.sh`, `.ps1`, and `.bat`
- Build files: `Dockerfile`, `Makefile`, CI workflows

For each file, store:

```text
path, file type, start/end lines, text, commit SHA
```

Chunk these files by logical sections where possible. Use semantic search to answer questions such as "where is the database connection configured?" Label these results as semantic evidence, not exact call-graph evidence.

### Layer 2 — Create a Common Analysis Interface

Introduce a language-independent contract so each parser produces the same kind of output:

```text
LanguageAdapter
  supports(path) -> bool
  parse(path, source) -> ParsedFile

ParsedFile
  language
  symbols
  imports
  calls
  references
  parse_errors
```

Keep the existing Python parser behind a `PythonAdapter`. The call graph should consume `ParsedFile` objects rather than knowing Python-specific AST details.

### Layer 3 — Add JavaScript and TypeScript

This should be the first additional programming-language target because web repositories commonly mix Python with JavaScript or TypeScript.

- Detect `.js`, `.jsx`, `.ts`, and `.tsx`
- Use Tree-sitter or the TypeScript compiler API
- Extract functions, classes, methods, imports, exports, and calls
- Resolve ES module imports and CommonJS `require()` where possible
- Preserve unresolved dynamic behavior as `unknown/dynamic`
- Add mixed-language fixtures and real-repository tests

Do not merge JavaScript results into the graph until the common symbol and edge format is stable.

### Layer 4 — Add Additional Compiled Languages

Add languages based on user demand and parser maturity:

| Language | File types | Candidate parser |
|---|---|---|
| Java | `.java` | Tree-sitter or JavaParser |
| Go | `.go` | Go standard parser or Tree-sitter |
| Rust | `.rs` | Tree-sitter or `syn` |
| C/C++ | `.c`, `.h`, `.cpp` | Tree-sitter or Clang |
| C# | `.cs` | Roslyn or Tree-sitter |

For each language, repeat the same delivery cycle:

1. Add a language adapter and file detection rules.
2. Define name, import, call, and reference mappings.
3. Add unit fixtures for normal and dynamic syntax.
4. Add cross-file graph tests.
5. Add hand-labeled evaluation cases.
6. Measure precision, recall, parse failures, and unsupported syntax.

### Layer 5 — Analyze an Entire Repository

Replace the Python-only filter with a repository inventory step:

```text
GitHub tree
    -> classify files by language and content type
    -> exclude binaries, secrets, vendored code, and generated output
    -> enforce total file and byte limits
    -> fetch selected files in batches
    -> run the correct adapter
    -> index symbols and text chunks
```

Add safeguards before broadening the file scope:

- Detect binary files and skip them
- Exclude `.git`, dependencies, build output, caches, and generated files
- Never index likely secrets such as `.env`, private keys, or credentials
- Enforce limits on file count, total bytes, and per-file size
- Use commit SHA as the cache key
- Report skipped files and the reason for skipping
- Keep repository contents in memory unless the user explicitly enables persistence

### Cross-Language Graph Rules

The first version should support relationships within one language and explicit cross-language boundaries only where they are observable:

- Python importing Python
- TypeScript importing TypeScript
- Frontend calling an HTTP endpoint implemented by Python
- Configuration referring to a file, command, route, or environment variable

Cross-language relationships should have a separate confidence level. For example, an HTTP route match is weaker than a direct function call and should be labeled `medium` rather than `high`.

### Evaluation Plan for Expansion

Maintain separate evaluation metrics for each language and evidence type:

- Direct call precision and recall
- Import-resolution precision and recall
- Semantic-search relevance at fixed `top_k`
- Parse failure rate
- Unsupported-file classification accuracy
- Cross-language boundary precision

Do not combine all languages into one score until each language has enough hand-labeled cases. A realistic first milestone is 10 cases for Python and 10 cases for JavaScript/TypeScript across at least three mixed-language repositories.

### Suggested Release Stages

```text
v1.0  Python exact analysis + generic text search
v1.1  JavaScript/TypeScript exact analysis
v1.2  Mixed-language repository inventory and caching
v1.3  Configuration, SQL, and documentation relationships
v2.0  Java, Go, Rust, C/C++, or C# based on demand
```

The product promise should remain precise: DepScope can provide exact dependency evidence for supported languages, semantic evidence for readable unsupported files, and an explicit explanation whenever analysis is uncertain.
