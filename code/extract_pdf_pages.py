#!/usr/bin/env python3
"""Plain per-page PDF text extraction, handed to the chunker as-is.

Rationale
---------
An earlier version of this tried to infer document structure from font sizes and emit typed
blocks. That recovers real headings and lists, but it is heuristic: thresholds that suit one
document drop content in another, and a dropped line is unrecoverable downstream. Extraction
should be lossless; deciding what the text means is the chunker's job, and the chunker is a
language model that can read.

So this takes every piece of text on each page, in reading order, and nothing else. The only
transformations are ones that repair the extractor's own artifacts rather than judge content:

  * lines joined into paragraphs on blank-line boundaries, preserving order
  * hyphenated words split across lines rejoined
  * a paragraph continuing across a page break marked, so the chunker can see the join
  * whitespace normalised - the existing corpus carries three distinct PDF corruptions,
    including one where every word is separated by a newline

Running headers and footers are recorded but NOT removed, for the same reason: identifying
them is a judgement, and a false positive silently deletes body text. They are flagged so the
chunker can disregard them.

Output is one record per PDF, with a `pages` array. Nothing is ingested.
"""
from __future__ import annotations

import argparse, collections, json, re
from datetime import datetime, timezone
from pathlib import Path

HYPHEN = re.compile(r"(\w)-\s*$")
WS = re.compile(r"[ \t\xa0]+")
SENT_END = (".", "!", "?", ":", ";", '"', "”", ")", "]")


def page_text(page) -> list[str]:
    """Every text line on the page, in reading order, grouped into paragraphs."""
    paras, cur = [], []
    for blk in sorted(page.get_text("dict")["blocks"], key=lambda b: (b["bbox"][1], b["bbox"][0])):
        if blk.get("type") != 0:
            continue
        for line in blk["lines"]:
            t = WS.sub(" ", "".join(s["text"] for s in line["spans"])).strip()
            if not t:
                continue
            if cur and HYPHEN.search(cur[-1]):
                cur[-1] = HYPHEN.sub(r"\1", cur[-1].rstrip()) + t
            else:
                cur.append(t)
        if cur:
            paras.append(" ".join(cur)); cur = []
    if cur:
        paras.append(" ".join(cur))
    return paras


def extract(path: Path) -> dict:
    import fitz
    doc = fitz.open(path)
    pages = []
    for i in range(len(doc)):
        paras = page_text(doc[i])
        pages.append({"page": i + 1, "paragraphs": paras,
                      "chars": sum(len(p) for p in paras)})

    # Repeated first/last paragraphs are probably running headers or footers. Flagged only.
    edge = collections.Counter()
    for p in pages:
        for t in ([p["paragraphs"][0]] if p["paragraphs"] else []) + \
                 ([p["paragraphs"][-1]] if len(p["paragraphs"]) > 1 else []):
            edge[re.sub(r"\d+", "#", t)[:80]] += 1
    furniture = {k for k, v in edge.items() if v >= max(3, int(0.5 * len(pages)))}
    for p in pages:
        p["likely_furniture"] = [t for t in p["paragraphs"]
                                 if re.sub(r"\d+", "#", t)[:80] in furniture]
        p["continues_from_previous"] = False
    for i in range(1, len(pages)):
        prev = pages[i - 1]["paragraphs"]
        if prev and not prev[-1].rstrip().endswith(SENT_END) and pages[i]["paragraphs"]:
            pages[i]["continues_from_previous"] = True

    return {"file": path.name, "extracted_at": datetime.now(timezone.utc).isoformat(),
            "extractor": "pymupdf-plain-page-text",
            "pages": len(doc),
            "paragraphs": sum(len(p["paragraphs"]) for p in pages),
            "chars": sum(p["chars"] for p in pages),
            "furniture_patterns_flagged": len(furniture),
            "pages_continuing_a_sentence": sum(1 for p in pages if p["continues_from_previous"]),
            "page_data": pages}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+", type=Path)
    ap.add_argument("--out", default="data/pdf_pages", type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = root / a.out; out.mkdir(parents=True, exist_ok=True)
    for p in a.pdf:
        rec = extract(p)
        (out / f"{p.stem}.pages.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{p.name}: {rec['pages']} pages, {rec['paragraphs']} paragraphs, "
              f"{rec['chars']:,} chars, {rec['pages_continuing_a_sentence']} pages continue a sentence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
