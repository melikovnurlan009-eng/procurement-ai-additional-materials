#!/usr/bin/env python3
"""Edge-level semantics and hub structure of the legal graph.

Why not component-level: 99.8% of graph nodes fall in one component, so "within-component
coherence" degenerates into "any two nodes in the corpus" and cannot discriminate. The
meaningful unit is the EDGE - does a citation connect topically related provisions?

Tests
-----
1. EDGE COHERENCE. Jaccard overlap of topics+legal_concepts across each edge, against a
   random-pair baseline drawn from the same node population. Lift > 1 means citations carry
   topical signal; lift ~1 means they are structurally real but semantically uninformative.
2. HUB STRUCTURE. Degree distribution and what the hubs ARE. A hub that is a definitions or
   interpretation provision is cited by everything, so traversing into it injects generic
   material - a retrieval hazard rather than a benefit.
3. REACHABILITY. Whether each edge endpoint is retrievable, split by direction, since
   densification repaired targets but not sources.
4. AUTHORITY FLOW. Which authority classes cite which - does guidance point at legislation?
"""
from __future__ import annotations

import argparse, collections, json, random, sqlite3, statistics
from datetime import datetime, timezone
from pathlib import Path

LEGAL_RELATIONS = ("CROSS_REFERS_TO", "REFERENCES")
DEFINITIONAL_HINT = ("interpretation", "definition", "citation", "commencement",
                     "general", "meaning", "application", "extent")


def jac(a, b): return len(a & b) / len(a | b) if a and b else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="state/chunk_index_merged.sqlite3", type=Path)
    ap.add_argument("--out", default="evaluation/graph_analysis", type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = root / a.out; out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / a.db); con.row_factory = sqlite3.Row

    ident = {}
    for r in con.execute("SELECT chunk_id,parent_node_id,document_id,citation,authority_class,"
                         "retrieval_title,topics,legal_concepts FROM chunks"):
        ident.setdefault(r["parent_node_id"] or r["document_id"], []).append(dict(r))

    def vocab(n):
        acc = set()
        for c in ident.get(n, []):
            for f in ("topics", "legal_concepts"):
                try: acc |= {t.lower().strip() for t in json.loads(c[f] or "[]")}
                except Exception: pass
        return acc

    def title(n):
        cs = ident.get(n, [])
        return (cs[0]["retrieval_title"] or cs[0]["citation"] or "") if cs else ""

    ph = ",".join("?" * len(LEGAL_RELATIONS))
    edges = [dict(r) for r in con.execute(
        f"SELECT source_id, COALESCE(retrieval_target_id,target_id) AS tgt, relation, confidence,"
        f" retrieval_resolution FROM edges WHERE relation IN ({ph})", LEGAL_RELATIONS)]

    # ---- 1. edge coherence ------------------------------------------------------
    per_rel = collections.defaultdict(list)
    scored = 0
    for e in edges:
        va, vb = vocab(e["source_id"]), vocab(e["tgt"])
        if va and vb:
            per_rel[e["relation"]].append(jac(va, vb)); scored += 1
    pop = [n for n in ident if vocab(n)]
    random.seed(13)
    base = [jac(vocab(x), vocab(y)) for x, y in
            (random.sample(pop, 2) for _ in range(4000)) ] if len(pop) > 2 else [0]
    bmean = statistics.mean(base)

    coherence = {"random_pair_baseline": round(bmean, 4), "edges_scored": scored,
                 "by_relation": {}}
    for rel, vals in per_rel.items():
        coherence["by_relation"][rel] = {
            "n": len(vals), "mean_jaccard": round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "zero_overlap_pct": round(100 * sum(1 for v in vals if v == 0) / len(vals), 1),
            "lift_over_chance": round(statistics.mean(vals) / bmean, 2) if bmean else None}

    # ---- 2. hubs ----------------------------------------------------------------
    deg = collections.Counter()
    for e in edges:
        deg[e["source_id"]] += 1; deg[e["tgt"]] += 1
    hubs = []
    for n, d in deg.most_common(12):
        t = title(n).lower()
        hubs.append({"node": n, "degree": d, "title": title(n)[:64] or None,
                     "looks_definitional": any(k in t for k in DEFINITIONAL_HINT),
                     "retrievable": bool(ident.get(n))})
    topdeg = [d for _, d in deg.most_common(int(0.01 * len(deg)) or 1)]
    hub_share = round(100 * sum(topdeg) / sum(deg.values()), 1)

    # ---- 3. reachability by direction ------------------------------------------
    src_ok = sum(1 for e in edges if e["source_id"] in ident)
    tgt_ok = sum(1 for e in edges if e["tgt"] in ident)
    both = sum(1 for e in edges if e["source_id"] in ident and e["tgt"] in ident)

    # ---- 4. authority flow -----------------------------------------------------
    def auth(n):
        cs = ident.get(n, [])
        return cs[0]["authority_class"] if cs else "NOT_IN_CORPUS"
    flow = collections.Counter((auth(e["source_id"]), auth(e["tgt"])) for e in edges)

    rep = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge_coherence": coherence,
        "hubs": {"top": hubs, "definitional_in_top12": sum(1 for h in hubs if h["looks_definitional"]),
                 "share_of_all_edge_endpoints_held_by_top_1pct_nodes": hub_share,
                 "degree_mean": round(statistics.mean(deg.values()), 2),
                 "degree_median": statistics.median(deg.values()),
                 "degree_p99": sorted(deg.values())[int(0.99 * len(deg))]},
        "reachability": {"edges": len(edges), "source_retrievable": src_ok,
                         "target_retrievable": tgt_ok, "both_retrievable": both,
                         "both_pct": round(100 * both / len(edges), 1),
                         "source_unreachable": len(edges) - src_ok},
        "authority_flow_top": [{"from": k[0], "to": k[1], "n": v} for k, v in flow.most_common(10)],
    }
    (out / "graph_edges.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
