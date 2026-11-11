"""Writers for the analytical tables: local filesystem or S3.

One Protocol, two backends, so the very same publishing code feeds the offline
demo (a local directory) and the deployed lake (the curated S3 bucket). boto3 is
imported inside the methods: the CI workers do not have it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Writer(Protocol):
    """Where the published tables land."""

    def write(self, key: str, payload: bytes) -> str: ...
    def uri(self, key: str) -> str: ...


class LocalWriter:
    """Writes under a local root directory (demo, tests, dry runs)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def write(self, key: str, payload: bytes) -> str:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return str(target)

    def uri(self, key: str) -> str:
        return str(self.root / key)


class S3Writer:
    """Writes into an S3 bucket (the deployed curated zone)."""

    def __init__(self, bucket: str, prefix: str = "", client=None) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self._client = client

    def _s3(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("s3")
        return self._client

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def write(self, key: str, payload: bytes) -> str:
        full = self._key(key)
        self._s3().put_object(Bucket=self.bucket, Key=full, Body=payload, ContentType="text/csv")
        return self.uri(key)

    def uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{self._key(key)}"


class MemoryWriter:
    """Keeps everything in memory — used by the tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def write(self, key: str, payload: bytes) -> str:
        self.objects[key] = payload
        return f"memory://{key}"

    def uri(self, key: str) -> str:
        return f"memory://{key}"
