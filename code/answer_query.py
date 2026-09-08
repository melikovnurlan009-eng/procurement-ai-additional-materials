#!/usr/bin/env python3
"""Cited answer generation over the retrieved evidence bundle.

Closes the pipeline: query -> hybrid + graph retrieval -> authority reranking ->
evidence bundle -> answer with citations traceable to provisions and URLs.

Constraints this implements (they are correctness requirements, not style choices)
----------------------------------------------------------------------------------
* Only the exact source `text` of retrieved chunks is supplied as evidence. The
  LLM-generated `retrieval_summary` and `topics` are retrieval metadata and are withheld
  from the generator, so a model-written gloss can never be cited as if it were law.
* Every substantive sentence must carry a marker [E1], [E2], ... identifying the evidence
  item it rests on. Unsupported statements are not permitted.
* The regime the answer applies to is stated explicitly, because the same question has
  different answers under PA2023 and PCR2015.
* Where the evidence does not answer the question, the model must say so rather than
  reason from general knowledge.

Post-generation verification (deterministic, not a second opinion from the model)
---------------------------------------------------------------------------------
The answer is checked in code for: citation markers that reference no supplied evidence
item; evidence items never cited; the proportion of sentences carrying a citation; and
whether any quoted span actually occurs in the cited chunk. These become the
citation-correctness metrics the evaluation needs, and they are reported with the answer
rather than assumed.

Usage
-----
    .venv-embed/bin/python answer_query.py "When can a supplier be excluded for bid rigging?"
    .venv-embed/bin/python answer_query.py "..." --json --top-k 8
"""
from __future__ import annotations

import argparse
import json
import os
import re
import textwrap
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ANSWER_VERSION = "1.0.0"
PROMPT_VERSION = "cited_answer_v1"

