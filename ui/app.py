"""Streamlit demo for exploring a repository's change impact."""

import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from src.call_graph import build_call_graph
from src.github_client import GitHubClient, GitHubClientError, parse_github_url
from src.repo_filter import filter_python_files


def load_repository(url: str, token: str | None = None, max_files: int = 200) -> tuple[str, dict[str, str]]:
    """Fetch and filter a repository without cloning it."""
    owner, repo = parse_github_url(url)
    client = GitHubClient(token=token)
    tree = client.get_repo_tree(owner, repo)
    paths = filter_python_files(tree.entries, max_files=max_files)
    files = {path: client.get_file_content(owner, repo, tree.branch, path) for path in paths}
    return tree.branch, files


def evidence_for_edge(edge, files: dict[str, str]) -> str:
    """Return the source line where a caller invokes the callee."""
    path = edge.caller.split("::", 1)[0]
    lines = files.get(path, "").splitlines()
    return lines[edge.line - 1].strip() if 0 < edge.line <= len(lines) else "Source line unavailable"


def main() -> None:
    import streamlit as st

    load_dotenv()
    st.set_page_config(page_title="DepScope", page_icon="D", layout="wide")
    st.title("DepScope")
    st.caption("Explore what may be affected when a Python function changes.")

    with st.sidebar:
        st.header("Repository")
        example = st.checkbox("Use example", value=True)
        default_url = "https://github.com/psf/requests" if example else ""
        repo_url = st.text_input("Public GitHub URL", value=default_url)
        function_name = st.text_input("Function to change", value="request")
        max_files = st.number_input("Maximum Python files", min_value=1, max_value=2500, value=200)
        analyze = st.button("Analyze impact", type="primary", use_container_width=True)

    if not analyze:
        st.info("Enter a public repository and function, then run an analysis.")
        return
    if not repo_url or not function_name:
        st.warning("Repository URL and function name are required.")
        return

    try:
        with st.spinner("Fetching Python files and building the call graph..."):
            branch, files = load_repository(repo_url, os.getenv("GITHUB_TOKEN"), int(max_files))
            graph = build_call_graph(files)
            callers = graph.find_callers(function_name)
            callees = graph.find_callees(function_name)
    except (ValueError, GitHubClientError) as error:
        st.error(str(error))
        return
    except Exception as error:
        st.error(f"Analysis failed: {error}")
        return

    st.success(f"Analyzed {len(files)} Python files on branch `{branch}`.")
    if function_name not in graph.functions and not any(item.name == function_name for item in graph.functions.values()):
        st.warning("Function was not found in the filtered source files.")
        return

    left, right = st.columns(2)
    with left:
        st.subheader("Potential callers")
        if not callers:
            st.write("No statically resolved callers found.")
        for edge in callers:
            st.markdown(f"**{edge.caller}**  \\nConfidence: `high`  \\nLine {edge.line}: `{evidence_for_edge(edge, files)}`")
    with right:
        st.subheader("Callees for context")
        if not callees:
            st.write("No statically resolved callees found.")
        for edge in callees:
            confidence = "unknown" if edge.dynamic else "high"
            st.markdown(f"**{edge.callee}**  \\nConfidence: `{confidence}`  \\nLine {edge.line}")

    st.caption("Direct call-graph matches are high-confidence static evidence. Dynamic Python behavior may not be resolved.")


if __name__ == "__main__":
    main()