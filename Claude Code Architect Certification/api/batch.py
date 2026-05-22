"""
CCA-F D4.5: Batch Processing Strategies — Message Batches API
Exam facts:
- Message Batches API: 50% cost savings vs synchronous
- Up to 24-hour processing window
- Use when latency tolerance allows AND cost matters
- Never block synchronously on batch — poll or use webhook
"""
from __future__ import annotations
import asyncio
import json
import sys
import time
import logging
from pathlib import Path
import anthropic
from prompts.few_shot import build_rca_prompt
from schemas.rca_output import RCAOutput

logger = logging.getLogger(__name__)
client = anthropic.Anthropic()

# D4.5: When to use batch vs synchronous (exam decision criteria)
# Batch: >10 items AND latency > 1 minute acceptable AND cost is a constraint
# Sync:  real-time requirement OR <10 items OR interactive session


def submit_batch(tickets: list[dict], output_dir: str = "results/") -> str:
    """
    Submit multiple tickets for RCA analysis using Message Batches API.
    Returns batch_id for polling.

    D4.5: 50% cost savings, up to 24h processing window.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    requests = []
    for ticket in tickets:
        ticket_id = ticket.get("id", f"ticket_{len(requests)}")
        prompt = build_rca_prompt(ticket["content"])

        requests.append(anthropic.types.message_create_params.Request(
            custom_id=ticket_id,
            params=anthropic.types.MessageCreateParamsNonStreaming(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                # D4.3: Force structured output via tool in batch
                tools=[_rca_batch_tool()],
                tool_choice={"type": "tool", "name": "generate_rca"},
            )
        ))

    batch = client.messages.batches.create(requests=requests)
    logger.info(f"Submitted batch {batch.id} with {len(requests)} requests")

    # Persist batch ID for later polling (D4.5: don't block)
    metadata_path = Path(output_dir) / f"{batch.id}_metadata.json"
    metadata_path.write_text(json.dumps({
        "batch_id": batch.id,
        "submitted_at": time.time(),
        "request_count": len(requests),
        "ticket_ids": [t.get("id") for t in tickets],
        "status": "submitted",
    }, indent=2))

    print(f"Batch submitted: {batch.id}")
    print(f"Poll with: python -m api.batch --poll {batch.id}")
    return batch.id


def poll_batch(batch_id: str, output_dir: str = "results/") -> dict:
    """
    D4.5: Poll batch status. Do NOT block synchronously — call on a timer.
    Returns summary of completed/failed requests.
    """
    batch = client.messages.batches.retrieve(batch_id)
    status = batch.processing_status

    summary = {
        "batch_id": batch_id,
        "status": status,
        "counts": {
            "processing": batch.request_counts.processing,
            "succeeded": batch.request_counts.succeeded,
            "errored": batch.request_counts.errored,
            "canceled": batch.request_counts.canceled,
            "expired": batch.request_counts.expired,
        }
    }

    if status == "ended":
        results = _collect_results(batch_id, output_dir)
        summary["results"] = results

    return summary


def _collect_results(batch_id: str, output_dir: str) -> list[dict]:
    """Collect and persist results when batch completes."""
    results = []
    for result in client.messages.batches.results(batch_id):
        ticket_id = result.custom_id

        if result.result.type == "succeeded":
            message = result.result.message
            rca_data = None
            for block in message.content:
                if block.type == "tool_use" and block.name == "generate_rca":
                    rca_data = block.input
                    break

            if rca_data:
                try:
                    rca = RCAOutput(**rca_data, ticket_id=ticket_id)
                    out_path = Path(output_dir) / f"{ticket_id}_rca.json"
                    out_path.write_text(rca.model_dump_json(indent=2))
                    results.append({"ticket_id": ticket_id, "status": "ok"})
                except Exception as e:
                    results.append({"ticket_id": ticket_id, "status": "parse_error", "error": str(e)})
            else:
                results.append({"ticket_id": ticket_id, "status": "no_tool_use"})

        elif result.result.type == "errored":
            # D4.5: Batch failure resubmission — log failed IDs for retry
            error = result.result.error
            results.append({
                "ticket_id": ticket_id,
                "status": "api_error",
                "error_type": error.type,
                "resubmit": True,  # flag for resubmission
            })
            logger.warning(f"Batch item {ticket_id} failed: {error.type}")

    return results


def _rca_batch_tool() -> dict:
    """RCA tool schema for batch requests — same as synchronous."""
    return {
        "name": "generate_rca",
        "description": "Generate a structured Root Cause Analysis report",
        "input_schema": {
            "type": "object",
            "properties": {
                "root_cause": {"type": "string"},
                "severity": {"type": "string", "enum": ["P1", "P2", "P3", "P4"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "evidence": {"type": "array", "items": {"type": "object"}},
                "next_steps": {"type": "array", "items": {"type": "string"}},
                "escalate": {"type": "boolean"},
                "escalation_reason": {"type": "string"},
            },
            "required": ["root_cause", "severity", "confidence", "next_steps", "escalate"],
        }
    }


# CLI entry point
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch ticket processing")
    parser.add_argument("--input", help="JSONL file of tickets")
    parser.add_argument("--poll", help="Poll an existing batch ID")
    parser.add_argument("--wait", action="store_true", help="Poll until complete")
    args = parser.parse_args()

    if args.input:
        tickets = [json.loads(line) for line in Path(args.input).read_text().splitlines() if line]
        batch_id = submit_batch(tickets)
        if args.wait:
            print("Waiting for batch to complete (polling every 60s)...")
            while True:
                result = poll_batch(batch_id)
                print(json.dumps(result["counts"], indent=2))
                if result["status"] == "ended":
                    break
                time.sleep(60)

    elif args.poll:
        result = poll_batch(args.poll)
        print(json.dumps(result, indent=2))
