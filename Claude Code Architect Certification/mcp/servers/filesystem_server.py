"""
CCA-F D2.1 + D2.4: MCP Filesystem Server
Demonstrates: precise tool descriptions, project-level .mcp.json config,
structured error responses, tool distribution best practices.

Run: python -m mcp.servers.filesystem_server
"""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent, CallToolResult
import mcp.server.stdio as stdio_server

from mcp.errors import transient_error, validation_error, permission_error

# D2.3: Only expose tools this server is responsible for
# Don't mix filesystem + database tools in one server (tool overload)
ALLOWED_EXTENSIONS = {".log", ".txt", ".json", ".jsonl", ".md", ".yaml", ".yml"}
MAX_FILE_SIZE_MB = 10


def create_server() -> Server:
    server = Server("filesystem-incident-server")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="read_log_file",
                # D2.1: VERB(read) + NOUN(log file lines) + BOUNDARY(by line range) + CONSTRAINT(size limit)
                description="Read a specific line range from a log file. "
                            "Returns raw log content. "
                            "Limited to files under 10MB and .log/.txt extensions.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute or relative path to the log file"
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "1-indexed start line (inclusive)",
                            "minimum": 1
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "1-indexed end line (inclusive). Max 500 lines per call.",
                            "maximum": 9999
                        },
                    },
                    "required": ["file_path", "start_line", "end_line"],
                }
            ),
            Tool(
                name="list_incident_files",
                # D2.1: Precise boundary — only incident-related directories
                description="List files in an incident data directory. "
                            "Returns file names, sizes, and modification times. "
                            "Only searches within the project data/ directory.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "Subdirectory within data/ to list (e.g. 'logs', 'tickets')"
                        },
                        "extension_filter": {
                            "type": "string",
                            "description": "Filter by extension, e.g. '.log'. Optional.",
                        }
                    },
                    "required": ["directory"],
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> CallToolResult:
        if name == "read_log_file":
            return await _read_log_file(**arguments)
        if name == "list_incident_files":
            return await _list_incident_files(**arguments)
        return CallToolResult(
            isError=True,
            content=[TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        )

    return server


async def _read_log_file(file_path: str, start_line: int, end_line: int) -> CallToolResult:
    """D2.2: Every error path returns structured MCPError, never raw exception."""
    path = Path(file_path)

    # Validation errors
    if not path.exists():
        return CallToolResult(**validation_error(
            f"File not found: {file_path}",
            source="filesystem_server",
            expected_format="Valid file path within the project directory",
        ))

    if path.suffix not in ALLOWED_EXTENSIONS:
        return CallToolResult(**validation_error(
            f"Unsupported file type: {path.suffix}",
            source="filesystem_server",
            expected_format=f"One of: {', '.join(ALLOWED_EXTENSIONS)}",
        ))

    # Permission check
    try:
        stat = path.stat()
    except PermissionError:
        return CallToolResult(**permission_error(
            f"No read permission for: {file_path}",
            source="filesystem_server",
        ))

    if stat.st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        return CallToolResult(**validation_error(
            f"File too large: {stat.st_size / 1024 / 1024:.1f}MB (max {MAX_FILE_SIZE_MB}MB)",
            source="filesystem_server",
            expected_format="Files under 10MB. Use line range parameters to read large files in chunks.",
        ))

    # Clamp line range
    end_line = min(end_line, start_line + 499)  # max 500 lines

    try:
        lines = path.read_text(errors="replace").splitlines()
        selected = lines[start_line - 1:end_line]
        return CallToolResult(content=[TextContent(
            type="text",
            text=json.dumps({
                "file": str(path),
                "start_line": start_line,
                "end_line": min(end_line, len(lines)),
                "total_lines": len(lines),
                "content": "\n".join(selected),
            })
        )])
    except OSError as e:
        return CallToolResult(**transient_error(
            str(e), source="filesystem_server", retry_after=2
        ))


async def _list_incident_files(directory: str, extension_filter: str = "") -> CallToolResult:
    base = Path("data") / directory
    if not base.exists():
        return CallToolResult(**validation_error(
            f"Directory not found: data/{directory}",
            source="filesystem_server",
            expected_format="Valid subdirectory within data/",
        ))

    files = []
    for f in sorted(base.iterdir()):
        if not f.is_file():
            continue
        if extension_filter and f.suffix != extension_filter:
            continue
        stat = f.stat()
        files.append({
            "name": f.name,
            "path": str(f),
            "size_kb": round(stat.st_size / 1024, 1),
            "modified": stat.st_mtime,
        })

    return CallToolResult(content=[TextContent(
        type="text",
        text=json.dumps({"directory": str(base), "files": files, "count": len(files)})
    )])


async def main():
    server = create_server()
    async with stdio_server.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream,
            InitializationOptions(
                server_name="filesystem-incident-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities={}
                ),
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
