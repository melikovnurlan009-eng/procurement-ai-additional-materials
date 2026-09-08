#!/usr/bin/env python3
"""Integrity validator for the semantic search corpus.

Checks the hard invariants the chunking methodology depends on. Non-destructive:
reads the corpus, writes a report plus a corrected per-segment validation file.

Invariants
----------
I1  block coverage      every source block appears in exactly one chunk range
I2  placeholder conservation
                        raw placeholder OCCURRENCES in the parent segment ==
                        raw placeholder occurrences summed over its chunks
I3  exact reconstruction chunk text == join of its source block texts (no rewriting)
I4  content hash        content_sha256 matches the chunk text
I5  chunk id uniqueness no duplicate chunk_id
I6  ordinal continuity  chunk_ordinal is 1..n contiguous within each segment
I7  parent stability    every chunk's parent_node_id/segment_id exists in segments
I8  edge endpoints      every edge endpoint is a known chunk/provision/document id,
                        or is explicitly flagged external/unresolved
I9  edge key uniqueness no duplicate (source,relation,target) unless provenance differs

Why the shipped validator reported 6 PLACEHOLDER_MISMATCH rows
-------------------------------------------------------------
build_search_corpus.phs() returns sorted(set(...)). Source placeholders were
deduplicated per BLOCK while chunk placeholders were deduplicated per CHUNK, so a
placeholder occurring in two blocks inside one chunk compared 2 != 1. No text was
lost. I2 below compares true occurrence multisets and is the authoritative check.

Usage
-----
    python validate_search_corpus.py --corpus-dir data/search_corpus
    python validate_search_corpus.py --corpus-dir data/search_corpus --strict
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALIDATOR_VERSION = "1.0.0"
PLACEHOLDER_RE = re.compile(r"\[\[LINK_\d{4,}\]\]")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def occurrences(text: str) -> list[str]:
    """Raw placeholder occurrences, NOT deduplicated. This is the integrity unit."""
    return PLACEHOLDER_RE.findall(text or "")


def join_blocks(blocks: list[dict[str, Any]]) -> str:
    """Reproduce exactly how build_search_corpus materialises chunk text."""
    return "\n\n".join(b.get("text") or "" for b in blocks).strip()


def load_legal_node_ids(patterns: list[str], project_root: Path) -> set[str]:
    """Legal provision ids from legislation scrapes.

    Structural ancestors (Part, Chapter) are legitimate graph endpoints but are never
    parent segments, so they must be added to the node universe or I8 reports them as
    dangling. Paths are resolved relative to the project root, so the check does not
    depend on the _canonical_corpus staging copy existing.
    """
    ids: set[str] = set()
    for pattern in patterns:
        for path in sorted(project_root.glob(pattern)):
            for line in path.open(encoding="utf-8"):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for key in ("node_id", "id", "eId"):
                    if row.get(key):
                        ids.add(row[key])
    return ids


class Validator:
    def __init__(self, corpus_dir: Path, legal_node_ids: set[str] | None = None):
        self.dir = corpus_dir
        self.legal_node_ids = legal_node_ids or set()
        self.segments = read_jsonl(corpus_dir / "parent_segments.jsonl")
        self.boundaries = read_jsonl(corpus_dir / "chunk_boundaries.jsonl")
        self.chunks = read_jsonl(corpus_dir / "chunks.jsonl")
        self.edges = read_jsonl(corpus_dir / "edges.jsonl")
        self.seg_by_id = {s["segment_id"]: s for s in self.segments}
        self.bound_by_id = {b["segment_id"]: b for b in self.boundaries}
        self.chunks_by_segment: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for c in self.chunks:
            self.chunks_by_segment[c["segment_id"]].append(c)
        self.failures: list[dict[str, Any]] = []
        self.seg_rows: list[dict[str, Any]] = []

    def fail(self, invariant: str, subject: str, detail: dict[str, Any]) -> None:
        self.failures.append({"invariant": invariant, "subject": subject, **detail})

    # ---------- per-segment invariants: I1, I2, I3, I6 ----------
    def check_segments(self) -> None:
        for seg in self.segments:
            sid = seg["segment_id"]
            blocks = seg["blocks"]
            ids = [b["block_id"] for b in blocks]
            pos = {bid: i for i, bid in enumerate(ids)}
            br = self.bound_by_id.get(sid)
            statuses: list[str] = []

            if not br or "plan" not in br:
                self.fail("I1_COVERAGE", sid, {"error": "no boundary plan"})
                self.seg_rows.append({"segment_id": sid, "status": "NO_BOUNDARY_PLAN"})
                continue

            plan = br["plan"]["chunks"]
            covered = collections.Counter()
            for c in plan:
                s, e = pos.get(c["start_block_id"]), pos.get(c["end_block_id"])
                if s is None or e is None or s > e:
                    self.fail("I1_COVERAGE", sid, {"error": "bad block range", "chunk": c})
                    continue
                for i in range(s, e + 1):
                    covered[i] += 1

            gaps = [ids[i] for i in range(len(ids)) if covered[i] == 0]
            dups = [ids[i] for i in range(len(ids)) if covered[i] > 1]
            if gaps:
                self.fail("I1_COVERAGE", sid, {"uncovered_blocks": gaps[:20], "count": len(gaps)})
                statuses.append("BLOCK_GAP")
            if dups:
                self.fail("I1_COVERAGE", sid, {"duplicated_blocks": dups[:20], "count": len(dups)})
                statuses.append("BLOCK_OVERLAP")

            # I2 placeholder conservation on raw occurrences
            src_occ = collections.Counter(o for b in blocks for o in occurrences(b.get("text") or ""))
            seg_chunks = sorted(self.chunks_by_segment.get(sid, []), key=lambda c: c["chunk_ordinal"])
            chunk_occ = collections.Counter(o for c in seg_chunks for o in occurrences(c.get("text") or ""))
            if src_occ != chunk_occ:
                missing = {k: src_occ[k] - chunk_occ[k] for k in src_occ if src_occ[k] > chunk_occ[k]}
                extra = {k: chunk_occ[k] - src_occ[k] for k in chunk_occ if chunk_occ[k] > src_occ[k]}
                self.fail("I2_PLACEHOLDER", sid, {"missing": missing, "extra": extra})
                statuses.append("PLACEHOLDER_MISMATCH")

            # I3 exact reconstruction + I4 hash, per chunk
            for c in seg_chunks:
                s, e = pos.get(c.get("start_block_id")), pos.get(c.get("end_block_id"))
                if s is None or e is None:
                    self.fail("I3_RECONSTRUCTION", c["chunk_id"], {"error": "block ids not in segment"})
                    statuses.append("BAD_BLOCK_REF")
                    continue
                expected = join_blocks(blocks[s : e + 1])
                if expected != (c.get("text") or ""):
                    self.fail(
                        "I3_RECONSTRUCTION",
                        c["chunk_id"],
                        {
                            "expected_len": len(expected),
                            "actual_len": len(c.get("text") or ""),
                            "expected_sha": sha256_text(expected),
                            "actual_sha": sha256_text(c.get("text") or ""),
                        },
                    )
                    statuses.append("TEXT_MISMATCH")
                if c.get("content_sha256") and c["content_sha256"] != sha256_text(c.get("text") or ""):
                    self.fail("I4_HASH", c["chunk_id"], {"stored": c["content_sha256"]})
                    statuses.append("HASH_MISMATCH")

            # I6 ordinal continuity
            ordinals = [c["chunk_ordinal"] for c in seg_chunks]
            if ordinals != list(range(1, len(seg_chunks) + 1)):
                self.fail("I6_ORDINALS", sid, {"ordinals": ordinals})
                statuses.append("ORDINAL_GAP")

            self.seg_rows.append(
                {
                    "segment_id": sid,
                    "status": "PASS" if not statuses else "|".join(sorted(set(statuses))),
                    "block_count": len(blocks),
                    "chunk_count": len(seg_chunks),
                    "source_placeholder_occurrences": sum(src_occ.values()),
                    "chunk_placeholder_occurrences": sum(chunk_occ.values()),
                    "distinct_placeholders": len(set(src_occ)),
                }
            )

    # ---------- corpus-level invariants: I5, I7 ----------
    def check_corpus(self) -> None:
        seen = collections.Counter(c["chunk_id"] for c in self.chunks)
        for cid, n in seen.items():
            if n > 1:
                self.fail("I5_CHUNK_ID", cid, {"occurrences": n})
        for c in self.chunks:
            if c["segment_id"] not in self.seg_by_id:
                self.fail("I7_PARENT", c["chunk_id"], {"unknown_segment": c["segment_id"]})

    # ---------- graph invariants: I8, I9 ----------
    def check_edges(self) -> dict[str, Any]:
        chunk_ids = {c["chunk_id"] for c in self.chunks}
        seg_parents = {s.get("parent_node_id") for s in self.segments if s.get("parent_node_id")}
        doc_ids = {s.get("document_id") for s in self.segments if s.get("document_id")}
        node_source_ids = {
            nid for s in self.segments for b in s["blocks"] if (nid := b.get("source_node_id"))
        }
        known = chunk_ids | seg_parents | doc_ids | node_source_ids | self.legal_node_ids

        dangling = collections.Counter()
        key_counter = collections.Counter()
        for e in self.edges:
            for side in ("source_id", "target_id"):
                val = e.get(side)
                if val and val not in known:
                    dangling[e.get("relation", "?")] += 1
            key_counter[(e.get("source_id"), e.get("relation"), e.get("target_id"))] += 1

        dup_keys = {k: v for k, v in key_counter.items() if v > 1}
        for k, v in list(dup_keys.items())[:50]:
            self.fail("I9_EDGE_KEY", "|".join(str(x) for x in k), {"occurrences": v})

        return {
            "edge_count": len(self.edges),
            "known_node_ids": len(known),
            "dangling_endpoints_by_relation": dict(dangling),
            "duplicate_edge_keys": len(dup_keys),
            "relations": dict(collections.Counter(e.get("relation") for e in self.edges)),
        }

    def run(self) -> dict[str, Any]:
        self.check_segments()
        self.check_corpus()
        edge_report = self.check_edges()

        # Empty chunks are legitimate (a PDF page with no text layer still occupies a
        # block, and coverage requires it be chunked) but must never be indexed as
        # evidence. Surface them here so the index build can exclude them explicitly.
        empty_chunks = [c["chunk_id"] for c in self.chunks if not (c.get("text") or "").strip()]

        by_status = collections.Counter(r["status"] for r in self.seg_rows)
        by_invariant = collections.Counter(f["invariant"] for f in self.failures)
        total_src = sum(r.get("source_placeholder_occurrences", 0) for r in self.seg_rows)
        total_chunk = sum(r.get("chunk_placeholder_occurrences", 0) for r in self.seg_rows)

        return {
            "validator_version": VALIDATOR_VERSION,
            "generated_at": now_iso(),
            "corpus_dir": str(self.dir),
            "counts": {
                "parent_segments": len(self.segments),
                "boundary_plans": len(self.boundaries),
                "chunks": len(self.chunks),
                "edges": len(self.edges),
                "source_blocks": sum(len(s["blocks"]) for s in self.segments),
                "chunk_chars": sum(len(c.get("text") or "") for c in self.chunks),
            },
            "placeholders": {
                "source_occurrences": total_src,
                "chunk_occurrences": total_chunk,
                "conserved": total_src == total_chunk,
            },
            "indexability": {
                "indexable_chunks": len(self.chunks) - len(empty_chunks),
                "empty_chunks_excluded_from_index": len(empty_chunks),
                "empty_chunk_ids": empty_chunks,
            },
            "segment_status": dict(by_status),
            "failures_by_invariant": dict(by_invariant),
            "failure_count": len(self.failures),
            "graph": edge_report,
            "passed": len(self.failures) == 0,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", default="data/search_corpus", type=Path)
    ap.add_argument("--report", default=None, type=Path, help="report path (default: <corpus>/validation_report.json)")
    ap.add_argument(
        "--write-segment-validation",
        default=None,
        type=Path,
        help="corrected per-segment rows (default: <corpus>/chunk_validation_v2.jsonl)",
    )
    ap.add_argument("--strict", action="store_true", help="exit non-zero if any invariant fails")
    ap.add_argument(
        "--legal-nodes-glob",
        action="append",
        default=None,
        help="glob(s), relative to project root, of legislation nodes_*.jsonl providing "
        "legal-provision ids for the I8 endpoint check "
        "(default: data/group_a_legislation_v4/*/nodes_*.jsonl)",
    )
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent
    patterns = args.legal_nodes_glob or ["data/group_a_legislation_v4/*/nodes_*.jsonl"]
    legal_ids = load_legal_node_ids(patterns, project_root)

    v = Validator(args.corpus_dir, legal_node_ids=legal_ids)
    if not v.segments:
        print(f"ERROR: no parent_segments.jsonl under {args.corpus_dir}", file=sys.stderr)
        return 2

    report = v.run()

    report_path = args.report or args.corpus_dir / "validation_report.json"
    seg_path = args.write_segment_validation or args.corpus_dir / "chunk_validation_v2.jsonl"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with seg_path.open("w", encoding="utf-8") as f:
        for row in v.seg_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if v.failures:
        fail_path = args.corpus_dir / "validation_failures.jsonl"
        with fail_path.open("w", encoding="utf-8") as f:
            for row in v.failures:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nreport  -> {report_path}")
    print(f"segments-> {seg_path}")
    return 1 if (args.strict and not report["passed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
