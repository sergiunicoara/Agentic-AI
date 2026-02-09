from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_dataset(path: Path, registry_path: Path = Path("app/eval/datasets/registry.yaml")) -> dict[str, Any]:
    """Verify dataset integrity against the registry.

    Returns the registry entry if found. Raises on mismatch.
    """

    if not registry_path.exists():
        return {}

    reg = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    for entry in reg.get("datasets", []) or []:
        p = Path(str(entry.get("path", "")))
        if p.resolve() == path.resolve():
            expected = str(entry.get("sha256", ""))
            if expected:
                got = _sha256(path)
                if got != expected:
                    raise RuntimeError(f"Dataset hash mismatch for {path}: expected {expected}, got {got}")
            return entry

    return {}
