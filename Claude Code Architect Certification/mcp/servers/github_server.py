"""
CCA-F D2.4: MCP GitHub Server
Read-only access to repository files and commits for code analysis.
Credentials via env vars (GITHUB_TOKEN, GITHUB_REPO).
"""
from __future__ import annotations
import asyncio
import json
import os
import httpx
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent, CallToolResult
import mcp.server.stdio as stdio_server
from mcp.errors import transient_error, validation_error, permission_error

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # e.g. "org/repo"
GITHUB_API = "https://api.github.com"


def create_server() -> Server:
    server = Server("github-incident-server")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="read_file",
                # D2.1: Precise description
                "description": "Read the contents of a file from the GitHub repository at a specific ref. "
                              "Returns file content as text. Limited to files under 1MB.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path in the repo, e.g. 'src/main.py'"},
                        "ref": {"type": "string", "default": "main", "description": "Branch, tag, or commit SHA"},
                    },
                    "required": ["path"],
                }
            ),
            Tool(
                name="list_commits",
                "description": "List recent commits for a file or directory path. "
                              "Returns commit SHA, message, author, and timestamp. "
                              "Limited to last 20 commits.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File or directory path to get history for"},
                        "limit": {"type": "integer", "default": 10, "maximum": 20},
                    },
                    "required": ["path"],
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> CallToolResult:
        if not GITHUB_TOKEN:
            return CallToolResult(**permission_error(
                "GITHUB_TOKEN not set", source="github_server"
            ))
        if name == "read_file":
            return await _read_file(arguments["path"], arguments.get("ref", "main"))
        if name == "list_commits":
            return await _list_commits(arguments["path"], arguments.get("limit", 10))
        return CallToolResult(isError=True, content=[TextContent(type="text", text="{}")])

    return server


async def _read_file(path: str, ref: str) -> CallToolResult:
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3.raw"}
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}?ref={ref}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, headers=headers)
            if r.status_code == 404:
                return CallToolResult(**validation_error(
                    f"File not found: {path}@{ref}", source="github_server",
                    expected_format="Valid file path in the repository"
                ))
            if r.status_code == 403:
                return CallToolResult(**permission_error("GitHub token lacks read access", source="github_server"))
            r.raise_for_status()
            return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                "path": path, "ref": ref, "content": r.text[:50000]
            }))])
        except httpx.TimeoutException as e:
            return CallToolResult(**transient_error(str(e), source="github_server", retry_after=3))


async def _list_commits(path: str, limit: int) -> CallToolResult:
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/commits?path={path}&per_page={min(limit, 20)}"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            commits = [
                {"sha": c["sha"][:8], "message": c["commit"]["message"][:100],
                 "author": c["commit"]["author"]["name"], "ts": c["commit"]["author"]["date"]}
                for c in r.json()
            ]
            return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                "path": path, "commits": commits
            }))])
        except httpx.TimeoutException as e:
            return CallToolResult(**transient_error(str(e), source="github_server", retry_after=3))


async def main():
    server = create_server()
    async with stdio_server.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, InitializationOptions(
            server_name="github-incident-server", server_version="1.0.0",
            capabilities=server.get_capabilities(notification_options=None, experimental_capabilities={}),
        ))


if __name__ == "__main__":
    asyncio.run(main())
