#!/usr/bin/env python3
"""
Verifies that the fully-deterministic legislation-chunking lane reproduces the shipped,
evaluated corpus's chunk text exactly, from a fresh scrape today.

Scope: only PA2023 and PR2024 use this lane (chunking_method STRUCTURAL_NODE_V1) -- a
structural XML tree walk with no LLM involved anywhere. Everything else in the corpus uses
an LLM step (boundary selection or direct text emission) and is not expected to reproduce
byte-for-byte on rerun; see README.md's "What is and is not exactly reproducible".

This scrapes live legislation.gov.uk content, so a provision inserted or removed by an
amendment since the corpus was built will show up as a difference below -- that is expected,
not a bug in this script or the chunker (see the same README section).

Usage (from the bundle root, after `pip install requests lxml` -- see code/requirements.txt):
    python3 scripts/verify_deterministic_chunking.py --source PA2023
    python3 scripts/verify_deterministic_chunking.py --source PR2024
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
CORPUS_CHUNKS = CODE_DIR / "corpus_export" / "data" / "chunks.jsonl"

DOC_IDS = {"PA2023": "UKPGA_2023_54", "PR2024": "UKSI_2024_692"}

NORM = lambda t: re.sub(r"\s+", " ", (t or "").strip().lower())
HASH = lambda t: hashlib.sha1(NORM(t).encode()).hexdigest()


def run(cmd, cwd):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"command failed: {' '.join(str(c) for c in cmd)}")
    return result.stdout


def load_jsonl(p):
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=sorted(DOC_IDS), required=True)
    args = ap.parse_args()
    doc_id = DOC_IDS[args.source]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        print(f"=== Stage 1/2: fresh scrape of {args.source} (live legislation.gov.uk) ===")
        run([sys.executable, "scrapers/legislation/group_a_legislation_scraper_v4.py",
             "--source", args.source, "--output-dir", str(tmp / "scraped")], cwd=CODE_DIR)

        nodes_path = tmp / "scraped" / args.source.lower() / "nodes.jsonl"
        if not nodes_path.exists():
            raise SystemExit(f"expected scraper output not found: {nodes_path}")

        print("\n=== Stage 2/2: deterministic structural chunking (no LLM) ===")
        chunks_out = tmp / "fresh_chunks.json"
        run([sys.executable, "chunk_legislation_from_nodes.py",
             "--doc", doc_id, "--nodes", str(nodes_path), "--out", str(chunks_out)], cwd=CODE_DIR)

        fresh = {d["parent_node_id"]: d for d in json.load(open(chunks_out, encoding="utf-8"))}

    shipped = {d["parent_node_id"]: d for d in load_jsonl(CORPUS_CHUNKS)
               if d.get("document_id") == doc_id and d.get("chunking_method") == "STRUCTURAL_NODE_V1"}

    common = set(shipped) & set(fresh)
    only_shipped = sorted(set(shipped) - set(fresh))
    only_fresh = sorted(set(fresh) - set(shipped))

    text_match = sum(1 for p in common if shipped[p]["text"] == fresh[p]["text"])
    hash_match = sum(1 for p in common if HASH(fresh[p]["text"]) == shipped[p].get("content_sha256"))

    print(f"\nShipped (live, evaluated) chunks for {doc_id}: {len(shipped)}")
    print(f"Freshly scraped+chunked today:                 {len(fresh)}")
    print(f"Matched by provision identity:                 {len(common)}")
    print(f"  exact text match:                             {text_match}/{len(common)}")
    print(f"  exact content_sha256 match:                   {hash_match}/{len(common)}")

    if only_shipped:
        print(f"\nIn the shipped corpus but not in today's scrape ({len(only_shipped)}): {only_shipped}")
        print("  Most likely: a provision inserted by an amendment since the corpus was built --")
        print("  legislation.gov.uk content is live and can change; this is expected, not a bug.")
    if only_fresh:
        print(f"\nIn today's scrape but not in the shipped corpus ({len(only_fresh)}): {only_fresh}")
        print("  Most likely: filtered out at ingestion for a disclosed reason, or a naming-scheme")
        print("  difference for a provision inserted since the original scrape.")

    if common and text_match == len(common) and hash_match == len(common):
        print("\nPASS: every provision both runs agree exists matches the shipped corpus exactly")
        print("(text and content hash). Residual differences above, if any, reflect live legislative")
        print("content that has changed since the corpus was built, not a reproducibility failure.")
    else:
        print("\nMismatch found in the common set -- inspect the differences above before concluding")
        print("this doesn't match.")


if __name__ == "__main__":
    main()
