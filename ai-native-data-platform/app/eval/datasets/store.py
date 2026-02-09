from __future__ import annotations

"""Dataset store abstractions.

Large-scale evaluation systems typically separate the **dataset registry**
(semantic name -> immutable version) from the **dataset store** (blob storage).

This module provides a tiny abstraction to demonstrate that separation.

Backends:
  - Local filesystem (default)
  - S3 (optional, requires boto3)
"""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetRef:
    name: str
    sha256: str
    uri: str  # file://... or s3://...


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class LocalDatasetStore:
    def __init__(self, root: str = "datasets"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, src: Path, *, name: str) -> DatasetRef:
        digest = sha256_file(src)
        dst = self.root / name / f"{digest}.jsonl"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            dst.write_bytes(src.read_bytes())
        return DatasetRef(name=name, sha256=digest, uri=f"file://{dst.resolve()}")

    def get(self, ref: DatasetRef) -> Path:
        if not ref.uri.startswith("file://"):
            raise ValueError("not a file URI")
        return Path(ref.uri[len("file://") :])


def maybe_s3_store():
    """Return an S3 store implementation if boto3 is installed."""
    try:
        import boto3  # type: ignore
    except Exception:
        return None

    class S3DatasetStore:  # pragma: no cover
        def __init__(self, bucket: str, prefix: str = "datasets"):
            self.bucket = bucket
            self.prefix = prefix.strip("/")
            self.s3 = boto3.client("s3")

        def put(self, src: Path, *, name: str) -> DatasetRef:
            digest = sha256_file(src)
            key = f"{self.prefix}/{name}/{digest}.jsonl"
            self.s3.upload_file(src.as_posix(), self.bucket, key)
            return DatasetRef(name=name, sha256=digest, uri=f"s3://{self.bucket}/{key}")

        def get(self, ref: DatasetRef, *, dst_dir: str = "datasets_cache") -> Path:
            if not ref.uri.startswith("s3://"):
                raise ValueError("not an s3 URI")
            _, _, rest = ref.uri.partition("s3://")
            bucket, _, key = rest.partition("/")
            out = Path(dst_dir) / ref.name / f"{ref.sha256}.jsonl"
            out.parent.mkdir(parents=True, exist_ok=True)
            if not out.exists():
                self.s3.download_file(bucket, key, out.as_posix())
            return out

    return S3DatasetStore


def default_store() -> LocalDatasetStore:
    root = os.environ.get("DATASET_STORE_ROOT", "datasets")
    return LocalDatasetStore(root=root)
