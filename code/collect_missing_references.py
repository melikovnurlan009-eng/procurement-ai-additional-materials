#!/usr/bin/env python3
"""Collect every referenced target that is NOT in the corpus - the acquisition backlog.

Three reference sources are harvested and merged:

  1. Hyperlinks in the normalised HTML records (`links` per document).
  2. Structured and regex citations recorded by the reference resolver, whose status places
     them outside the corpus (TARGET_NOT_IN_CORPUS, EXTERNAL_INSTRUMENT_REFERENCE).
  3. `<ref href>` targets in the Akoma Ntoso XML, which carry legislation.gov.uk URIs.

A target counts as HELD if its legislation.gov.uk URL maps to a document identifier already
in the index (ukpga/2023/54 -> UKPGA_2023_54), or if its URL matches a `source_url` or
`canonical_url` already ingested. Everything else is missing.

Output is ranked by citation frequency, because how often a target is cited is the best
available proxy for how much its absence costs. Legislation is separated from guidance and
from non-legal links, since only the first can gain legal node identity.

Usage
-----
    python collect_missing_references.py
    python collect_missing_references.py --min-citations 2
"""
from __future__ import annotations

import argparse, collections, csv, glob, json, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path

LEG_RE = re.compile(
    r"legislation\.gov\.uk/(?P<type>ukpga|uksi|ukdsi|asp|asc|nisr|ssi|eur|eudr)/"
    r"(?P<year>\d{4})/(?P<num>[\w\-]+)", re.I)
SI_RE = re.compile(r"\b(S\.?S?\.?I\.?)\s*(\d{4})/(\d+)", re.I)
ACT_RE = re.compile(r"\b([A-Z][A-Za-z’'\-]+(?:\s+[A-Z(][A-Za-z’'\-)]+){0,6}\s+Act\s+(?:19|20)\d{2})")


def doc_id_from_url(u: str) -> str | None:
    m = LEG_RE.search(u or "")
    return f"{m.group('type').upper()}_{m.group('year')}_{m.group('num')}" if m else None


