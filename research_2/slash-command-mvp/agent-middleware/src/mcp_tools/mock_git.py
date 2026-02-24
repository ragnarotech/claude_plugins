"""
Mock Git/GitHub MCP tools implemented as in-process Python functions.

# DECISION: Mock MCP tools are implemented as in-process Python functions for MVP.
# Why: Same rationale as mock_jira.py -- avoids subprocess MCP server overhead.
# Production: Separate MCP server using the GitHub MCP server
#   (https://github.com/github/github-mcp-server) via stdio transport.
#   Authenticated via GitHub App installation token (from K8s Secret).
# Standard: MCP tools protocol (model-controlled invocation).
# Alternative: Considered the @modelcontextprotocol/server-github npm package
#   as a subprocess, but JS in a Python service adds complexity for MVP.

# MCP_MAPPING: git_list_commits → list_commits tool; git_create_pr → create_pull_request tool.
#   In production these names align with the GitHub MCP server's tool names.
"""

MOCK_COMMITS = [
    {
        "hash": "a1b2c3d",
        "author": "alice",
        "message": "fix(auth): resolve JWT refresh token expiry issue",
        "date": "2026-02-22T14:00:00Z",
        "files_changed": 3,
    },
    {
        "hash": "e4f5a6b",
        "author": "bob",
        "message": "feat(api): add rate limiting middleware skeleton",
        "date": "2026-02-22T11:00:00Z",
        "files_changed": 5,
    },
    {
        "hash": "c7d8e9f",
        "author": "charlie",
        "message": "chore: update dependencies",
        "date": "2026-02-21T16:00:00Z",
        "files_changed": 2,
    },
    {
        "hash": "f0a1b2c",
        "author": "alice",
        "message": "test(auth): add integration tests for token refresh",
        "date": "2026-02-21T10:00:00Z",
        "files_changed": 4,
    },
    {
        "hash": "d3e4f5a",
        "author": "david",
        "message": "docs: update API documentation",
        "date": "2026-02-20T15:00:00Z",
        "files_changed": 1,
    },
]


def git_list_commits(limit: int = 10) -> dict:
    """List recent git commits."""
    # Production: GET /repos/{owner}/{repo}/commits via GitHub REST API.
    return {"commits": MOCK_COMMITS[:limit], "total": len(MOCK_COMMITS)}


def git_create_pr(
    title: str,
    description: str,
    base_branch: str = "main",
    head_branch: str = "feature/auto-generated",
) -> dict:
    """Create a pull request. Returns mock PR URL.

    # DECISION: PR number is hardcoded to 42 for MVP demo purposes.
    # Production: POST /repos/{owner}/{repo}/pulls via GitHub REST API;
    #   head_branch must already exist on the remote.
    """
    pr_number = 42
    return {
        "success": True,
        "pr_number": pr_number,
        "pr_url": f"https://github.com/company/repo/pull/{pr_number}",
        "title": title,
        "base": base_branch,
        "head": head_branch,
        "status": "open",
        "message": f"Pull request #{pr_number} created successfully",
    }
