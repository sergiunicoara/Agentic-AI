"""
CCA-F D2.4: MCP Postgres Server
Project-level config (.mcp.json), read-only enforcement via pre_tool_use hook.
Demonstrates credential management via env vars (not hardcoded).
"""
from __future__ import annotations
import asyncio
import json
import os
import asyncpg
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent, CallToolResult
import mcp.server.stdio as stdio_server
from mcp.errors import transient_error, validation_error, permission_error

# D2.4: Credentials via env vars, NEVER hardcoded
DB_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/incidents")


def create_server() -> Server:
    server = Server("postgres-incident-server")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="query_incidents",
                # D2.1: Precise description — read-only, specific table, result limit
                description="Query the incidents table by status, service, or date range. "
                            "Returns up to 100 incident records. "
                            "Read-only — no writes permitted.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string", "description": "Filter by service name. Optional."},
                        "status": {"type": "string", "enum": ["open", "resolved", "escalated"], "description": "Filter by status. Optional."},
                        "days_back": {"type": "integer", "default": 30, "description": "Look back N days"},
                        "limit": {"type": "integer", "default": 20, "maximum": 100},
                    },
                    "required": [],
                }
            ),
            Tool(
                name="get_incident_by_id",
                # D2.1: Single-record lookup — clear boundary
                description="Retrieve a single incident record by its ID. "
                            "Returns full incident details including timeline and resolution notes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "incident_id": {"type": "string", "description": "Incident ID, e.g. INC-2047"},
                    },
                    "required": ["incident_id"],
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> CallToolResult:
        if name == "query_incidents":
            return await _query_incidents(**arguments)
        if name == "get_incident_by_id":
            return await _get_incident(arguments["incident_id"])
        return CallToolResult(isError=True, content=[TextContent(type="text", text="{}")])

    return server


async def _query_incidents(service_name="", status="", days_back=30, limit=20) -> CallToolResult:
    try:
        conn = await asyncpg.connect(DB_URL)
        try:
            where = ["created_at > NOW() - INTERVAL $1 DAY"]
            params = [days_back]
            if service_name:
                params.append(service_name)
                where.append(f"service_name = ${len(params)}")
            if status:
                params.append(status)
                where.append(f"status = ${len(params)}")
            params.append(min(limit, 100))
            sql = f"SELECT * FROM incidents WHERE {' AND '.join(where)} LIMIT ${len(params)}"
            rows = await conn.fetch(sql, *params)
            return CallToolResult(content=[TextContent(
                type="text",
                text=json.dumps({"incidents": [dict(r) for r in rows], "count": len(rows)}, default=str)
            )])
        finally:
            await conn.close()
    except asyncpg.PostgresConnectionError as e:
        return CallToolResult(**transient_error(str(e), source="postgres_server", retry_after=5))
    except Exception as e:
        return CallToolResult(**transient_error(str(e), source="postgres_server"))


async def _get_incident(incident_id: str) -> CallToolResult:
    try:
        conn = await asyncpg.connect(DB_URL)
        try:
            row = await conn.fetchrow("SELECT * FROM incidents WHERE id = $1", incident_id)
            if not row:
                return CallToolResult(**validation_error(
                    f"Incident {incident_id} not found",
                    source="postgres_server",
                    expected_format="Valid incident ID, e.g. INC-2047",
                ))
            return CallToolResult(content=[TextContent(
                type="text",
                text=json.dumps(dict(row), default=str)
            )])
        finally:
            await conn.close()
    except asyncpg.PostgresConnectionError as e:
        return CallToolResult(**transient_error(str(e), source="postgres_server", retry_after=5))


async def main():
    server = create_server()
    async with stdio_server.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, InitializationOptions(
            server_name="postgres-incident-server",
            server_version="1.0.0",
            capabilities=server.get_capabilities(notification_options=None, experimental_capabilities={}),
        ))


if __name__ == "__main__":
    asyncio.run(main())
