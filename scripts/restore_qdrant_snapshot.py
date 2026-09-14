#!/usr/bin/env python3
"""Restore the shipped Qdrant dense-index snapshot instead of rebuilding it from scratch.

Downloads the exact snapshot of the evaluated Qdrant collection (a GitHub Release asset --
too large for a normal git-tracked file) and restores it directly into a running Qdrant
container. This skips build_chunk_index.py's `dense` stage entirely (no ~20-40 min
re-embedding) and, more importantly, sidesteps a disclosed reproducibility gap: Qdrant's
dense index (HNSW) is an approximate nearest-neighbour structure, so a from-scratch `dense`
rebuild is not guaranteed to return byte-identical retrieval rankings to what was originally
evaluated (see README.md, "What is and is not exactly reproducible"). Restoring this snapshot
gives you the exact same index, not a re-embedded approximation of it.

Usage:
    docker compose up -d qdrant
    python scripts/restore_qdrant_snapshot.py

Still need the lexical/graph side of the index (SQLite FTS5) -- run
`build_chunk_index.py lexical` first (or the full `rebuild_search_index.py`, which builds
lexical, then would normally build dense too; run this script instead of its dense step).
"""
from __future__ import annotations
import argparse
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = (
    "https://github.com/melikovnurlan009-eng/procurement-ai-additional-materials/"
    "releases/download/qdrant-snapshot-v1/chunks_bge_m3_merged.snapshot"
)
DEFAULT_COLLECTION = "chunks__bge_m3__merged"
EXPECTED_POINTS = 22042


def wait_for_qdrant(qdrant_url: str, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{qdrant_url}/collections", timeout=3)
            return
        except (urllib.error.URLError, ConnectionError):
            time.sleep(2)
    raise SystemExit(
        f"Qdrant not reachable at {qdrant_url} after {timeout}s -- "
        f"run `docker compose up -d qdrant` first."
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", default=DEFAULT_URL, help="snapshot download URL")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    args = ap.parse_args()

    import requests  # already a project dependency (code/requirements.txt)

    wait_for_qdrant(args.qdrant_url)

    print(f"Downloading {args.url} ...")
    resp = requests.get(args.url, stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    next_report = 0
    chunks = []
    for chunk in resp.iter_content(chunk_size=1 << 20):
        chunks.append(chunk)
        downloaded += len(chunk)
        if total and downloaded >= next_report:
            print(f"  {downloaded / (1 << 20):,.0f} / {total / (1 << 20):,.0f} MB")
            next_report += 20 << 20  # report roughly every 20 MB
    data = b"".join(chunks)
    print(f"Downloaded {len(data):,} bytes.")

    print(f"Uploading to Qdrant collection '{args.collection}' ...")
    upload = requests.post(
        f"{args.qdrant_url}/collections/{args.collection}/snapshots/upload",
        files={"snapshot": ("chunks_bge_m3_merged.snapshot", data)},
        timeout=600,
    )
    upload.raise_for_status()
    print(upload.json())

    info = requests.get(f"{args.qdrant_url}/collections/{args.collection}", timeout=10).json()[
        "result"
    ]
    points = info["points_count"]
    print(f"\nRestored. Collection '{args.collection}': {points:,} points, status={info['status']}")
    if points != EXPECTED_POINTS:
        print(
            f"WARNING: expected {EXPECTED_POINTS:,} points, got {points:,} -- "
            f"the snapshot may be stale, or this collection already had other data in it."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
