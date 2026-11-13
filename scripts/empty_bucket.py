"""Empty a versioned S3 bucket, so CloudFormation can delete it.

A versioned bucket keeps the old versions and the delete markers: ``aws s3 rm
--recursive`` is not enough. This script deletes every version and every
marker, then the bucket itself.

Usage: ``python3 scripts/empty_bucket.py <bucket> [<bucket> ...]``
"""

from __future__ import annotations

import sys


def _client():
    import boto3

    return boto3.client("s3")


def empty_bucket(client, bucket: str) -> int:
    """Delete every version and delete marker of the bucket."""
    removed = 0
    for _ in range(10):
        listing = client.list_object_versions(Bucket=bucket)
        items = [
            {"Key": row["Key"], "VersionId": row["VersionId"]}
            for row in listing.get("Versions", []) + listing.get("DeleteMarkers", [])
        ]
        if not items:
            break
        for offset in range(0, len(items), 1000):
            chunk = items[offset : offset + 1000]
            client.delete_objects(Bucket=bucket, Delete={"Objects": chunk})
            removed += len(chunk)
    return removed


def main(argv: list[str]) -> int:
    """Empty the buckets given on the command line."""
    if not argv:
        print("usage: empty_bucket.py <bucket> [<bucket> ...]", file=sys.stderr)
        return 2
    client = _client()
    for bucket in argv:
        removed = empty_bucket(client, bucket)
        client.delete_bucket(Bucket=bucket)
        print(f"deleted s3://{bucket} ({removed} versions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
