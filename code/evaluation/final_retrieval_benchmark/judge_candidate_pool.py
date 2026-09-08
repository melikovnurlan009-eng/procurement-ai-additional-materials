#!/usr/bin/env python3
"""
First-pass LLM relevance judging of candidate_pool.jsonl against each scenario's evidence
requirements. Model: gpt-4o-mini. Every judgment is tagged annotation_status="LLM_FIRST_PASS" --
this is explicitly NOT human ground truth.

Prints an estimate (calls, rough cost, rough runtime) before running and requires the
DRY_RUN=0 env var to actually spend -- otherwise it stops after printing the estimate.

Output: qrels_provisional.jsonl (all judgments) and qrels_review_queue.jsonl (grade-3 items,
low-confidence items, and regime-ambiguous items, for a human/second-pass check).

Caches by (scenario_id, chunk_id) to a local cache file so a re-run does not re-pay for
already-judged pairs.
"""
import json, os, sys, time
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
CACHE_PATH = BENCH_DIR / "_judge_cache.jsonl"
MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are grading retrieval candidates for a UK public procurement legal-retrieval
benchmark. You will be given a realistic user scenario, its query, its evidence requirements,
and one retrieved passage (with its citation/source metadata). Grade the passage's relevance
to that SPECIFIC scenario on a 0-3 scale:

3 = directly answers a required part of the scenario / is essential evidence for one of the
    listed requirements. This can be a legislation passage OR an official guidance passage --
    for a practical/workflow question, guidance that directly answers it is a 3; do not force
    primary legislation to 3 for every question, and do not force guidance down to 2 just
    because it is not legislation.
2 = strongly supports the answer / explains the applicable rule but is not by itself
    sufficient/direct evidence for a requirement.
1 = useful background, topically related, but does not materially resolve any requirement.
0 = irrelevant, wrong regime for this scenario's stated regime_context, wrong legal issue, or
    actively misleading.

Also identify which requirement_ids (if any) this passage helps satisfy, and note is_binding
(true if this is primary/secondary legislation) and is_currently_applicable (false if this
passage states a rule that was repealed/superseded relative to the scenario's regime_context,
e.g. citing PCR2015 for a clearly PA2023-only scenario with no legacy/transition angle).

Return strict JSON: {"relevance_grade": 0-3, "requirement_ids_supported": [...],
"is_binding": true/false, "is_currently_applicable": true/false, "reason": "...", "confidence": 0-1}
"""


def load_jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def main():
    scenarios = {s["scenario_id"]: s for s in load_jsonl(BENCH_DIR / "scenarios_all.jsonl")}
    pool = load_jsonl(BENCH_DIR / "candidate_pool.jsonl")

    cache = {}
    if CACHE_PATH.exists():
        for l in open(CACHE_PATH):
            if l.strip():
                d = json.loads(l)
                cache[(d["scenario_id"], d["chunk_id"])] = d

    to_judge = [row for row in pool if (row["scenario_id"], row["chunk_id"]) not in cache]

    n_total_calls = len(to_judge)
    est_input_tokens = n_total_calls * 700  # rough: system+scenario+passage
    est_output_tokens = n_total_calls * 120
    est_cost_usd = (est_input_tokens / 1_000_000) * 0.15 + (est_output_tokens / 1_000_000) * 0.60
    print(f"Candidate pool rows: {len(pool)}. Already cached: {len(pool) - n_total_calls}. "
          f"To judge now: {n_total_calls}.", file=sys.stderr)
    print(f"Estimated tokens: ~{est_input_tokens:,} in / ~{est_output_tokens:,} out. "
          f"Estimated cost (gpt-4o-mini): ~${est_cost_usd:.2f}. "
          f"Estimated runtime at ~8 req/s: ~{n_total_calls/8:.0f}s.", file=sys.stderr)

    if os.environ.get("DRY_RUN", "1") != "0":
        print("DRY RUN (default) -- set DRY_RUN=0 to actually spend and run judging.", file=sys.stderr)
        return

    from openai import OpenAI
    client = OpenAI(timeout=60.0, max_retries=3)

    t0 = time.time()
    cache_f = CACHE_PATH.open("a")
    for i, row in enumerate(to_judge):
        sid = row["scenario_id"]
        sc = scenarios.get(sid)
        if not sc:
            continue
        payload = {
            "scenario_text": sc.get("scenario_text"),
            "query": sc.get("query"),
            "regime_context": sc.get("regime_context"),
            "evidence_requirements": sc.get("evidence_requirements"),
            "passage_citation": row.get("citation"),
            "passage_authority_class": row.get("authority_class"),
            "passage_legal_regime": row.get("legal_regime"),
            "passage_text": (row.get("text") or "")[:1200],
        }
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0,
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                response_format={"type": "json_object"},
            )
            judgment = json.loads(resp.choices[0].message.content)
        except Exception as e:
            judgment = {"relevance_grade": None, "error": str(e)[:200]}
        record = {
            "scenario_id": sid, "chunk_id": row["chunk_id"],
            "authority_class": row.get("authority_class"), "legal_regime": row.get("legal_regime"),
            "source_role": row.get("authority_class"),
            "annotation_status": "LLM_FIRST_PASS", "model": MODEL,
            **judgment,
        }
        cache_f.write(json.dumps(record, ensure_ascii=False) + "\n")
        cache_f.flush()
        if (i + 1) % 50 == 0:
            print(f"  judged {i+1}/{n_total_calls} ({time.time()-t0:.0f}s)", file=sys.stderr)
    cache_f.close()

    # rebuild final outputs from full cache
    finalize()


def finalize():
    cache = [json.loads(l) for l in open(CACHE_PATH) if l.strip()]
    qrels_path = BENCH_DIR / "qrels_provisional.jsonl"
    review_path = BENCH_DIR / "qrels_review_queue.jsonl"
    n_review = 0
    with qrels_path.open("w") as fq, review_path.open("w") as fr:
        for rec in cache:
            fq.write(json.dumps(rec, ensure_ascii=False) + "\n")
            grade = rec.get("relevance_grade")
            conf = rec.get("confidence")
            needs_review = (grade == 3) or (isinstance(conf, (int, float)) and conf < 0.5) or (grade is None)
            if needs_review:
                fr.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_review += 1
    print(f"Wrote {len(cache)} judgments to {qrels_path}, {n_review} flagged to {review_path}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "finalize":
        finalize()
    else:
        main()
