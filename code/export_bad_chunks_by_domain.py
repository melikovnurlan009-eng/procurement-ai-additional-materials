#!/usr/bin/env python3
"""Export the chunks the LLM labelled INCOMPLETE or LOW_VALUE, grouped by source domain.

The labelling run (900 chunks, gpt-4.1, temperature 0) found only 21% usable as retrieval
units. This pulls the failures out with their full text, the model's reason, and every
mechanical defect flag, so each domain's characteristic failure can be read rather than
inferred from a percentage.

Domains fail differently, which is why grouping matters:
  assets.publishing.service.gov.uk   3% GOOD, 85% INCOMPLETE - PDF spans with no boundaries
  procurementpathway.civilservice    57% LOW_VALUE            - advice-footer boilerplate
  procurementjourney.scot            29% LOW_VALUE            - print-PDF chrome
  legislation.gov.uk                 51% GOOD                 - the control case

Each file also carries the domain's GOOD examples for contrast, since a failure catalogue
without a baseline invites the conclusion that everything is broken.
"""
from __future__ import annotations

import argparse, collections, json, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path

NLSP = re.compile(r"\w\n \n\w")
NLWORD = re.compile(r"\w\n\w")
CHROME = re.compile(r"(open or close|back to top|view pdf|skip to)", re.I)
BOILER = re.compile(r"(seek legal and commercial advice|additional support and guidance)", re.I)
APPLIES = re.compile(r"^\s*\d*\s*\n*\s*1?\s*This (section|regulation|Part|Chapter)\s+applies", re.I)


def defects(t: str) -> dict:
    words = len(re.findall(r"\w+", t or "")) or 1
    return {
        "word_newline_corruption": round(len(NLSP.findall(t or "")) / words, 3),
        "line_per_word_corruption": round(len(NLWORD.findall(t or "")) / words, 3),
        "ui_chrome": bool(CHROME.search(t or "")),
        "advice_boilerplate": bool(BOILER.search(t or "")),
        "opens_with_applicability_clause": bool(APPLIES.search((t or "")[:160])),
        "starts_mid_sentence": bool(t and t.strip()[:1].islower()),
        "ends_mid_sentence": bool(t and not t.rstrip().endswith((".", "!", "?", ":", ";", '"', ")"))),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="state/chunk_index_merged.sqlite3", type=Path)
    ap.add_argument("--labels", default="evaluation/chunk_quality_llm/labels.jsonl", type=Path)
    ap.add_argument("--per-label", type=int, default=6, help="bad examples per label per domain")
    ap.add_argument("--good", type=int, default=2, help="GOOD examples per domain for contrast")
    ap.add_argument("--chars", type=int, default=4000)
    ap.add_argument("--out", default="evaluation/bad_chunks_by_domain", type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = root / a.out; out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / a.db); con.row_factory = sqlite3.Row

    labs = [json.loads(l) for l in (root / a.labels).open(encoding="utf-8") if l.strip()]
    meta = {r["chunk_id"]: dict(r) for r in con.execute(
        "SELECT chunk_id,citation,retrieval_title,retrieval_summary,authority_class,"
        "legal_regime,jurisdiction,source_kind,parent_node_id,est_tokens,char_count,"
        "source_url,text FROM chunks")}
    edges = collections.Counter()
    for r in con.execute("SELECT COALESCE(retrieval_source_id,source_id) s FROM edges "
                         "WHERE relation IN ('REFERENCES','CROSS_REFERS_TO')"):
        edges[r[0]] += 1

    by_dom = collections.defaultdict(list)
    for x in labs:
        by_dom[x["domain"]].append(x)

    index = []
    for dom, items in sorted(by_dom.items(), key=lambda kv: -len(kv[1])):
        if len(items) < 10:
            continue
        counts = collections.Counter(x["label"] for x in items)
        n = len(items)

        def pack(x):
            m = meta.get(x["chunk_id"], {})
            t = m.get("text") or ""
            return {
                "label": x["label"], "reason": x["reason"],
                "chunk_id": x["chunk_id"], "citation": m.get("citation"),
                "retrieval_title": m.get("retrieval_title"),
                "retrieval_summary": m.get("retrieval_summary"),
                "authority_class": m.get("authority_class"),
                "legal_regime": m.get("legal_regime"), "jurisdiction": m.get("jurisdiction"),
                "source_kind": m.get("source_kind"), "source_url": m.get("source_url"),
                "est_tokens": m.get("est_tokens"), "char_count": m.get("char_count"),
                "has_legal_identity": bool(m.get("parent_node_id")),
                "outbound_legal_edges": edges.get(x["chunk_id"], 0),
                "mechanical_defects": defects(t),
                "text_truncated_for_display": len(t) > a.chars,
                "text": t[: a.chars],
            }

        sel = {}
        for lab, k in (("LOW_VALUE", a.per_label), ("INCOMPLETE", a.per_label), ("GOOD", a.good)):
            sel[lab] = [pack(x) for x in items if x["label"] == lab][:k]

        # Which mechanical defect dominates this domain's failures?
        bad = [x for x in items if x["label"] != "GOOD"]
        dflag = collections.Counter()
        for x in bad:
            d = defects((meta.get(x["chunk_id"], {}).get("text") or ""))
            for k, v in d.items():
                if v is True or (isinstance(v, float) and v > 0.3):
                    dflag[k] += 1

        payload = {
            "domain": dom, "generated_at": datetime.now(timezone.utc).isoformat(),
            "labelled_sample": n,
            "distribution": {k: f"{counts.get(k,0)} ({100*counts.get(k,0)/n:.0f}%)"
                             for k in ("GOOD", "INCOMPLETE", "LOW_VALUE")},
            "dominant_mechanical_defects_among_failures": dict(dflag.most_common()),
            "common_reasons": dict(collections.Counter(
                x["reason"][:60] for x in bad).most_common(6)),
            "examples": sel,
        }
        f = out / f"bad_{dom.replace('.', '_')}.json"
        f.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        index.append({"domain": dom, "file": f.name, "labelled": n,
                      **{k: counts.get(k, 0) for k in ("GOOD", "INCOMPLETE", "LOW_VALUE")}})
        print(f"  {dom[:38]:38s} n={n:4d}  GOOD {counts.get('GOOD',0):3d}  "
              f"INCOMPLETE {counts.get('INCOMPLETE',0):3d}  LOW_VALUE {counts.get('LOW_VALUE',0):3d}"
              f"  -> {f.name}")

    (out / "index.json").write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(), "domains": index}, indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
