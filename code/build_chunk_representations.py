#!/usr/bin/env python3
"""Build three retrieval representations per chunk: full text, sentences, and a summary.

Motivation
----------
Cosine similarity is scale-free: measured over the candidate pool it is essentially flat
across a twentyfold length range (0.629 at 2k+ tokens against 0.644 at 300-800). A long chunk
therefore keeps a respectable similarity while diluting whichever topic the query is about -
one vector has to stand for everything the chunk says.

Two alternatives to a single whole-text vector:

  sentences  embed each sentence separately and score the chunk by its BEST-matching
             sentence. A chunk that states five rules is then judged on the rule that
             matches, not on the average of five.
  summary    embed a one-line statement of what the chunk says. Shorter and more topical
             than the source, at the cost of losing the exact statutory wording that BM25
             and the citation both depend on.

Only 23% of active chunks carry a `retrieval_summary` - the new PDF and legislation lanes
emit a title but no summary - so summaries are generated here for the evaluation pool.

Sentence splitting is deliberately conservative on legal text: a split on ". " alone breaks
"reg. 72", "s. 12" and "No. 3", so abbreviations and enumeration markers are protected.
"""
from __future__ import annotations

import argparse, json, os, re, sqlite3, statistics, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Protect legal abbreviations and numbered markers before splitting.
ABBR = re.compile(r"\b(reg|s|ss|art|para|paras|sch|No|no|cl|r|Ch|Pt|SI|S\.I)\.\s", re.I)
SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z(“\"]|\(\w\)|\d+\.)")


def sentences(text: str, min_chars: int = 25) -> list[str]:
    t = ABBR.sub(lambda m: m.group(0).replace(".", "\x00"), text or "")
    parts = [p.replace("\x00", ".").strip() for p in SPLIT.split(t)]
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        # A fragment shorter than a clause is attached to its predecessor rather than
        # embedded alone: "(a) the supplier is insolvent" is not a retrievable unit.
        if out and len(p) < min_chars:
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


SUMMARY_SYSTEM = """You write one-sentence descriptions of UK public procurement text, for a search index.

Given a passage, state what it says in a single sentence of at most 30 words.

Rules:
- Describe the rule, procedure or definition the passage states. Do not editorialise.
- Use the terminology of the passage, including statutory terms, so a search on those terms matches.
- Do not begin with "This passage", "This section describes" or similar. State the content directly.
- If the passage states an obligation, say what must be done and by whom.

Return JSON only."""

SCHEMA = {"type": "object", "properties": {"summaries": {"type": "array", "items": {
    "type": "object", "properties": {"ref": {"type": "integer"}, "summary": {"type": "string"}},
    "required": ["ref", "summary"], "additionalProperties": False}}},
    "required": ["summaries"], "additionalProperties": False}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="state/chunk_index_merged.sqlite3", type=Path)
    ap.add_argument("--sets", nargs="*", default=[
        "evaluation/curated/retrieval_eval_150_v1_curated.jsonl",
        "evaluation/curated/retrieval_test_150_v1_curated.jsonl"])
    ap.add_argument("--distractors", type=int, default=2500,
                    help="non-gold chunks retrieved for these queries, to make ranking realistic")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--out", default="evaluation/representations", type=Path)
    a = ap.parse_args()
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ROOT / a.db); con.row_factory = sqlite3.Row

    gold, queries = set(), []
    for s in a.sets:
        for l in (ROOT / s).open(encoding="utf-8"):
            q = json.loads(l)
            if q.get("gold_chunk_ids"):
                gold |= set(q["gold_chunk_ids"])
                queries.append({"query_id": q["query_id"], "query": q["query"],
                                "suite": q.get("suite"), "split": q.get("split"),
                                "gold_chunk_ids": q["gold_chunk_ids"]})
    print(f"queries {len(queries)}  gold chunks {len(gold):,}", flush=True)

    # Distractors are what retrieval actually returns for these queries, so the pool reflects
    # the real competition rather than a random sample of the corpus.
    from chunk_retrieval import ChunkRetriever
    r = ChunkRetriever(ROOT / a.db, "chunks__bge_m3__merged")
    pool = set(gold)
    for i, q in enumerate(queries, 1):
        res, _ = r.search(q["query"], top_k=12)
        pool |= {x["chunk_id"] for x in res}
        if len(pool) >= len(gold) + a.distractors:
            break
        if i % 50 == 0:
            print(f"  pooling {i}/{len(queries)}: {len(pool):,} chunks", flush=True)
    print(f"pool: {len(pool):,} chunks ({len(gold):,} gold)", flush=True)

    ph = ",".join("?" * len(pool))
    rows = [dict(x) for x in con.execute(
        f"SELECT chunk_id, citation, retrieval_title, retrieval_summary, text, est_tokens, "
        f"authority_class, chunking_method FROM chunks WHERE chunk_id IN ({ph})", tuple(pool))]

    need = [x for x in rows if not (x["retrieval_summary"] or "").strip()]
    print(f"summaries to generate: {len(need):,} of {len(rows):,}", flush=True)
    if need:
        from openai import OpenAI
        cl = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=180.0, max_retries=3)
        for i in range(0, len(need), a.batch):
            b = need[i: i + a.batch]
            payload = [{"ref": j, "citation": x["citation"],
                        "text": (x["text"] or "")[:2500]} for j, x in enumerate(b)]
            try:
                resp = cl.chat.completions.create(
                    model=a.model, temperature=0,
                    messages=[{"role": "system", "content": SUMMARY_SYSTEM},
                              {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                    response_format={"type": "json_schema", "json_schema": {
                        "name": "summaries", "schema": SCHEMA, "strict": True}})
                got = {s["ref"]: s["summary"] for s in
                       json.loads(resp.choices[0].message.content)["summaries"]}
                for j, x in enumerate(b):
                    x["retrieval_summary"] = got.get(j, "")
            except Exception as exc:
                print(f"  batch {i//a.batch} failed: {str(exc)[:90]}", flush=True)
            if (i // a.batch) % 10 == 0:
                print(f"  {min(i+a.batch,len(need))}/{len(need)}", flush=True)
            time.sleep(0.1)

    recs = []
    for x in rows:
        sents = sentences(x["text"] or "")
        recs.append({
            "chunk_id": x["chunk_id"], "citation": x["citation"],
            "authority_class": x["authority_class"], "chunking_method": x["chunking_method"],
            "est_tokens": x["est_tokens"], "is_gold": x["chunk_id"] in gold,
            "rep_text": x["text"] or "",
            "rep_title_text": f"{x['citation']}\n{x['retrieval_title'] or ''}\n\n{x['text'] or ''}",
            "rep_summary": (x["retrieval_summary"] or "").strip(),
            "rep_sentences": sents,
            "n_sentences": len(sents),
        })
    (out / "pool.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in recs), encoding="utf-8")
    (out / "queries.jsonl").write_text(
        "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queries), encoding="utf-8")
    ns = [x["n_sentences"] for x in recs]
    print(f"\nwritten {len(recs):,} chunks -> {out}/pool.jsonl")
    print(f"  sentences per chunk: median {statistics.median(ns):.0f}  mean {statistics.mean(ns):.1f}  max {max(ns)}")
    print(f"  total sentence vectors that would be needed: {sum(ns):,}")
    print(f"  summaries present: {sum(1 for x in recs if x['rep_summary']):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
