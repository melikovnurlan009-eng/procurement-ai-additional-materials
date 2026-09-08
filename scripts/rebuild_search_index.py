#!/usr/bin/env python3
"""Rebuild the searchable index (SQLite FTS5 + Qdrant dense vectors) from the included
corpus export (`code/corpus_export/data/`), using the actual, unmodified production
script (`code/build_chunk_index.py`). No LLM call is made anywhere in this script --
lexical indexing is pure SQL, and dense indexing embeds already-final chunk text with a
fixed local model (BAAI/bge-m3), which is deterministic (no sampling, no seed needed).

Prerequisites: `docker compose up -d qdrant` (bundle root) already running.

Usage (from the bundle root):
    python3 scripts/rebuild_search_index.py
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
CORPUS_DIR = CODE_DIR / "corpus_export" / "data"
DB_PATH = CODE_DIR / "state" / "chunk_index_merged.sqlite3"
COLLECTION = "chunks__bge_m3__merged"
QDRANT_URL = "http://localhost:6333"
EXPECTED_CHUNKS = 22042
EXPECTED_EDGES = 27600


def wait_for_qdrant(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(f"{QDRANT_URL}/collections", timeout=3)
            return True
        except Exception:
            time.sleep(1)
    return False


def run(cmd):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=CODE_DIR, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {' '.join(str(c) for c in cmd)}")
    return result.stdout


def main():
    if not CORPUS_DIR.exists():
        raise SystemExit(f"missing {CORPUS_DIR} -- is this the full bundle?")

    print("Waiting for Qdrant (did you run `docker compose up -d qdrant`?)...")
    if not wait_for_qdrant():
        raise SystemExit("Qdrant not reachable at " + QDRANT_URL)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("\n=== Stage 1/3: lexical index (SQLite FTS5, deterministic, no model call) ===")
    out = run([sys.executable, "build_chunk_index.py", "lexical",
               "--corpus-dir", str(CORPUS_DIR), "--db", str(DB_PATH)])
    stats = json.loads(out)
    if stats["chunks_indexed"] != EXPECTED_CHUNKS or stats["edges_indexed"] != EXPECTED_EDGES:
        raise SystemExit(
            f"FAIL: expected {EXPECTED_CHUNKS} chunks / {EXPECTED_EDGES} edges, "
            f"got {stats['chunks_indexed']} / {stats['edges_indexed']}"
        )
    print(f"PASS: {stats['chunks_indexed']} chunks, {stats['edges_indexed']} edges "
          f"-- matches the documented corpus exactly.")

    print("\n=== Stage 2/3: graph densification (adds retrieval_source_id/retrieval_target_id/\n"
          "retrieval_resolution columns that chunk_retrieval.py requires -- discovered missing\n"
          "from build_chunk_index.py's own schema during end-to-end testing of this exact\n"
          "sequence; deterministic, no model call) ===")
    run([sys.executable, "densify_graph_edges.py", "--db", str(DB_PATH), "--apply"])

    print("\n=== Stage 3/3: dense index (local BAAI/bge-m3 embeddings -> Qdrant) ===")
    print("This embeds 22,042 chunks with a locally-hosted model -- expect this to take "
          "several minutes depending on your hardware (CPU vs. GPU/MPS).")
    out = run([sys.executable, "build_chunk_index.py", "dense",
               "--corpus-dir", str(CORPUS_DIR), "--db", str(DB_PATH),
               "--collection", COLLECTION])
    dense_stats = json.loads(out)
    print(f"PASS: {dense_stats.get('vectors', '?')} vectors embedded into "
          f"Qdrant collection '{COLLECTION}'.")

    print("\nDone. Start the application with:\n"
          "    cd code && python chunk_api.py\n"
          "and test with:\n"
          "    curl -X POST http://127.0.0.1:8899/search "
          "-H 'Content-Type: application/json' "
          "-d '{\"query\": \"standstill period before contract award\", \"limit\": 3}'")


if __name__ == "__main__":
    main()
