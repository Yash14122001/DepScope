from unittest.mock import Mock

import pytest

from src.github_client import GitHubClient, RateLimitError, parse_github_url


def response(status_code, json_data=None, text=""):
    result = Mock(status_code=status_code, text=text)
    result.json.return_value = json_data
    result.raise_for_status.side_effect = None
    return result


def test_parse_github_url():
    assert parse_github_url("https://github.com/psf/requests.git") == ("psf", "requests")


def test_tree_is_cached():
    session = Mock()
    session.headers = {}
    session.get.return_value = response(200, {"tree": [{"path": "src/app.py", "type": "blob"}]})
    client = GitHubClient(session=session)

    first = client.get_repo_tree("owner", "repo", "main")
    second = client.get_repo_tree("owner", "repo", "main")

    assert first is second
    assert session.get.call_count == 1


def test_content_is_cached():
    session = Mock()
    session.headers = {}
    session.get.return_value = response(200, text="print('hello')")
    client = GitHubClient(session=session)

    assert client.get_file_content("owner", "repo", "main", "app.py") == "print('hello')"
    assert client.get_file_content("owner", "repo", "main", "app.py") == "print('hello')"
    assert session.get.call_count == 1


def test_tree_falls_back_to_main_when_default_branch_tree_is_missing():
    session = Mock()
    session.headers = {}
    session.get.side_effect = [
        response(200, {"default_branch": "trunk"}),
        response(404),
        response(200, {"tree": []}),
    ]
    client = GitHubClient(session=session)

    tree = client.get_repo_tree("owner", "repo")

    assert tree.branch == "main"
    assert session.get.call_count == 3


def test_rate_limit_is_explicit():
    session = Mock()
    session.headers = {}
    session.get.return_value = response(403)
    with pytest.raises(RateLimitError):
        GitHubClient(session=session).get_repo_tree("owner", "repo", "main")