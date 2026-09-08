#!/usr/bin/env python3
"""Export the chunks labelled GOOD, grouped by source type, with their spans.

The failure catalogue showed what goes wrong. This shows what a working retrieval unit looks
like in each lane, which is the more useful reference when redesigning segmentation: the
target is not an abstraction, it is these.

Each sample carries the full text, provenance, and where available the block span the
chunker chose, since the span analysis found that GOOD chunks span their whole segment 26.1%
of the time against 9.8% for INCOMPLETE - so the shape of a good chunk is part of what makes
it good.
"""
from __future__ import annotations

import argparse, collections, json, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="state/chunk_index_merged.sqlite3", type=Path)
    ap.add_argument("--labels", default="evaluation/chunk_quality_llm/labels.jsonl", type=Path)
    ap.add_argument("--per-group", type=int, default=5)
    ap.add_argument("--chars", type=int, default=5000)
    ap.add_argument("--out", default="evaluation/good_chunks_by_source", type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = root / a.out; out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / a.db); con.row_factory = sqlite3.Row

    segs, plans = {}, {}
    for f in ["data/search_corpus_merged/parent_segments.jsonl",
              "data/search_corpus_full/parent_segments.jsonl",
              "data/search_corpus_v2/parent_segments.jsonl"]:
        p = root / f
        if p.exists():
            for l in p.open(encoding="utf-8"):
                s = json.loads(l); segs.setdefault(s["segment_id"], s)
    for f in ["data/search_corpus_full/chunk_boundaries.jsonl",
              "data/search_corpus_v2/chunk_boundaries.jsonl"]:
        p = root / f
        if p.exists():
            for l in p.open(encoding="utf-8"):
                r = json.loads(l); plans.setdefault(r["segment_id"], r)

    labs = [json.loads(l) for l in (root / a.labels).open(encoding="utf-8") if l.strip()]
    good = [x for x in labs if x["label"] == "GOOD"]
    meta = {r["chunk_id"]: dict(r) for r in con.execute("SELECT * FROM chunks")}
    edges = collections.Counter()
    for r in con.execute("SELECT COALESCE(retrieval_source_id,source_id) s FROM edges "
                         "WHERE relation IN ('REFERENCES','CROSS_REFERS_TO')"):
        edges[r[0]] += 1

    def span_of(m):
        s = segs.get(m.get("segment_id")); p = plans.get(m.get("segment_id"))
        if not s or not p: return None
        idx = {b["block_id"]: i for i, b in enumerate(s["blocks"])}
        cs = p.get("plan", {}).get("chunks", [])
        o = m.get("chunk_ordinal")
        if not cs or not o or o > len(cs): return None
        c = cs[o - 1]
        st, en = idx.get(c.get("start_block_id")), idx.get(c.get("end_block_id"))
        if st is None or en is None: return None
        n = len(s["blocks"])
        return {"start_block": st, "end_block": en, "blocks_in_segment": n,
                "blocks_used": en - st + 1, "spans_whole_segment": st == 0 and en == n - 1}

    groups = collections.defaultdict(list)
    for x in good:
        groups[x["domain"]].append(x)

    index = []
    for dom, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        samples = []
        for x in items[: a.per_group]:
            m = meta.get(x["chunk_id"], {})
            t = m.get("text") or ""
            samples.append({
                "why_good": x["reason"],
                "chunk_id": x["chunk_id"], "citation": m.get("citation"),
                "retrieval_title": m.get("retrieval_title"),
                "retrieval_summary": m.get("retrieval_summary"),
                "authority_class": m.get("authority_class"),
                "legal_regime": m.get("legal_regime"), "jurisdiction": m.get("jurisdiction"),
                "source_kind": m.get("source_kind"), "source_url": m.get("source_url"),
                "est_tokens": m.get("est_tokens"), "char_count": m.get("char_count"),
                "has_legal_identity": bool(m.get("parent_node_id")),
                "parent_node_id": m.get("parent_node_id") or None,
                "outbound_legal_edges": edges.get(x["chunk_id"], 0),
                "chunk_span": span_of(m),
                "text_truncated_for_display": len(t) > a.chars,
                "text": t[: a.chars],
            })
        band = collections.Counter(x["band"] for x in items)
        payload = {"domain": dom, "generated_at": datetime.now(timezone.utc).isoformat(),
                   "good_chunks_in_sample": len(items),
                   "token_bands": dict(band.most_common()),
                   "examples": samples}
        f = out / f"good_{dom.replace('.', '_')}.json"
        f.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        index.append({"domain": dom, "file": f.name, "good": len(items)})
        print(f"  {dom[:40]:40s} GOOD={len(items):3d}  bands={dict(band.most_common(3))}")

    (out / "index.json").write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(), "domains": index}, indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
