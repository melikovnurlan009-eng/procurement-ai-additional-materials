#!/usr/bin/env python3
"""Layout-aware PDF extraction: recover structure instead of emitting page rectangles.

The problem this replaces
-------------------------
The existing PDF path emits one `page_text` block per page and nothing else. Measured on the
corpus that lane produced 88% INCOMPLETE chunks - the worst of any source - because the
chunker's smallest possible unit was a whole page, and page edges fall wherever the layout
designer put them: mid-sentence, mid-list, mid-table. With no headings or list markers there
were also no seams to choose between, so cuts landed by token budget rather than by meaning.
PDFs are 30.7% of the corpus by chunks and 50.5% by characters, so this lane dominates the
corpus's text even though it is a minority of its units.

What this does instead
----------------------
PyMuPDF exposes each span's font size, weight and position, which is enough to recover the
structure the page was laid out from:

  headings     spans notably larger than the document's body size, or bold and short
  list items   lines opening with a bullet, a lettered or numbered marker
  paragraphs   everything else, with lines joined
  furniture    running headers and footers, detected as text repeating at the same vertical
               position across many pages, then dropped

Two joins matter and both are done here rather than left to the chunker:

  * a paragraph broken by a page break is rejoined, because the sentence continues
  * a hyphenated word split across lines is repaired

Segmentation
------------
`--segment page` keeps one segment per page, as requested. `--segment heading` starts a new
segment at each detected heading, which is what the HTML lane effectively does and what the
evidence favours: page boundaries are a property of the layout, not of the argument, so a
segment that ends at a page edge inherits the same defect this extractor exists to remove.
Both are provided; the default is heading, and page is available for comparison.

Nothing is ingested. Output is staged for inspection.
"""
from __future__ import annotations

import argparse, collections, json, re, statistics, sys
from datetime import datetime, timezone
from pathlib import Path

BULLET = re.compile(r"^\s*([•●▪‣⁃\-–]|\(?[a-z]\)|\(?[ivxlc]+\)|\d+[\.\)])\s+", re.I)
HYPHEN_BREAK = re.compile(r"(\w)-\s*$")
SENT_END = (".", "!", "?", ":", ";", '"', "”", ")", "]")


def spans_of(page):
    out = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:
            continue
        for line in blk["lines"]:
            txt = "".join(s["text"] for s in line["spans"]).strip()
            if not txt:
                continue
            sizes = [s["size"] for s in line["spans"]]
            bold = any(s["flags"] & 2 ** 4 for s in line["spans"])
            out.append({"text": txt, "size": round(max(sizes), 1), "bold": bold,
                        "y": round(line["bbox"][1], 1), "x": round(line["bbox"][0], 1)})
    return out


def find_furniture(pages: list[list[dict]], min_share: float = 0.5) -> set[str]:
    """Running headers and footers: the same text at the same height on many pages."""
    n = len(pages)
    if n < 4:
        return set()
    seen = collections.Counter()
    for lines in pages:
        if not lines:
            continue
        ys = [l["y"] for l in lines]
        top, bot = min(ys), max(ys)
        for l in lines:
            if l["y"] <= top + 2 or l["y"] >= bot - 2:
                seen[re.sub(r"\d+", "#", l["text"])[:80]] += 1
    return {k for k, v in seen.items() if v >= max(3, int(min_share * n))}


def extract(path: Path, segment_mode: str) -> dict:
    import fitz
    doc = fitz.open(path)
    pages = [spans_of(doc[i]) for i in range(len(doc))]
    furniture = find_furniture(pages)
    body = statistics.median([l["size"] for p in pages for l in p] or [10.0])

    blocks, page_of = [], []
    for pno, lines in enumerate(pages, 1):
        for l in lines:
            key = re.sub(r"\d+", "#", l["text"])[:80]
            if key in furniture:
                continue
            if len(l["text"]) < 2:
                continue
            if l["size"] >= body * 1.35 or (l["bold"] and len(l["text"]) < 90):
                lvl = 2 if l["size"] >= body * 1.8 else 3 if l["size"] >= body * 1.35 else 4
                kind = f"h{lvl}"
            elif BULLET.match(l["text"]):
                kind = "li"
            else:
                kind = "p"
            blocks.append({"block_type": kind, "text": l["text"], "page": pno,
                           "size": l["size"], "bold": l["bold"]})

    # Join wrapped lines within a paragraph, across page breaks where the sentence runs on.
    merged: list[dict] = []
    for b in blocks:
        if (merged and b["block_type"] == "p" and merged[-1]["block_type"] == "p"
                and not merged[-1]["text"].rstrip().endswith(SENT_END)):
            prev = merged[-1]
            if HYPHEN_BREAK.search(prev["text"]):
                prev["text"] = HYPHEN_BREAK.sub(r"\1", prev["text"].rstrip()) + b["text"].lstrip()
            else:
                prev["text"] = prev["text"].rstrip() + " " + b["text"].lstrip()
            prev["page_end"] = b["page"]
            continue
        merged.append(dict(b))
    for i, b in enumerate(merged, 1):
        b["block_id"] = f"B{i:04d}"

    segs, cur = [], []
    def flush():
        if cur:
            segs.append({"blocks": [dict(x) for x in cur],
                         "heading": next((x["text"] for x in cur if x["block_type"].startswith("h")), None),
                         "pages": sorted({x["page"] for x in cur})})
            cur.clear()
    if segment_mode == "page":
        last = None
        for b in merged:
            if last is not None and b["page"] != last:
                flush()
            cur.append(b); last = b["page"]
        flush()
    else:
        for b in merged:
            if b["block_type"].startswith("h") and cur:
                flush()
            cur.append(b)
        flush()

    bt = collections.Counter(b["block_type"] for b in merged)
    return {"file": path.name, "pages": len(doc), "body_font_size": body,
            "furniture_lines_dropped": len(furniture),
            "blocks": len(merged), "block_types": dict(bt),
            "segments": len(segs), "segment_mode": segment_mode,
            "chars": sum(len(b["text"]) for b in merged),
            "segments_detail": segs}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+", type=Path)
    ap.add_argument("--segment", choices=["heading", "page"], default="heading")
    ap.add_argument("--out", default="data/pdf_restructured", type=Path)
    a = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = root / a.out; out.mkdir(parents=True, exist_ok=True)
    for p in a.pdf:
        rec = extract(p, a.segment)
        (out / f"{p.stem}.{a.segment}.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{p.name}")
        print(f"   pages {rec['pages']}  blocks {rec['blocks']}  segments {rec['segments']}  "
              f"chars {rec['chars']:,}")
        print(f"   block types: {rec['block_types']}")
        print(f"   running header/footer lines dropped: {rec['furniture_lines_dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
