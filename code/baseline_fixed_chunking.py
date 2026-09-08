#!/usr/bin/env python3
"""Fixed-size chunking baseline, to test the claim that LLM boundaries are better.

The corpus is built by an LLM choosing boundaries over immutable blocks. The structural
detectors report 93.4% clean, but that number is unanchored: it only means something against
an alternative. This builds the obvious alternative over the SAME parent segments and the
SAME blocks, so the only variable is who chooses the boundary.

Two deterministic strategies:

  fixed_tokens   accumulate blocks until a token budget is reached, then cut. The standard
                 naive baseline. Blocks stay whole, so this is already generous - a character
                 splitter that cuts mid-block would score far worse.
  block_window   fixed number of blocks per chunk, ignoring size entirely.

Both are scored with the identical Tier 1 detectors used on the production corpus, so the
comparison is like for like.
"""
from __future__ import annotations

import argparse, collections, json, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_chunk_quality import assess_chunk, est_tokens


def build(segments, strategy: str, budget: int):
    out = []
    for s in segments:
        blocks = s["blocks"]
        cur, cur_tok = [], 0
        groups = []
        for b in blocks:
            t = est_tokens(b.get("text") or "")
            if strategy == "fixed_tokens":
                if cur and cur_tok + t > budget:
                    groups.append(cur); cur, cur_tok = [], 0
            else:
                if cur and len(cur) >= budget:
                    groups.append(cur); cur, cur_tok = [], 0
            cur.append(b); cur_tok += t
        if cur: groups.append(cur)
        for i, g in enumerate(groups, 1):
            text = "\n\n".join(x.get("text") or "" for x in g)
            out.append({"chunk_id": f"{s['segment_id']}__FX_{i:03d}", "text": text,
                        "retrieval_title": s.get("heading") or s.get("citation") or "",
                        "retrieval_summary": "", "est_tokens": est_tokens(text)})
    return out


def evaluate(chunks):
    counts = collections.Counter()
    clean = 0
    for i, c in enumerate(chunks):
        nxt = chunks[i + 1] if i + 1 < len(chunks) else None
        d = assess_chunk(c, nxt).get("defects", [])
        for x in d: counts[x] += 1
        if not d: clean += 1
    toks = [c["est_tokens"] for c in chunks]
    return {"chunks": len(chunks), "clean": clean,
            "clean_pct": round(100 * clean / len(chunks), 1),
            "defects": sum(counts.values()),
            "defects_per_chunk": round(sum(counts.values()) / len(chunks), 3),
            "by_detector": dict(counts.most_common()),
            "median_tokens": statistics.median(toks),
            "mean_tokens": round(statistics.mean(toks), 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default="data/search_corpus_v2/parent_segments.jsonl", type=Path)
    ap.add_argument("--llm-chunks", default="data/search_corpus_v2/chunks.jsonl", type=Path)
    ap.add_argument("--out", default="evaluation/chunking_baseline", type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = root / a.out; out.mkdir(parents=True, exist_ok=True)

    segs = [json.loads(l) for l in (root / a.segments).open(encoding="utf-8") if l.strip()]
    llm = [json.loads(l) for l in (root / a.llm_chunks).open(encoding="utf-8") if l.strip()]
    for c in llm: c.setdefault("est_tokens", est_tokens(c.get("text") or ""))

    results = {"llm_semantic (production)": evaluate(llm)}
    for label, strat, budget in (("fixed_tokens_400", "fixed_tokens", 400),
                                 ("fixed_tokens_800", "fixed_tokens", 800),
                                 ("block_window_5", "block_window", 5),
                                 ("block_window_10", "block_window", 10)):
        results[label] = evaluate(build(segs, strat, budget))

    (out / "chunking_baseline.json").write_text(json.dumps(
        {"segments": len(segs), "results": results}, indent=2), encoding="utf-8")

    hdr = f"{'strategy':26s} {'chunks':>7s} {'clean%':>7s} {'defects':>8s} {'per chunk':>10s} {'med tok':>8s}"
    print(f"segments: {len(segs)}\n"); print(hdr); print("-" * len(hdr))
    for k, v in results.items():
        print(f"{k:26s} {v['chunks']:7d} {v['clean_pct']:7.1f} {v['defects']:8d} "
              f"{v['defects_per_chunk']:10.3f} {v['median_tokens']:8.0f}")
    print(f"\n{'detector':24s}", "".join(f"{k[:14]:>16s}" for k in results))
    keys = sorted({d for v in results.values() for d in v["by_detector"]})
    for d in keys:
        print(f"{d:24s}", "".join(f"{v['by_detector'].get(d,0):16d}" for v in results.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
