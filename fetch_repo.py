"""Print a small in-memory summary of a public GitHub repository."""

import argparse
import os

from dotenv import load_dotenv

from src.github_client import GitHubClient, parse_github_url
from src.repo_filter import filter_python_files


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Inspect Python files in a GitHub repository without cloning it.")
    parser.add_argument("url", help="Public repository URL, for example https://github.com/psf/requests")
    parser.add_argument("--include-tests", action="store_true", help="Include tests in the filtered file list")
    parser.add_argument("--max-files", type=int, default=2500)
    args = parser.parse_args()

    owner, repo = parse_github_url(args.url)
    client = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
    tree = client.get_repo_tree(owner, repo)
    paths = filter_python_files(tree.entries, args.include_tests, args.max_files)
    print(f"Repository: {owner}/{repo}")
    print(f"Branch: {tree.branch}")
    print(f"Total tree entries: {len(tree.entries)}")
    print(f"Filtered Python files: {len(paths)}")
    if paths:
        sample_path = paths[0]
        sample = client.get_file_content(owner, repo, tree.branch, sample_path)
        print(f"\nContent sample: {sample_path}")
        print(sample[:500])


if __name__ == "__main__":
    main()