def domain(u: str) -> str:
    m = re.match(r"https?://([^/]+)", u or "")
    return m.group(1).lower() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="state/chunk_index_merged.sqlite3", type=Path)
    ap.add_argument("--records", default="normalized_html_json_v2/records", type=Path)
    ap.add_argument("--resolution", default="data/search_corpus/reference_resolution_all.jsonl", type=Path)
    ap.add_argument("--xml-dir", default="corpus_minor_formats/xml", type=Path)
    ap.add_argument("--out", default="evaluation/acquisition", type=Path)
    ap.add_argument("--min-citations", type=int, default=1)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = root / a.out; out.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(root / a.db)
    held_docs = {r[0] for r in con.execute("SELECT DISTINCT document_id FROM chunks")}
    held_urls = {(r[0] or "").split("#")[0].rstrip("/")
                 for r in con.execute("SELECT DISTINCT source_url FROM chunks")}
    # Instruments already parsed with legal identity.
    identified = {r[0].split("__")[0] for r in con.execute(
        "SELECT DISTINCT parent_node_id FROM chunks WHERE parent_node_id<>''")}

    refs: dict[str, dict] = {}

    def add(url: str, anchor: str, origin: str):
        url = (url or "").strip()
        if not url or url.startswith(("mailto:", "tel:", "#", "javascript:")):
            return
        key = url.split("#")[0].rstrip("/")
        r = refs.setdefault(key, {"url": key, "citations": 0, "anchors": set(),
                                  "origins": set(), "domain": domain(key)})
        r["citations"] += 1
        if anchor: r["anchors"].add(anchor.strip()[:90])
        r["origins"].add(origin)

    # 1. hyperlinks in normalised HTML records
    n_rec = 0
    for f in glob.glob(str(root / a.records / "*.json")):
        try: d = json.load(open(f, encoding="utf-8"))
        except Exception: continue
        n_rec += 1
        for l in (d.get("links") or []):
            if isinstance(l, dict):
                add(l.get("url") or l.get("href") or "", l.get("text") or l.get("anchor") or "", "html_link")
            elif isinstance(l, str):
                add(l, "", "html_link")

    # 2. Akoma Ntoso ref targets
    for f in glob.glob(str(root / a.xml_dir / "*.xml")):
        try: s = open(f, encoding="utf-8", errors="replace").read()
        except Exception: continue
        for u in re.findall(r'href="(https?://[^"]+)"', s):
            add(u, "", "akn_ref")

    # 3. resolver candidates that fell outside the corpus
    instruments = collections.Counter()
    res_path = root / a.resolution
    if res_path.exists():
        for line in res_path.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("status") not in ("TARGET_NOT_IN_CORPUS", "EXTERNAL_INSTRUMENT_REFERENCE"):
                continue
            ev = (r.get("evidence_text") or "").strip()
            if not ev: continue
            m = SI_RE.search(ev)
            if m:
                instruments[f"{m.group(1).upper().replace('.','')} {m.group(2)}/{m.group(3)}"] += 1
                continue
            m = ACT_RE.search(ev)
            if m:
                instruments[m.group(1)] += 1

    rows = []
    for r in refs.values():
        did = doc_id_from_url(r["url"])
        in_corpus = bool(
            (did and did in held_docs) or r["url"] in held_urls
            or any(r["url"].startswith(h) for h in held_urls if h))
        rows.append({
            "url": r["url"], "citations": r["citations"], "domain": r["domain"],
            "kind": ("legislation" if LEG_RE.search(r["url"])
                     else "gov_guidance" if r["domain"].endswith(("gov.uk", "gov.scot"))
                     else "external"),
            "derived_document_id": did or "",
            "has_legal_identity": bool(did and did in identified),
            "in_corpus": in_corpus,
            "anchor_examples": " | ".join(sorted(r["anchors"])[:3]),
            "origins": ",".join(sorted(r["origins"])),
        })
    missing = [r for r in rows if not r["in_corpus"] and r["citations"] >= a.min_citations]
    missing.sort(key=lambda r: (-r["citations"], r["url"]))

    with (out / "missing_references.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(missing[0])) if missing else None
        if w: w.writeheader(); w.writerows(missing)
    with (out / "missing_references.jsonl").open("w", encoding="utf-8") as f:
        for r in missing: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    inst = [{"instrument": k, "citations": v} for k, v in instruments.most_common()]
    with (out / "missing_instruments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["instrument", "citations"]); w.writeheader(); w.writerows(inst)

    by_kind = collections.Counter(r["kind"] for r in missing)
    by_dom = collections.Counter(r["domain"] for r in missing)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records_scanned": n_rec, "distinct_referenced_urls": len(rows),
        "already_in_corpus": sum(1 for r in rows if r["in_corpus"]),
        "missing": len(missing),
        "missing_by_kind": dict(by_kind),
        "missing_top_domains": dict(by_dom.most_common(12)),
        "named_instruments_not_held": len(inst),
        "outputs": ["missing_references.csv", "missing_references.jsonl", "missing_instruments.csv"],
    }
    (out / "acquisition_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("\nTOP MISSING LEGISLATION TARGETS")
    for r in [x for x in missing if x["kind"] == "legislation"][:12]:
        print(f"  {r['citations']:4d}  {r['derived_document_id'] or '-':22s} {r['url'][:74]}")
    print("\nTOP MISSING GUIDANCE TARGETS")
    for r in [x for x in missing if x["kind"] == "gov_guidance"][:10]:
        print(f"  {r['citations']:4d}  {r['url'][:88]}")
    print("\nNAMED INSTRUMENTS CITED BUT NOT HELD")
    for r in inst[:14]:
        print(f"  {r['citations']:4d}  {r['instrument']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
