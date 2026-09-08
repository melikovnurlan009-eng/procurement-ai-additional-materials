#!/usr/bin/env python3
"""Evolutionary optimisation of the semantic-chunking prompt.

Method
------
WizardLM-style prompt evolution against a measured objective. Each round an LLM mutates the
current best prompt (add a constraint, make an instruction concrete, remove a redundancy);
every candidate is then RUN over a fixed stratified sample of parent segments and scored by
the Tier-1 structural detectors from `evaluate_chunk_quality.py`. The best-scoring candidate
seeds the next round.

The objective is deterministic and model-free, which is the point: a prompt tuned by asking
a model "is this prompt better" optimises agreement with that model, not chunk quality.

Objective (lower is better)
    defect_rate        boundary defects per chunk (severed sentences, severed list stems,
                       orphan list items, too-small-to-retrieve, empty text)
    size_penalty       fraction of chunks outside the 200-1200 token retrievable band
    grounding_penalty  1 - mean lexical grounding of retrieval_summary in chunk text
    score = defect_rate + 0.5*size_penalty + 0.5*grounding_penalty

Sample segments are held fixed across rounds so scores are comparable. Chunk text is
reconstructed from immutable source blocks exactly as the production pipeline does, so a
prompt cannot score well by rewriting text.

Usage
-----
    python optimize_chunking_prompt.py --rounds 2 --variants 3
"""
from __future__ import annotations

import argparse, json, os, statistics, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_chunk_quality import assess_chunk, est_tokens, grounding

