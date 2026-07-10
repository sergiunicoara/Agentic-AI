#!/usr/bin/env python3
"""Generate Python and JS gRPC stubs from proto/v1/agent_events.proto.

Usage:
    pip install grpcio-tools
    python scripts/generate_proto.py
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROTO_DIR = ROOT / "proto" / "v1"
PROTO_FILE = PROTO_DIR / "agent_events.proto"

# Python output goes into backend/app/generated/
PY_OUT = ROOT / "backend" / "app" / "generated"
PY_OUT.mkdir(parents=True, exist_ok=True)

print(f"Generating Python stubs → {PY_OUT}")
subprocess.run(
    [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO_DIR}",          # resolve imports relative to proto/v1/
        f"--python_out={PY_OUT}",
        f"--grpc_python_out={PY_OUT}",
        str(PROTO_FILE),
    ],
    check=True,
)

# Fix relative import in generated grpc file (grpc_tools quirk)
grpc_file = PY_OUT / "agent_events_pb2_grpc.py"
if grpc_file.exists():
    content = grpc_file.read_text()
    content = content.replace(
        "import agent_events_pb2 as agent__events__pb2",
        "from app.generated import agent_events_pb2 as agent__events__pb2",
    )
    grpc_file.write_text(content)
    print("Fixed relative import in agent_events_pb2_grpc.py")

print("Done.")
