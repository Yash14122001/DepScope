"""FastAPI backend for repository analysis and general repository questions."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import AnalysisContext, make_tools, run_agent
from .call_graph import build_call_graph
from .github_client import GitHubClient, GitHubClientError, parse_github_url
from .repo_filter import filter_repository_files

load_dotenv()
app = FastAPI(title="DepScope API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@dataclass
class RepositorySession:
    repo: str
    branch: str
    files: dict[str, str]
    context: AnalysisContext


sessions: dict[str, RepositorySession] = {}


class AnalyzeRequest(BaseModel):
    url: str
    max_files: int = Field(default=200, ge=1, le=2500)


class AskRequest(BaseModel):
    session_id: str
    question: str = Field(min_length=1, max_length=4000)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, object]:
    try:
        owner, repo = parse_github_url(request.url)
        client = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
        tree = client.get_repo_tree(owner, repo)
        paths = filter_repository_files(tree.entries, max_files=request.max_files)
        files = {}
        for path in paths:
            content = client.get_file_content(owner, repo, tree.branch, path)
            if "\x00" not in content:
                files[path] = content
        graph = build_call_graph({path: content for path, content in files.items() if path.endswith(".py")})
    except (ValueError, GitHubClientError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Repository analysis failed: {error}") from error

    session_id = uuid.uuid4().hex
    context = AnalysisContext(graph=graph, files=files)
    sessions[session_id] = RepositorySession(f"{owner}/{repo}", tree.branch, files, context)
    return {"session_id": session_id, "repo": f"{owner}/{repo}", "branch": tree.branch, "file_count": len(files), "function_count": len(graph.functions)}


@app.post("/api/ask")
def ask(request: AskRequest) -> dict[str, object]:
    session = sessions.get(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Analysis session not found. Analyze the repository again.")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured on the server.")

    from google import genai

    prompt = f"""You are DepScope, a careful repository analyst.
Repository: {session.repo}
Branch: {session.branch}
Analyzed readable files: {len(session.files)}
Exact Python functions: {len(session.context.graph.functions)}

Answer the user's question about this repository. Use tools to inspect files and relationships before answering. Cite exact paths and line numbers whenever possible. Clearly distinguish direct static evidence, text-search evidence, and an inference. If the repository does not contain enough evidence, say so instead of guessing.

For broad questions such as "what is this project about?" or "give me an overview", use at most two high-value tools, such as listing files and reading the README, then answer. Do not repeatedly call the same tool or keep investigating after you have enough evidence. For focused questions, use only the tools needed to support the answer.

User question: {request.question}"""
    try:
        result = run_agent(genai.Client(api_key=api_key), prompt, make_tools(session.context))
    except Exception as error:
        error_text = str(error)
        if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
            wait_match = re.search(r"retryDelay['\"]?: ['\"]?(\d+)s", error_text)
            wait_message = f" Try again in about {wait_match.group(1)} seconds." if wait_match else " Try again later."
            raise HTTPException(status_code=429, detail=f"Gemini API quota is exhausted.{wait_message}") from error
        raise HTTPException(status_code=502, detail=f"Gemini request failed: {error}") from error
    return {"answer": result.answer, "tool_calls": result.tool_calls, "elapsed_seconds": round(result.elapsed_seconds, 2)}


frontend = Path(__file__).resolve().parents[1] / "web"
app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")