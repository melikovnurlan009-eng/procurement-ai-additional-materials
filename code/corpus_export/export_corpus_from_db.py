#!/usr/bin/env python3
"""Export the live, evaluated corpus (chunks, documents, edges) from the frozen
`chunk_index_merged.sqlite3` database into the JSONL format `build_chunk_index.py`
(already in this bundle, unmodified) expects to read via its `--corpus-dir` argument.

This is a plain data export -- no LLM call, no re-chunking, no re-scraping. It exists so
this bundle can ship the actual final corpus data without shipping a 262MB binary SQLite
file: the export below is chunk-level text and metadata only (~tens of MB), and
`build_chunk_index.py` + `rebuild_search_index.sh` reconstruct a byte-for-byte-equivalent
searchable index from it (the lexical index is deterministic; the dense index is
deterministic given the same fixed local embedding model, since no LLM sampling is
involved in embedding fixed text).

Usage:
    python export_corpus_from_db.py --db <path to chunk_index_merged.sqlite3> --out corpus_export
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path

STRUCTURAL_RELATIONS = {"CONTAINS", "HAS_CHUNK"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--out", default="corpus_export", type=Path)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    args.out.mkdir(parents=True, exist_ok=True)

    # Live chunks only: not filtered out, not superseded by a later dedup decision.
    cur.execute("PRAGMA table_info(chunks)")
    chunk_cols = [r[1] for r in cur.fetchall()]
    export_cols = [c for c in chunk_cols if c not in ("superseded_by", "filtered_out")]
    cur.execute(
        f"SELECT {', '.join(export_cols)} FROM chunks "
        f"WHERE (filtered_out = 0 OR filtered_out IS NULL) AND superseded_by IS NULL"
    )
    n_chunks = 0
    with (args.out / "chunks.jsonl").open("w") as f:
        for row in cur.fetchall():
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            n_chunks += 1

    cur.execute("SELECT * FROM documents")
    with (args.out / "documents.jsonl").open("w") as f:
        n_docs = 0
        for row in cur.fetchall():
            f.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            n_docs += 1

    cur.execute("SELECT edge_id, source_id, relation, target_id, evidence_method, "
                "evidence_text, resolution_status, confidence FROM edges")
    all_edges = [dict(row) for row in cur.fetchall()]
    structural = [e for e in all_edges if e.get("relation") in STRUCTURAL_RELATIONS]
    reference = [e for e in all_edges if e.get("relation") not in STRUCTURAL_RELATIONS]

    with (args.out / "edges.jsonl").open("w") as f:
        for e in structural:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with (args.out / "edges_v2.jsonl").open("w") as f:
        for e in reference:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(json.dumps({
        "chunks_exported": n_chunks,
        "documents_exported": n_docs,
        "structural_edges_exported": len(structural),
        "reference_edges_exported": len(reference),
        "out_dir": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