SYSTEM_PROMPT = """You answer UK public procurement law questions for professionals, using ONLY the numbered evidence supplied.

FORMAT REQUIREMENT, applied to every sentence you write in `answer`:
end the sentence with the marker(s) of the evidence item(s) it rests on, before the full stop.

    Correct:   A contracting authority must exclude a supplier that is an excluded supplier [E3].
    Correct:   The authority must first notify the supplier [E2][E5].
    Incorrect: A contracting authority must exclude a supplier that is an excluded supplier.

An answer containing no [E...] markers is invalid and will be rejected.

Rules:
1. Every substantive sentence must end with one or more citation markers, e.g. [E1] or [E2][E5].
2. Use ONLY the supplied evidence. If it does not answer the question, say so plainly and state what is missing. Never fall back on general knowledge.
3. Quote sparingly and exactly. Any quoted phrase must appear verbatim in the evidence item you cite.
4. Prefer legislation over guidance when they address the same point, and say when guidance is only explaining a provision.
5. State which legal regime the answer applies to (Procurement Act 2023, Procurement Regulations 2024, or the legacy Public Contracts Regulations 2015). If the evidence mixes regimes, say which parts apply to which.
6. Be concise: a direct answer first, then the conditions, exceptions and procedural steps that qualify it.

Return JSON only."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "regime": {"type": "string"},
        "evidence_used": {"type": "array", "items": {"type": "string"}},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["statement", "evidence_ids"],
                "additionalProperties": False,
            },
        },
        "unanswered_aspects": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string"},
    },
    "required": ["answer", "regime", "evidence_used", "claims", "unanswered_aspects", "confidence"],
    "additionalProperties": False,
}

MARKER_RE = re.compile(r"\[E(\d+)\]")
SENTENCE_RE = re.compile(r"[^.!?]+[.!?]")
QUOTE_RE = re.compile(r"[\"“]([^\"”]{12,})[\"”]")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_evidence(results: list[dict[str, Any]], max_chars: int, lane: str | None = None) -> list[dict[str, Any]]:
    """Evidence items carry exact source text and provenance only."""
    items = []
    for i, r in enumerate(results, 1):
        text = (r.get("text") or "").strip()
        if not text:
            continue
        items.append({
            "id": f"E{i}",
            "citation": r.get("citation") or r.get("document_id"),
            "authority_class": r.get("authority_class"),
            "legal_regime": r.get("legal_regime"),
            "source_url": r.get("source_url"),
            "chunk_id": r.get("chunk_id"),
            "via_graph_only": r.get("via_graph_only"),
            "lane": lane,
            "text": text[:max_chars],
        })
    return items


def build_evidence_two_lanes(legislation: list[dict[str, Any]], other: list[dict[str, Any]],
                              max_chars: int) -> list[dict[str, Any]]:
    """Legislation first, then everything else - so the answer generator sees binding
    law before explanatory material and, if asked to lead with the statute, already
    has it at the front of the evidence list rather than needing to search for it."""
    items = build_evidence(legislation, max_chars, lane="legislation")
    other_items = build_evidence(other, max_chars, lane="other")
    for i, it in enumerate(other_items, len(items) + 1):
        it["id"] = f"E{i}"
    return items + other_items


STOPWORDS = {
    "the","a","an","and","or","of","to","in","for","on","with","by","is","are","be","as","at","that",
    "this","it","from","its","which","may","must","shall","not","any","all","such","under","where",
    "if","when","has","have","was","were","will","can","should","would","there","their","they","been",
    "applies","apply","ground","grounds","supplier","contracting","authority","procurement","act",
}


def content_terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z\-]{3,}", (text or "").lower()) if w not in STOPWORDS}


def check_claim_grounding(claims: list[dict[str, Any]], items: list[dict[str, Any]],
                          threshold: float = 0.45) -> dict[str, Any]:
    """Is each declared claim actually supported by the evidence item it cites?

    Citation markers are decoration unless the cited text supports the statement. This
    was demonstrated on this corpus: a model asked for mandatory exclusion grounds
    produced the Schedule 6 list from prior knowledge and attached [E1]..[E6] to sections
    about dynamic markets and direct award. Marker coverage was 1.0, every marker was
    valid, no quote was fabricated - and every claim was ungrounded.

    The test is lexical rather than semantic on purpose: it must be deterministic,
    explainable and independent of any model. It measures the fraction of a claim's
    content terms that occur in the cited evidence, which catches wholesale invention
    without pretending to adjudicate fine points of interpretation.
    """
    by_id = {it["id"]: content_terms(it["text"]) for it in items}
    rows = []
    for c in claims or []:
        terms = content_terms(c.get("statement", ""))
        cited = [e for e in (c.get("evidence_ids") or []) if e in by_id]
        best, best_id = 0.0, None
        for e in cited:
            overlap = len(terms & by_id[e]) / len(terms) if terms else 0.0
            if overlap > best:
                best, best_id = overlap, e
        rows.append({
            "statement": c.get("statement", "")[:140],
            "evidence_ids": c.get("evidence_ids"),
            "best_support": best_id,
            "term_overlap": round(best, 3),
            "grounded": best >= threshold,
        })
    grounded = sum(1 for r in rows if r["grounded"])
    return {
        "claims": len(rows),
        "grounded_claims": grounded,
        "ungrounded_claims": len(rows) - grounded,
        "grounding_rate": round(grounded / len(rows), 3) if rows else None,
        "threshold": threshold,
        "detail": rows,
    }


def verify(answer: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic citation checks. No model judgement involved."""
    valid_ids = {it["id"] for it in items}
    cited = {f"E{n}" for n in MARKER_RE.findall(answer)}
    sentences = [s.strip() for s in SENTENCE_RE.findall(answer) if len(s.strip()) > 25]
    with_marker = [s for s in sentences if MARKER_RE.search(s)]

    by_id = {it["id"]: it["text"].lower() for it in items}
    bad_quotes = []
    for m in QUOTE_RE.finditer(answer):
        quote = m.group(1).strip().lower()
        tail = answer[m.end(): m.end() + 40]
        targets = [f"E{n}" for n in MARKER_RE.findall(tail)] or sorted(cited)
        if targets and not any(quote in by_id.get(t, "") for t in targets):
            bad_quotes.append(quote[:70])

    return {
        "evidence_supplied": len(items),
        "evidence_cited": len(cited & valid_ids),
        "unused_evidence": sorted(valid_ids - cited),
        "invalid_citations": sorted(cited - valid_ids),
        "sentences": len(sentences),
        "sentences_with_citation": len(with_marker),
        "citation_coverage": round(len(with_marker) / len(sentences), 3) if sentences else None,
        "unverifiable_quotes": bad_quotes,
        # An answer with no citations at all is the worst case, not a pass. An earlier
        # revision checked only for INVALID citations and for quote fidelity, so a
        # completely uncited answer satisfied every condition vacuously. Coverage is
        # therefore part of the pass criterion, not a statistic reported beside it.
        # Two verdicts, deliberately separate. Marker coverage is a FORMATTING property:
        # an answer whose every claim is grounded but which omits a marker on one linking
        # sentence has not fabricated anything. Measured on 45 practitioner queries, 5 of 9
        # failures were coverage-only and their mean grounding was 0.950 - reporting a single
        # combined verdict made the system look four times less reliable than it is.
        "format_pass": (len(with_marker) / len(sentences) if sentences else 0) >= 0.8,
        "citations_valid": not (cited - valid_ids) and not bad_quotes and bool(cited & valid_ids),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--db", default="state/chunk_index_merged.sqlite3", type=Path)
    ap.add_argument("--collection", default="chunks__bge_m3__merged")
    ap.add_argument("--model", default=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--max-evidence-chars", type=int, default=4000)
    ap.add_argument("--no-graph", action="store_true")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    from chunk_retrieval import ChunkRetriever

    db = args.db if args.db.is_absolute() else root / args.db
    retriever = ChunkRetriever(db, args.collection)
    legislation, other, trace = retriever.search_two_lanes(
        args.query, top_k_legislation=args.top_k, top_k_other=args.top_k,
        use_graph=not args.no_graph,
    )
    items = build_evidence_two_lanes(legislation, other, args.max_evidence_chars)
    if not items:
        print("No evidence retrieved.")
        return 1

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set")
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    payload = {
        "question": args.query,
        "evidence": [
            {k: v for k, v in it.items() if k in
             ("id", "citation", "authority_class", "legal_regime", "lane", "text")}
            for it in items
        ],
    }
    resp = client.chat.completions.create(
        model=args.model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "cited_answer", "schema": ANSWER_SCHEMA, "strict": True}},
        temperature=0,
    )
    out = json.loads(resp.choices[0].message.content)
    checks = verify(out["answer"], items)
    grounding = check_claim_grounding(out.get("claims") or [], items)
    # A citation that does not support its claim is worse than no citation, so grounding
    # gates the overall verdict alongside the marker checks.
    checks["claim_grounding"] = grounding
    # The substantive verdict: is every claim supported by the evidence it cites?
    checks["substantive_pass"] = bool(checks["citations_valid"]) and (
        grounding.get("grounding_rate") or 0) >= 0.6
    # Overall remains the conjunction, so a strict caller is unaffected, but the two
    # components are now reported separately and can be scored independently.
    checks["passed"] = bool(checks["substantive_pass"]) and bool(checks["format_pass"])

    record = {
        "answer_version": ANSWER_VERSION,
        "prompt_version": PROMPT_VERSION,
        "generated_at": now_iso(),
        "model": args.model,
        "query": args.query,
        "regime": out.get("regime"),
        "answer": out.get("answer"),
        "claims": out.get("claims"),
        "unanswered_aspects": out.get("unanswered_aspects"),
        "confidence": out.get("confidence"),
        "citation_checks": checks,
        "evidence": [{k: v for k, v in it.items() if k != "text"} for it in items],
        "retrieval_config": trace.config,
    }

    if args.json:
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0

    print(f"\nQUESTION: {args.query}")
    print(f"REGIME:   {out.get('regime')}")
    print("-" * 96)
    print(textwrap.fill(out["answer"], 96, replace_whitespace=False))
    if out.get("unanswered_aspects"):
        print("\nNOT ANSWERED BY THE EVIDENCE:")
        for u in out["unanswered_aspects"]:
            print(f"  - {u}")
    print("\nEVIDENCE")
    for it in items:
        tag = " [via graph]" if it["via_graph_only"] else ""
        print(f"  {it['id']}  [{it['authority_class']}{'/' + it['legal_regime'] if it['legal_regime'] else ''}]{tag}")
        print(f"      {it['citation']}")
        if it["source_url"]:
            print(f"      {it['source_url']}")
    print("\nCITATION CHECKS")
    for k, v in checks.items():
        if k == "claim_grounding":
            continue
        print(f"  {k}: {v}")
    g = checks["claim_grounding"]
    print(f"  claim_grounding: {g['grounded_claims']}/{g['claims']} grounded "
          f"(rate {g['grounding_rate']}, threshold {g['threshold']})")
    for r in g["detail"]:
        mark = "ok " if r["grounded"] else "UNGROUNDED"
        print(f"    [{mark}] {r['evidence_ids']} overlap={r['term_overlap']}  {r['statement'][:70]}")
    return 0 if checks["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
