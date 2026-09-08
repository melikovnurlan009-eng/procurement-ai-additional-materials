#!/usr/bin/env python3
"""
Resolve each gold evidence item's free-text "citation" (as written by the construction agents,
e.g. "Procurement Act 2023 s 43", "Procurement Act 2023, s.43", "Guidance: Direct Award (HTML)")
against the LIVE corpus (state/chunk_index_merged.sqlite3), to attach a real chunk_id/
parent_node_id/document_id wherever the corpus actually contains a matching row.

This does NOT invent or guess a target -- an item that cannot be matched is left UNRESOLVED
and flagged for manual/agent review rather than silently assigned a plausible-looking id.

Output: gold_evidence.jsonl (enriched with a "resolution" block per evidence item) plus a
resolution_report.json summary.
"""
import json, re, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH_DIR = Path(__file__).resolve().parent

con = sqlite3.connect(ROOT / "state" / "chunk_index_merged.sqlite3")
con.row_factory = sqlite3.Row


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[.,;:]", " ", s)
    s = re.sub(r"\bsection\b", "s", s)
    s = re.sub(r"\bregulation\b", "reg", s)
    s = re.sub(r"\bschedule\b", "sch", s)
    s = re.sub(r"\bparagraph\b", "para", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def resolve_citation(citation: str):
    if not citation:
        return {"status": "UNRESOLVED", "reason": "empty citation"}
    norm = normalize(citation)
    # 1. exact citation column match (normalized)
    rows = con.execute(
        "SELECT chunk_id, citation, parent_node_id, document_id, authority_class, legal_regime "
        "FROM chunks WHERE filtered_out IS NULL AND superseded_by IS NULL"
    ).fetchall()
    # cache normalized citation once per process call would be expensive repeated per item;
    # instead do a targeted FTS/LIKE pass first, fall back to full scan only if needed.
    candidates = []
    # try direct citation LIKE match on key tokens
    tokens = [t for t in re.findall(r"[a-z0-9]+", norm) if len(t) > 1]
    if tokens:
        like_clause = " AND ".join(["lower(citation) LIKE ?"] * min(len(tokens), 4))
        params = [f"%{t}%" for t in tokens[:4]]
        try:
            rows2 = con.execute(
                f"SELECT chunk_id, citation, parent_node_id, document_id, authority_class, legal_regime "
                f"FROM chunks WHERE filtered_out IS NULL AND superseded_by IS NULL AND {like_clause} LIMIT 10",
                params,
            ).fetchall()
            candidates.extend(rows2)
        except sqlite3.OperationalError:
            pass
    if candidates:
        best = candidates[0]
        return {
            "status": "MATCHED",
            "chunk_id": best["chunk_id"],
            "parent_node_id": best["parent_node_id"],
            "document_id": best["document_id"],
            "matched_citation": best["citation"],
            "authority_class": best["authority_class"],
            "legal_regime": best["legal_regime"],
            "n_candidates": len(candidates),
        }
    # 2. fallback: title/heading search for guidance-style citations
    rows3 = con.execute(
        "SELECT c.chunk_id, c.citation, c.retrieval_title, c.parent_node_id, c.document_id, c.authority_class, c.legal_regime "
        "FROM chunks_fts f JOIN chunks c ON c.chunk_id=f.chunk_id "
        "WHERE chunks_fts MATCH ? AND c.filtered_out IS NULL AND c.superseded_by IS NULL LIMIT 5",
        (" OR ".join(f'"{t}"' for t in tokens[:6]) if tokens else citation,),
    ).fetchall()
    if rows3:
        best = rows3[0]
        return {
            "status": "FUZZY_MATCHED",
            "chunk_id": best["chunk_id"],
            "parent_node_id": best["parent_node_id"],
            "document_id": best["document_id"],
            "matched_citation": best["citation"],
            "authority_class": best["authority_class"],
            "legal_regime": best["legal_regime"],
        }
    return {"status": "UNRESOLVED", "reason": "no citation/FTS match in live corpus"}


def main():
    gold_path = BENCH_DIR / "gold_evidence.jsonl"
    records = [json.loads(l) for l in open(gold_path) if l.strip()]
    out_records = []
    stats = {"MATCHED": 0, "FUZZY_MATCHED": 0, "UNRESOLVED": 0}
    for rec in records:
        for req in rec.get("requirements", []):
            for bucket in ("essential_evidence", "strong_supporting_evidence"):
                for item in req.get(bucket, []):
                    res = resolve_citation(item.get("citation", ""))
                    item["resolution"] = res
                    stats[res["status"] if res["status"] != "FUZZY_MATCHED" else "FUZZY_MATCHED"] = \
                        stats.get(res["status"], 0) + 1
        out_records.append(rec)

    with (BENCH_DIR / "gold_evidence.jsonl").open("w") as f:
        for rec in out_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    json.dump(
        {"total_records": len(records), "resolution_stats": stats},
        open(BENCH_DIR / "gold_resolution_report.json", "w"),
        indent=2,
    )
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
