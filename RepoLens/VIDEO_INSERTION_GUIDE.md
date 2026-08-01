# Final demo insertion guide

Scenes 6 and 7 are now included in `DEMO_VIDEO.mp4`. The movie is 04:15 and contains the
repository-backed MCP configuration/server evidence and the CI workflow definition.

If you later obtain live MCP-client, GitHub Actions, or Langfuse recordings, replace the matching
25-second and 40-second clips at the same positions; do not describe the current static evidence
cards as live external recordings.

| Final timing | Clip to insert | What to show | Voiceover |
| --- | --- | --- | --- |
| 02:50-03:15 | Scene 6 - MCP (25 seconds) | `.mcp.json`, then `search_code`, `get_file`, and `get_repo_map` in an MCP-capable client. | "The same retrieval and browsing capabilities are exposed through MCP. That means an MCP client can search code, retrieve a file, and inspect the repository map without duplicating the application logic." |
| 03:15-03:55 | Scene 7 - evaluation, CI, observability (40 seconds) | `evals/golden.yaml`, a green GitHub Actions run, and a Langfuse trace or local OpenTelemetry console trace. | "Quality is measured with a golden question set covering retrieval, answer correctness, citation validity and coverage, groundedness, refusal accuracy, and latency. CI runs deterministic objective evaluation tests, while the frontend is type-checked and production-built. OpenTelemetry and optional Langfuse instrumentation provide visibility into ingestion, retrieval, generation, and MCP calls." |
| 03:55-04:15 | Scene 8 - closing card (20 seconds) | Transition from the cited answer and source viewer to the `CODEX` card: **Grounded. Verifiable. Observable.** | The final project-summary narration. |

After inserting the 65 seconds, the final presentation is approximately 04:15.