# build_search_corpus imports bs4, which the evaluation venv does not carry. The seed prompt
# and boundary schema are therefore lifted from that file at import time rather than copied,
# so the production definitions remain the single source of truth and cannot drift.
def _load_from_pipeline() -> tuple[str, dict]:
    import ast
    src = (Path(__file__).resolve().parent / "build_search_corpus.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("SYSTEM_PROMPT", "BOUNDARY_SCHEMA"):
                found[name] = ast.literal_eval(node.value)
    missing = {"SYSTEM_PROMPT", "BOUNDARY_SCHEMA"} - set(found)
    if missing:
        raise SystemExit(f"could not lift {missing} from build_search_corpus.py")
    return found["SYSTEM_PROMPT"], found["BOUNDARY_SCHEMA"]

SEED_PROMPT, BOUNDARY_SCHEMA = _load_from_pipeline()


def llm_payload(seg):
    """Identical to build_search_corpus.llm_payload - the model must see the same input."""
    return json.dumps({
        "segment_id": seg["segment_id"], "document_id": seg["document_id"],
        "source_kind": seg["source_kind"], "citation": seg.get("citation"),
        "heading": seg.get("heading"), "heading_path": seg.get("heading_path", []),
        "blocks": [{k: b.get(k) for k in
                    ["block_id", "block_type", "number", "heading", "page_number", "text"]}
                   for b in seg["blocks"]],
    }, ensure_ascii=False)

OPTIMISER_VERSION = "1.0.0"
TARGET_MIN, TARGET_MAX = 200, 1200

MUTATE_SYSTEM = """You improve a SYSTEM PROMPT used by a legal-document chunking component.

The prompt instructs a model to group contiguous immutable source blocks into independently
retrievable semantic chunks. It must never permit rewriting, paraphrasing or reordering source text.

Produce ONE improved variant. Apply exactly one evolution operator:
- CONSTRAIN: add a precise, checkable rule that prevents a boundary defect
- CONCRETISE: replace a vague instruction with a specific, testable one
- DEEPEN: give sharper guidance for a hard case (severed list stems, orphan list items,
  headings split from the text they govern, definitions split from the term defined)
- PRUNE: remove redundancy or an instruction that conflicts with another

Constraints on your output:
- Keep it under 320 words.
- Preserve every safety rule about not altering source text or [[LINK_NNNN]] placeholders.
- Must still instruct the model to return structured JSON only.
- Do not mention this optimisation process.

Return the prompt text only, no commentary."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def chunks_from_plan(seg: dict, plan: dict) -> list[dict]:
    """Reconstruct chunk text from immutable blocks, exactly as the pipeline does."""
    order = [b["block_id"] for b in seg["blocks"]]
    text_of = {b["block_id"]: b["text"] for b in seg["blocks"]}
    idx = {b: i for i, b in enumerate(order)}
    out = []
    for i, c in enumerate(plan.get("chunks", []), 1):
        a, b = idx.get(c["start_block_id"]), idx.get(c["end_block_id"])
        if a is None or b is None or b < a:
            continue
        body = "\n\n".join(text_of[x] for x in order[a:b + 1])
        out.append({"chunk_id": f"{seg['segment_id']}__CH_{i:03d}", "text": body,
                    "retrieval_title": c.get("retrieval_title", ""),
                    "retrieval_summary": c.get("retrieval_summary", ""),
                    "est_tokens": est_tokens(body)})
    return out


def score(all_chunks: list[dict]) -> dict:
    if not all_chunks:
        return {"score": 9.99, "chunks": 0}
    defects = 0
    for i, c in enumerate(all_chunks):
        nxt = all_chunks[i + 1] if i + 1 < len(all_chunks) else None
        a = assess_chunk(c, nxt)
        defects += len(a.get("defects", []))
    n = len(all_chunks)
    outside = sum(1 for c in all_chunks if not (TARGET_MIN <= c["est_tokens"] <= TARGET_MAX))
    g = statistics.mean([grounding(c["retrieval_summary"], c["text"]) for c in all_chunks])
    defect_rate, size_pen, ground_pen = defects / n, outside / n, 1.0 - g
    return {"score": round(defect_rate + 0.5 * size_pen + 0.5 * ground_pen, 4),
            "defect_rate": round(defect_rate, 4), "defects": defects,
            "size_penalty": round(size_pen, 4), "grounding": round(g, 4), "chunks": n}


def run_prompt(client, model: str, prompt: str, segs: list[dict], max_out: int) -> dict:
    chunks = []
    for seg in segs:
        try:
            r = client.responses.create(
                model=model, instructions=prompt, input=llm_payload(seg),
                text={"format": {"type": "json_schema", "name": "semantic_chunk_boundaries",
                                 "strict": True, "schema": BOUNDARY_SCHEMA}},
                max_output_tokens=max_out, store=False)
            chunks += chunks_from_plan(seg, json.loads(r.output_text))
        except Exception as exc:
            print(f"    [warn] {seg['segment_id'][:28]}: {str(exc)[:70]}", flush=True)
    return score(chunks)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", default="evaluation/prompt_opt/sample_segments.jsonl", type=Path)
    ap.add_argument("--out", default="evaluation/prompt_opt", type=Path)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--mutator-model", default="gpt-4.1")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--max-output-tokens", type=int, default=16000)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    segs = [json.loads(l) for l in (root / args.sample).open(encoding="utf-8") if l.strip()]
    out = root / args.out; out.mkdir(parents=True, exist_ok=True)
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    print(f"sample: {len(segs)} segments | rounds {args.rounds} x {args.variants} variants\n")
    print("scoring SEED prompt ...", flush=True)
    best_prompt, best = SEED_PROMPT, run_prompt(client, args.model, SEED_PROMPT, segs, args.max_output_tokens)
    print(f"  seed  score={best['score']}  defects/chunk={best['defect_rate']} "
          f"size_pen={best['size_penalty']} grounding={best['grounding']} chunks={best['chunks']}\n")
    history = [{"round": 0, "label": "seed", **best, "prompt": SEED_PROMPT}]

    for rnd in range(1, args.rounds + 1):
        print(f"--- round {rnd} ---", flush=True)
        for v in range(1, args.variants + 1):
            m = client.chat.completions.create(
                model=args.mutator_model, temperature=1,
                messages=[{"role": "system", "content": MUTATE_SYSTEM},
                          {"role": "user", "content": f"Current prompt:\n\n{best_prompt}"}])
            cand = m.choices[0].message.content.strip()
            s = run_prompt(client, args.model, cand, segs, args.max_output_tokens)
            flag = ""
            if s["score"] < best["score"]:
                best, best_prompt, flag = s, cand, "  <-- new best"
            print(f"  v{rnd}.{v}  score={s['score']}  defects/chunk={s['defect_rate']} "
                  f"size_pen={s['size_penalty']} grounding={s['grounding']} chunks={s['chunks']}{flag}", flush=True)
            history.append({"round": rnd, "label": f"v{rnd}.{v}", **s, "prompt": cand})

    (out / "optimised_prompt.txt").write_text(best_prompt, encoding="utf-8")
    (out / "optimisation_report.json").write_text(json.dumps({
        "optimiser_version": OPTIMISER_VERSION, "generated_at": now_iso(),
        "chunking_model": args.model, "mutator_model": args.mutator_model,
        "sample_segments": len(segs), "rounds": args.rounds, "variants": args.variants,
        "objective": "defect_rate + 0.5*size_penalty + 0.5*grounding_penalty (lower better)",
        "seed": history[0], "best": {k: v for k, v in history[0].items() if k != "prompt"} if best_prompt == SEED_PROMPT
                 else next({k: v for k, v in h.items() if k != "prompt"} for h in history if h["prompt"] == best_prompt),
        "history": [{k: v for k, v in h.items() if k != "prompt"} for h in history],
        "all_prompts": {h["label"]: h["prompt"] for h in history},
    }, indent=2), encoding="utf-8")
    print(f"\nBEST score={best['score']}  (seed was {history[0]['score']})")
    print(f"written: {out/'optimised_prompt.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
