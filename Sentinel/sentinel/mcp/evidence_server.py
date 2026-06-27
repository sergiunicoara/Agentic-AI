from fastmcp import FastMCP

mcp = FastMCP("Sentinel Evidence Server")

@mcp.tool()
def gather_evidence(tool_name: str, target_path: str) -> str:
    """
    Run a static analysis tool (e.g. bandit, ruff, pip-audit) on the target path.
    """
    return f"Stub evidence output for tool {tool_name} on {target_path}"
