from __future__ import annotations

"""Dataset management CLI.

Implements light-weight dataset registration and retrieval to demonstrate
"large-scale dataset management tooling" without requiring an external system.

Commands:
  - register: copy a JSONL dataset into the dataset store and add it to the registry
  - resolve:  resolve a registry entry to a local file path (downloads if needed)
"""

import argparse
import yaml
from pathlib import Path

from app.eval.datasets.store import default_store


REGISTRY_PATH = Path("app/eval/datasets/registry.yaml")


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"datasets": []}
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {"datasets": []}


def _save_registry(reg: dict) -> None:
    REGISTRY_PATH.write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")


def register(name: str, path: Path) -> None:
    store = default_store()
    ref = store.put(path, name=name)
    reg = _load_registry()
    reg.setdefault("datasets", [])
    reg["datasets"] = [d for d in reg["datasets"] if d.get("sha256") != ref.sha256]
    reg["datasets"].append({"name": ref.name, "sha256": ref.sha256, "path": ref.uri})
    _save_registry(reg)
    print(ref.uri)


def resolve(sha256: str) -> None:
    store = default_store()
    reg = _load_registry()
    for d in reg.get("datasets", []):
        if d.get("sha256") == sha256:
            uri = str(d.get("path"))
            if uri.startswith("file://"):
                print(uri[len("file://") :])
                return
            print(uri)
            return
    raise SystemExit("dataset not found")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("register")
    a.add_argument("--name", required=True)
    a.add_argument("--path", required=True)

    b = sub.add_parser("resolve")
    b.add_argument("--sha256", required=True)

    args = ap.parse_args()
    if args.cmd == "register":
        register(args.name, Path(args.path))
    elif args.cmd == "resolve":
        resolve(args.sha256)


if __name__ == "__main__":
    main()
