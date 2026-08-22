"""Small GitHub REST client that keeps repository data in memory."""

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


class GitHubClientError(RuntimeError):
    """Base error for expected GitHub API failures."""


class RepositoryNotFoundError(GitHubClientError):
    """The repository does not exist or is not publicly accessible."""


class BranchNotFoundError(GitHubClientError):
    """The requested branch does not exist."""


class RateLimitError(GitHubClientError):
    """GitHub rejected the request because the API rate limit was reached."""


@dataclass(frozen=True)
class RepositoryTree:
    """A repository tree and the branch it came from."""

    branch: str
    entries: list[dict[str, Any]]


class GitHubClient:
    """Fetch public GitHub data without cloning or writing files to disk."""

    def __init__(self, token: str | None = None, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json"})
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        self._tree_cache: dict[tuple[str, str, str], RepositoryTree] = {}
        self._content_cache: dict[tuple[str, str, str, str], str] = {}

    def _get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.get(url, timeout=30, **kwargs)
        if response.status_code == 403:
            raise RateLimitError("GitHub API rate limit reached. Set GITHUB_TOKEN and try again.")
        if response.status_code == 404:
            raise RepositoryNotFoundError("Repository or branch was not found.")
        response.raise_for_status()
        return response.json()

    def get_default_branch(self, owner: str, repo: str) -> str:
        data = self._get_json(f"https://api.github.com/repos/{owner}/{repo}")
        return str(data["default_branch"])

    def get_repo_tree(self, owner: str, repo: str, branch: str | None = None) -> RepositoryTree:
        requested_branch = branch or self.get_default_branch(owner, repo)
        cache_key = (owner, repo, requested_branch)
        if cache_key in self._tree_cache:
            return self._tree_cache[cache_key]

        branches = [requested_branch]
        if branch is None:
            branches.extend(candidate for candidate in ("main", "master") if candidate not in branches)
        last_error: GitHubClientError | None = None
        for candidate in branches:
            try:
                data = self._get_json(
                    f"https://api.github.com/repos/{owner}/{repo}/git/trees/{quote(candidate, safe='')}?recursive=1"
                )
                tree = RepositoryTree(candidate, data.get("tree", []))
                self._tree_cache[cache_key] = tree
                if candidate != requested_branch:
                    self._tree_cache[(owner, repo, candidate)] = tree
                return tree
            except RepositoryNotFoundError as error:
                last_error = error
        raise BranchNotFoundError(f"Could not find a branch for {owner}/{repo}.") from last_error

    def get_file_content(self, owner: str, repo: str, branch: str, path: str) -> str:
        cache_key = (owner, repo, branch, path)
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{quote(branch, safe='')}/{quote(path, safe='/')}"
        response = self.session.get(url, timeout=30)
        if response.status_code == 403:
            raise RateLimitError("GitHub API rate limit reached. Set GITHUB_TOKEN and try again.")
        if response.status_code == 404:
            raise RepositoryNotFoundError(f"File was not found: {path}")
        response.raise_for_status()
        content = response.text
        self._content_cache[cache_key] = content
        return content


def parse_github_url(url: str) -> tuple[str, str]:
    """Return owner and repository from https://github.com/owner/repo."""
    from urllib.parse import urlparse

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise ValueError("Expected a GitHub URL such as https://github.com/owner/repo")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include both an owner and repository")
    return parts[0], parts[1].removesuffix(".git")