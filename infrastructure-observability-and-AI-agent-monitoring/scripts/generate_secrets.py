#!/usr/bin/env python3
"""Print production secrets for copy/paste into a protected env store.

This intentionally never writes a .env file or logs existing secrets.
"""

import argparse
import json
import secrets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent",
        action="append",
        required=True,
        help="Agent name to create a dedicated ingestion key for; repeat as needed.",
    )
    args = parser.parse_args()

    agent_keys = {agent: secrets.token_urlsafe(48) for agent in sorted(set(args.agent))}
    print(f"JWT_SECRET={secrets.token_urlsafe(48)}")
    print(f"EMIT_AGENT_KEYS={json.dumps(agent_keys, separators=(',', ':'))}")


if __name__ == "__main__":
    main()
