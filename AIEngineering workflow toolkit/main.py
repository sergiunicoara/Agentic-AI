"""
AI Engineering Workflow Toolkit — CLI Entry Point

Commands:
  review   Run the full 5-layer review pipeline on a diff
  eval     Run the evaluation harness against the golden dataset
  serve    Start the FastMCP server for Claude Code integration
  queue    Process the post-file-write review queue
"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

import click

_REPO_ROOT = Path(__file__).parent


@click.group()
def cli():
    """AI Engineering Workflow Toolkit — Governed Code Review Infrastructure."""


# ──────────────────────────────────────────────────────────────────────────────
# review
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--diff", "diff_file", type=click.Path(exists=True), default=None,
              help="Path to a .patch or .diff file.")
@click.option("--file", "source_file", type=click.Path(exists=True), default=None,
              help="Review a specific source file (generates diff against HEAD).")
@click.option("--staged", is_flag=True, default=False,
              help="Review the current git staged diff.")
@click.option("--output", type=click.Choice(["pretty", "json"]), default="pretty",
              help="Output format.")
def review(diff_file, source_file, staged, output):
    """Run the full review pipeline on a diff."""
    diff = _resolve_diff(diff_file, source_file, staged)

    if not diff.strip():
        click.echo("No diff to review. Nothing to do.")
        sys.exit(0)

    click.echo(f"\n[AIWT] Running 5-layer review pipeline...")
    click.echo(f"       Diff size: {len(diff)} chars\n")

    from orchestrator.agent import OrchestratorAgent
    from review_agent.agent import ReviewAgent

    async def _run():
        orchestrator = OrchestratorAgent()
        merged = await orchestrator.run(diff, _REPO_ROOT)
        reviewer = ReviewAgent()
        return await reviewer.review(merged)

    disposition = asyncio.run(_run())

    if output == "json":
        click.echo(json.dumps(disposition, indent=2))
    else:
        _print_disposition(disposition)


def _resolve_diff(diff_file, source_file, staged) -> str:
    if diff_file:
        return Path(diff_file).read_text(encoding="utf-8")

    if source_file:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", source_file],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        diff = result.stdout.strip()
        if not diff:
            # Untracked file — use full content
            content = Path(source_file).read_text(encoding="utf-8", errors="replace")
            rel = Path(source_file).name
            lines = [f"+++ b/{rel}"] + [f"+{l}" for l in content.splitlines()]
            return "\n".join(lines)
        return diff

    if staged:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    # Default: unstaged + staged working tree diff
    result = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _print_disposition(disposition: dict) -> None:
    verdict = disposition.get("verdict", "unknown").upper()
    findings = disposition.get("findings", [])
    suppressed = disposition.get("suppressed_count", 0)
    summary = disposition.get("summary", "")

    verdict_colours = {
        "APPROVE": "\033[92m",         # green
        "COMMENT": "\033[93m",         # yellow
        "REQUEST_CHANGES": "\033[91m", # red
    }
    reset = "\033[0m"
    colour = verdict_colours.get(verdict, "")

    click.echo(f"\n{'─'*60}")
    click.echo(f"  Verdict: {colour}{verdict}{reset}")
    click.echo(f"  Findings: {len(findings)}  (suppressed: {suppressed})")
    click.echo(f"{'─'*60}\n")

    if summary:
        click.echo(f"  {summary}\n")

    if findings:
        click.echo("  Findings (ranked by severity):\n")
        for i, f in enumerate(findings, 1):
            sev = f.get("severity", "info").upper()
            sev_colours = {"ERROR": "\033[91m", "WARNING": "\033[93m", "INFO": "\033[96m"}
            sc = sev_colours.get(sev, "")
            file_ref = f.get("file", "")
            line_ref = f":{f['line']}" if f.get("line") else ""
            click.echo(
                f"  {i:2d}. [{sc}{sev}{reset}] [{f.get('domain','?').upper()}] "
                f"{file_ref}{line_ref}"
            )
            click.echo(f"      Rule: {f.get('rule','')}")
            click.echo(f"      {f.get('message','')}")
            if f.get("suggestion"):
                click.echo(f"      → {f['suggestion']}")
            click.echo()

    click.echo(f"{'─'*60}\n")


# ──────────────────────────────────────────────────────────────────────────────
# eval
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--case", default=None, help="Run a single case by ID (e.g. GC-001).")
@click.option("--verbose", is_flag=True, default=False, help="Show per-dimension scores.")
@click.option("--compare", is_flag=True, default=False,
              help="Show score delta (↑/↓) vs the previous eval run.")
def eval(case, verbose, compare):
    """Run the LLM-as-judge evaluation harness against the golden dataset."""
    from eval.harness import run_harness
    summary = asyncio.run(run_harness(case_id=case, verbose=verbose, compare=compare))
    if not summary["passed_threshold"]:
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# serve
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio",
              help="MCP transport. Use 'stdio' for Claude Code integration.")
def serve(transport):
    """Start the FastMCP server for Claude Code integration."""
    from mcp_server.server import get_mcp_server
    mcp = get_mcp_server()
    if mcp is None:
        click.echo("fastmcp is not installed. Run: pip install fastmcp", err=True)
        sys.exit(1)
    click.echo(f"[AIWT] Starting MCP server (transport={transport})...")
    mcp.run(transport=transport)


# ──────────────────────────────────────────────────────────────────────────────
# queue
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--clear", is_flag=True, default=False, help="Clear the queue after processing.")
def queue(clear):
    """Process the post-file-write review queue."""
    queue_file = _REPO_ROOT / ".claude" / "review_queue.jsonl"
    if not queue_file.exists():
        click.echo("Review queue is empty.")
        return

    entries = []
    with open(queue_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    if not entries:
        click.echo("Review queue is empty.")
        return

    click.echo(f"[AIWT] Processing {len(entries)} queued review(s)...\n")

    from orchestrator.agent import OrchestratorAgent
    from review_agent.agent import ReviewAgent

    async def _process_all():
        orchestrator = OrchestratorAgent()
        reviewer = ReviewAgent()
        for entry in entries:
            click.echo(f"  Reviewing: {Path(entry['file']).name}")
            merged = await orchestrator.run(entry["diff"], _REPO_ROOT)
            disposition = await reviewer.review(merged)
            _print_disposition(disposition)

    asyncio.run(_process_all())

    if clear:
        queue_file.unlink()
        click.echo("[AIWT] Queue cleared.")


# ──────────────────────────────────────────────────────────────────────────────
# ui
# ──────────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host.")
@click.option("--port", default=8000, show_default=True, type=int, help="Bind port.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (dev mode).")
def ui(host, port, reload):
    """Start the web UI server (FastAPI + React)."""
    try:
        import uvicorn
    except ImportError:
        click.echo("uvicorn is not installed. Run: uv pip install 'ai-engineering-workflow-toolkit[ui]'", err=True)
        sys.exit(1)

    ui_dist = _REPO_ROOT / "ui" / "dist"
    if not ui_dist.exists():
        click.echo(
            "React UI not built yet. Run:\n"
            "  cd ui && npm install && npm run build",
            err=True,
        )
        click.echo("Starting API-only mode (no frontend).")

    click.echo(f"[AIWT] Web UI → http://{host}:{port}")
    click.echo(f"[AIWT] API docs → http://{host}:{port}/api/docs\n")
    uvicorn.run("api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    cli()
