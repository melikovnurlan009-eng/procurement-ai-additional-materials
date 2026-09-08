#!/usr/bin/env python3
"""Structural and semantic analysis of the legal knowledge graph.

Answers, with measurements rather than assertion:
  1. What is the connected structure of the legal graph?
  2. Do connected components correspond to MEANINGFUL legal relationships, or are they
     artefacts of citation density?
  3. Which nodes are hubs, and are they hubs for legal or structural reasons?

Method
------
Nodes are legal identities (provision node ids and document ids), not chunks, because a
citation points at a provision. Edges are the two LEGAL relations only - CROSS_REFERS_TO and
REFERENCES - traversed on `retrieval_target_id` (the densified, chunk-reachable target).
HAS_CHUNK and CONTAINS are excluded: they are structural, so including them would merge the
whole corpus into one component and tell us nothing about legal connectivity.

Component semantics are tested by topic coherence: for every component, the Jaccard overlap
of the `topics` and `legal_concepts` assigned to its member chunks. A component whose members
share vocabulary is a real legal cluster; one whose members share nothing is a citation
artefact. A random-pairs baseline is computed so coherence can be read against chance.

Usage
-----
    python analyze_graph.py --db state/chunk_index_merged.sqlite3
"""
from __future__ import annotations

import argparse, collections, json, random, sqlite3, statistics
from datetime import datetime, timezone
from pathlib import Path

TOOL_VERSION = "1.0.0"
LEGAL_RELATIONS = ("CROSS_REFERS_TO", "REFERENCES")
STRUCTURAL_RELATIONS = ("HAS_CHUNK", "CONTAINS")


class DSU:
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[ra] = rb


def jaccard(a: set, b: set) -> float:
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="state/chunk_index_merged.sqlite3", type=Path)
    ap.add_argument("--out", default="evaluation/graph_analysis", type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = root / args.out; out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / args.db if not args.db.is_absolute() else args.db)
    con.row_factory = sqlite3.Row

    # ---- node vocabulary: what a chunk's legal identity is -----------------------
    chunk_rows = con.execute(
        "SELECT chunk_id, parent_node_id, document_id, citation, authority_class, "
        "legal_regime, topics, legal_concepts FROM chunks").fetchall()
    ident = {}          # legal identity -> list of chunks
    for r in chunk_rows:
        key = r["parent_node_id"] or r["document_id"]
        ident.setdefault(key, []).append(dict(r))

    rel_ph = ",".join("?" * len(LEGAL_RELATIONS))
    edges = con.execute(
        f"SELECT source_id, COALESCE(retrieval_target_id, target_id) AS tgt, relation, "
        f"confidence FROM edges WHERE relation IN ({rel_ph})", LEGAL_RELATIONS).fetchall()

    # ---- components over legal edges only ---------------------------------------
    dsu = DSU(); deg = collections.Counter(); kept = 0
    adj = collections.defaultdict(set)
    for e in edges:
        s, t = e["source_id"], e["tgt"]
        if s is None or t is None or s == t: continue
        kept += 1
        dsu.union(s, t); deg[s] += 1; deg[t] += 1
        adj[s].add(t); adj[t].add(s)

    comps = collections.defaultdict(list)
    for n in list(deg): comps[dsu.find(n)].append(n)
    sizes = sorted((len(v) for v in comps.values()), reverse=True)

    # ---- do components mean anything? topic coherence vs chance -----------------
    def topics_of(node) -> set:
        acc = set()
        for c in ident.get(node, []):
            for f in ("topics", "legal_concepts"):
                try: acc |= {t.lower().strip() for t in json.loads(c[f] or "[]")}
                except Exception: pass
        return acc

    coherence = []
    for members in comps.values():
        if len(members) < 3: continue
        withv = [topics_of(m) for m in members]
        withv = [w for w in withv if w]
        if len(withv) < 2: continue
        pairs = [jaccard(withv[i], withv[j])
                 for i in range(len(withv)) for j in range(i + 1, len(withv))][:400]
        if pairs:
            coherence.append({"size": len(members), "mean_jaccard": statistics.mean(pairs)})

    random.seed(7)
    all_nodes = [n for n in deg if topics_of(n)]
    base = []
    for _ in range(2000):
        a, b = random.sample(all_nodes, 2) if len(all_nodes) > 2 else (None, None)
        if a: base.append(jaccard(topics_of(a), topics_of(b)))

    # ---- hubs -------------------------------------------------------------------
    hubs = []
    for n, d in deg.most_common(15):
        cs = ident.get(n, [])
        hubs.append({"node": n, "degree": d,
                     "citation": cs[0]["citation"] if cs else None,
                     "authority": cs[0]["authority_class"] if cs else None,
                     "chunks": len(cs), "retrievable": bool(cs)})

    struct_ph = ",".join("?" * len(STRUCTURAL_RELATIONS))
    struct_n = con.execute(
        f"SELECT count(*) FROM edges WHERE relation IN ({struct_ph})", STRUCTURAL_RELATIONS).fetchone()[0]

    giant = sizes[0] if sizes else 0
    report = {
        "tool_version": TOOL_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
        "legal_relations": list(LEGAL_RELATIONS),
        "edges": {"legal_total": len(edges), "used_after_selfloop_drop": kept,
                  "structural_excluded": struct_n},
        "nodes": {"in_legal_graph": len(deg), "distinct_legal_identities_in_corpus": len(ident),
                  "coverage_pct": round(100 * len(deg) / max(1, len(ident)), 1)},
        "components": {
            "count": len(comps),
            "giant_component_nodes": giant,
            "giant_share_of_graph_pct": round(100 * giant / max(1, len(deg)), 1),
            "size_distribution": {"top10": sizes[:10],
                                  "singleton_pairs_le2": sum(1 for s in sizes if s <= 2),
                                  "median": statistics.median(sizes) if sizes else 0},
        },
        "degree": {"mean": round(statistics.mean(deg.values()), 2) if deg else 0,
                   "median": statistics.median(deg.values()) if deg else 0,
                   "max": max(deg.values()) if deg else 0,
                   "nodes_degree_1": sum(1 for v in deg.values() if v == 1)},
        "semantic_coherence": {
            "components_scored": len(coherence),
            "mean_within_component_jaccard": round(statistics.mean(
                [c["mean_jaccard"] for c in coherence]), 4) if coherence else None,
            "random_pair_baseline_jaccard": round(statistics.mean(base), 4) if base else None,
            "lift_over_chance": round(statistics.mean([c["mean_jaccard"] for c in coherence])
                                      / statistics.mean(base), 2) if coherence and base and statistics.mean(base) else None,
        },
        "hubs": hubs,
    }
    (out / "graph_structure.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2)[:2600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
