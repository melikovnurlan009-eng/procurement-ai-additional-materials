#!/usr/bin/env python3
"""Extract and resolve legal citations made by guidance and commentary chunks.

Why this layer exists
---------------------
The graph had 6,489 CONTAINS, 4,763 CROSS_REFERS_TO (legislation to legislation) and
only 4 REFERENCES edges - so guidance was effectively disconnected from the law it
explains. Measured on the corpus, non-legislation chunks make 1,019 statutory citations
across 34 documents, none of which were edges.

That gap has a concrete retrieval cost. The Procurement Act never uses the phrase "bid
rigging" (0 chunks); it says "cartel" (9 chunks). A user asking about bid rigging can
only reach the operative provisions through guidance that cites them - which requires
these edges to exist.

The precision problem, and how it is handled
--------------------------------------------
"section 43" is the single most cited locator in the corpus (70 times) - and in ICO
guidance it means section 43 of the Freedom of Information Act, NOT section 43 of the
Procurement Act. Attaching those to PA2023 would fabricate authoritative-looking edges
between unrelated statutes.

Resolution therefore requires POSITIVE evidence of which instrument is meant:

  EXPLICIT   the instrument is named next to the citation ("section 57 of the
             Procurement Act 2023", "PA 2023 s 57")           -> confidence 0.90
  DOC_REGIME the citing document is itself unambiguously about one regime
             (legal_regime set on the chunk)                   -> confidence 0.70
  otherwise  no edge; retained as an unresolved candidate.

A document naming a foreign instrument anywhere near the citation (FOIA, GDPR,
Competition Act...) is refused outright, even when the document's regime is set.

Usage
-----
    python extract_guidance_references.py --corpus-dir data/search_corpus
    python extract_guidance_references.py --corpus-dir data/search_corpus --dry-run
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXTRACTOR_VERSION = "1.0.0"

CITATION_RE = re.compile(
    r"\b(?P<unit>sections?|schedules?|regulations?|paragraphs?)\s+"
    r"(?P<locator>\d+[A-Za-z]?(?:\s*\(\s*[0-9a-z]+\s*\))*)",
    re.I,
)

REGIME_TO_DOC = {"PA2023": "UKPGA_2023_54", "PR2024": "UKSI_2024_692", "PCR2015": "UKSI_2015_102"}

NAMED_INSTRUMENT = [
    (re.compile(r"\b(procurement act 2023|PA\s?2023|the 2023 Act)\b", re.I), "UKPGA_2023_54"),
    (re.compile(r"\b(procurement regulations 2024|PR\s?2024|the 2024 Regulations)\b", re.I), "UKSI_2024_692"),
    (re.compile(r"\b(public contracts regulations 2015|PCR\s?2015|the 2015 Regulations)\b", re.I), "UKSI_2015_102"),
]

# Instruments outside the corpus that share locator space with procurement law. Their
# presence near a citation is disqualifying: FOIA s.43 is not PA2023 s.43.
FOREIGN_INSTRUMENT = re.compile(
    r"\b(freedom of information act|FOIA|data protection act|DPA\s?2018|UK\s?GDPR|"
    r"environmental information regulations|EIR|competition act 1998|enterprise act|"
    r"equality act|human rights act|companies act|insolvency act|employment rights act|"
    r"defence and security public contracts|utilities contracts regulations|"
    r"concession contracts regulations|health care services|social value act)\b",
    re.I,
)

UNIT_NORMAL = {"section": "section", "sections": "section", "schedule": "schedule",
               "schedules": "schedule", "regulation": "regulation", "regulations": "regulation",
               "paragraph": "paragraph", "paragraphs": "paragraph"}

UNIT_FOR_DOC = {"UKPGA_2023_54": "section", "UKSI_2024_692": "regulation", "UKSI_2015_102": "regulation"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def split_locator(locator: str) -> list[str]:
    locator = re.sub(r"\s+", "", locator or "")
    head = re.match(r"^(\d+[A-Za-z]?)", locator)
    parts = [head.group(1)] if head else []
    parts += re.findall(r"\(([^)]+)\)", locator)
    return parts


def load_nodes(root: Path) -> set[str]:
    nodes: set[str] = set()
    for path in sorted((root / "data" / "group_a_legislation_v4").glob("*/nodes_*.jsonl")):
        for row in read_jsonl(path):
            if row.get("node_id"):
                nodes.add(row["node_id"])
    return nodes


def resolve_target(doc_id: str, unit: str, locator: str, nodes: set[str]) -> tuple[str | None, str]:
    parts = split_locator(locator)
    if not parts:
        return None, "NO_LOCATOR"
    # "paragraph N" in guidance usually refers to a schedule paragraph; without the
    # schedule number it is not safely resolvable, so it is left alone.
    if unit == "paragraph":
        return None, "PARAGRAPH_WITHOUT_SCHEDULE"
    if unit == "section" and doc_id.startswith("UKSI"):
        unit = "regulation"
    if unit == "regulation" and doc_id.startswith("UKPGA"):
        unit = "section"
    exact = f"{doc_id}__{unit}-" + "-".join(parts)
    if exact in nodes:
        return exact, "EXACT"
    for depth in range(len(parts) - 1, 0, -1):
        anc = f"{doc_id}__{unit}-" + "-".join(parts[:depth])
        if anc in nodes:
            return anc, "ANCESTOR"
    return None, "ABSENT"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", default="data/search_corpus", type=Path)
    ap.add_argument("--context", type=int, default=160, help="context window each side of a citation")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    corpus_dir = args.corpus_dir if args.corpus_dir.is_absolute() else root / args.corpus_dir
    nodes = load_nodes(root)
    chunks = read_jsonl(corpus_dir / "chunks.jsonl")

    # Document-level instrument inference: which single in-corpus instrument does each
    # document discuss? Computed over the whole document, and abandoned if the document
    # also discusses a foreign instrument or more than one in-corpus instrument.
    doc_text: dict[str, list[str]] = collections.defaultdict(list)
    for c in chunks:
        if c.get("source_kind") != "LEGISLATION":
            doc_text[c.get("document_id")].append(
                f"{c.get('citation') or ''} {c.get('retrieval_title') or ''} {c.get('text') or ''}"
            )
    document_instrument: dict[str, str | None] = {}
    for doc_id, parts in doc_text.items():
        blob = " ".join(parts)
        found = {d for pattern, d in NAMED_INSTRUMENT if pattern.search(blob)}
        document_instrument[doc_id] = found.pop() if len(found) == 1 else None

    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    seen_keys: set[tuple] = set()
    stats = collections.Counter()

    for chunk in chunks:
        if chunk.get("source_kind") == "LEGISLATION":
            continue
        text = chunk.get("text") or ""
        if not text:
            continue
        doc_regime = chunk.get("legal_regime")
        doc_instrument = document_instrument.get(chunk.get("document_id"))
        for m in CITATION_RE.finditer(text):
            stats["citations_found"] += 1
            unit = UNIT_NORMAL.get(m.group("unit").lower(), "section")
            locator = m.group("locator")
            lo = max(0, m.start() - args.context)
            hi = min(len(text), m.end() + args.context)
            context = text[lo:hi]

            target_doc, basis, confidence = None, None, 0.0
            for pattern, doc_id in NAMED_INSTRUMENT:
                if pattern.search(context):
                    target_doc, basis, confidence = doc_id, "EXPLICIT_INSTRUMENT", 0.90
                    break

            if FOREIGN_INSTRUMENT.search(context):
                # A foreign statute is named nearby: refuse regardless of document regime.
                stats["refused_foreign_instrument"] += 1
                unresolved.append({
                    "source_chunk_id": chunk["chunk_id"], "unit": unit, "locator": locator,
                    "status": "FOREIGN_INSTRUMENT_CONTEXT", "matched_text": m.group(0),
                    "context": context.strip()[:220],
                })
                continue

            if target_doc is None and doc_regime in REGIME_TO_DOC:
                target_doc, basis, confidence = REGIME_TO_DOC[doc_regime], "DOCUMENT_REGIME", 0.70

            if target_doc is None and doc_instrument:
                # The document as a whole names exactly one in-corpus instrument and no
                # foreign one. Weaker evidence than a citation-adjacent mention, so it
                # scores lower - but far better than dropping guidance that is plainly
                # about one statute yet cites its sections in shorthand.
                target_doc, basis, confidence = doc_instrument, "DOCUMENT_INSTRUMENT_MENTION", 0.65

            if target_doc is None:
                stats["unresolved_no_instrument"] += 1
                unresolved.append({
                    "source_chunk_id": chunk["chunk_id"], "unit": unit, "locator": locator,
                    "status": "INSTRUMENT_UNKNOWN", "matched_text": m.group(0),
                    "context": context.strip()[:220],
                })
                continue

            target, how = resolve_target(target_doc, unit, locator, nodes)
            if not target:
                stats[f"unresolved_{how.lower()}"] += 1
                unresolved.append({
                    "source_chunk_id": chunk["chunk_id"], "unit": unit, "locator": locator,
                    "status": how, "target_document_id": target_doc,
                    "matched_text": m.group(0), "context": context.strip()[:220],
                })
                continue

            key = (chunk["chunk_id"], "REFERENCES", target)
            if key in seen_keys:
                stats["duplicate_suppressed"] += 1
                continue
            seen_keys.add(key)
            conf = confidence * (1.0 if how == "EXACT" else 0.85)
            edges.append({
                "edge_id": f"G{len(edges) + 1:06d}",
                "source_id": chunk["chunk_id"],
                "relation": "REFERENCES",
                "target_id": target,
                "evidence_method": "GUIDANCE_CITATION_REGEX",
                "evidence_text": m.group(0),
                "resolution_status": f"GUIDANCE_{how}",
                "resolution_basis": basis,
                "confidence": round(conf, 2),
                "target_document_id": target_doc,
                "extractor_version": EXTRACTOR_VERSION,
            })
            stats[f"edge_{basis.lower()}_{how.lower()}"] += 1

    report = {
        "extractor_version": EXTRACTOR_VERSION,
        "generated_at": now_iso(),
        "chunks_scanned": sum(1 for c in chunks if c.get("source_kind") != "LEGISLATION"),
        "edges_created": len(edges),
        "unresolved": len(unresolved),
        "counts": dict(stats.most_common()),
        "edges_by_target_document": dict(
            collections.Counter(e["target_document_id"] for e in edges).most_common()
        ),
        "edges_by_basis": dict(collections.Counter(e["resolution_basis"] for e in edges).most_common()),
        "confidence_distribution": dict(collections.Counter(str(e["confidence"]) for e in edges).most_common()),
    }

    if not args.dry_run:
        with (corpus_dir / "edges_guidance_refs.jsonl").open("w", encoding="utf-8") as f:
            for e in edges:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        with (corpus_dir / "unresolved_guidance_refs.jsonl").open("w", encoding="utf-8") as f:
            for u in unresolved:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")
        (corpus_dir / "guidance_reference_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
