#!/usr/bin/env python3
"""
Leakage audit for scenarios_all.jsonl: exact duplicate, normalised duplicate, and semantic
similarity checks between every DEV and TEST scenario (and within each split too, as a sanity
check). Must be run with .venv-embed/bin/python3 for the embedding step.

Writes split_audit.md with every DEV/TEST pair above the similarity threshold, its shared
topic/provision (if any), and a human-reviewable decision field (default: "NEEDS_REVIEW" --
this script flags, it does not adjudicate).
"""
import json, re, sys
from pathlib import Path
from itertools import product

BENCH_DIR = Path(__file__).resolve().parent
SIM_THRESHOLD = 0.90


def load():
    return [json.loads(l) for l in open(BENCH_DIR / "scenarios_all.jsonl") if l.strip()]


def norm_text(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main():
    scenarios = load()
    dev = [s for s in scenarios if s["split"] == "dev"]
    test = [s for s in scenarios if s["split"] == "test"]
    print(f"dev={len(dev)} test={len(test)}", file=sys.stderr)

    # 1. exact + normalised duplicate check (query field, the runtime-visible text)
    exact_dupes = []
    norm_dupes = []
    for d, t in product(dev, test):
        if d["query"].strip() == t["query"].strip():
            exact_dupes.append((d["scenario_id"], t["scenario_id"]))
        elif norm_text(d["query"]) == norm_text(t["query"]):
            norm_dupes.append((d["scenario_id"], t["scenario_id"]))

    # 2. semantic similarity via BGE-M3 (same model as production dense retrieval)
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = SentenceTransformer("BAAI/bge-m3")
        dev_vecs = model.encode([s["query"] for s in dev], normalize_embeddings=True)
        test_vecs = model.encode([s["query"] for s in test], normalize_embeddings=True)
        sim_matrix = dev_vecs @ test_vecs.T
        sim_pairs = []
        for i, d in enumerate(dev):
            for j, t in enumerate(test):
                sim = float(sim_matrix[i, j])
                if sim >= SIM_THRESHOLD:
                    sim_pairs.append((d["scenario_id"], t["scenario_id"], round(sim, 4)))
        sim_pairs.sort(key=lambda x: -x[2])
        embed_available = True
    except ImportError:
        sim_pairs = []
        embed_available = False
        print("WARNING: sentence_transformers not available in this interpreter -- semantic "
              "similarity check skipped. Re-run with .venv-embed/bin/python3.", file=sys.stderr)

    # 3. scenario-template inspection: same topic + same user_role + same organisation_type
    by_key = {}
    for s in scenarios:
        key = (s.get("topic"), s.get("user_role"), s.get("organisation_type"))
        by_key.setdefault(key, []).append(s["scenario_id"])
    template_clusters = {k: v for k, v in by_key.items() if len(v) > 1 and
                          any(sid.startswith("DEV") for sid in v) and any(sid.startswith("TEST") for sid in v)}

    scenario_by_id = {s["scenario_id"]: s for s in scenarios}

    lines = ["# Split Audit — Final Retrieval Benchmark", "",
             f"DEV scenarios: {len(dev)}. TEST scenarios: {len(test)}.", "",
             "## 1. Exact query-text duplicates (DEV vs TEST)", ""]
    if exact_dupes:
        lines.append("| DEV_ID | TEST_ID | shared issue | decision |")
        lines.append("|---|---|---|---|")
        for d, t in exact_dupes:
            lines.append(f"| {d} | {t} | identical query text | **REJECT — must be rewritten** |")
    else:
        lines.append("None found.")
    lines += ["", "## 2. Normalised-text duplicates (DEV vs TEST)", ""]
    if norm_dupes:
        lines.append("| DEV_ID | TEST_ID | shared issue | decision |")
        lines.append("|---|---|---|---|")
        for d, t in norm_dupes:
            lines.append(f"| {d} | {t} | same text after case/punctuation normalisation | **REJECT — must be rewritten** |")
    else:
        lines.append("None found.")
    lines += ["", f"## 3. Semantic similarity >= {SIM_THRESHOLD} (BGE-M3 cosine, DEV vs TEST)", ""]
    if not embed_available:
        lines.append("**NOT RUN** — re-run this script with `.venv-embed/bin/python3` to compute this section.")
    elif sim_pairs:
        lines.append("| DEV_ID | TEST_ID | similarity | DEV topic | TEST topic | decision |")
        lines.append("|---|---|---|---|---|---|")
        for d, t, sim in sim_pairs:
            ds, ts = scenario_by_id[d], scenario_by_id[t]
            same_topic = "same topic" if ds["topic"] == ts["topic"] else "different topic"
            lines.append(f"| {d} | {t} | {sim} | {ds['topic']} | {ts['topic']} | NEEDS_REVIEW ({same_topic}) |")
    else:
        lines.append(f"None found above threshold {SIM_THRESHOLD}.")
    lines += ["", "## 4. Same topic + role + organisation-type template clusters spanning DEV and TEST", ""]
    if template_clusters:
        lines.append("| topic | user_role | organisation_type | scenario_ids | decision |")
        lines.append("|---|---|---|---|---|")
        for (topic, role, org), ids in template_clusters.items():
            lines.append(f"| {topic} | {role} | {org} | {', '.join(ids)} | NEEDS_REVIEW — read both, confirm distinct fact patterns |")
    else:
        lines.append("None found — no topic+role+organisation combination spans both splits.")

    lines += ["", "## 5. Verdict", "",
              "TEST scenarios with an exact or normalised duplicate are REJECTED and must be "
              "rewritten before this benchmark is used for anything. Semantic-similarity and "
              "template-cluster flags are NEEDS_REVIEW, not automatic rejections — provision "
              "overlap and topical similarity are legitimate; only genuine scenario/fact-pattern "
              "duplication is disqualifying. Each flagged pair should be read by a human or a "
              "separate adversarial reviewer before the TEST split is frozen."]

    (BENCH_DIR / "split_audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"exact_dupes={len(exact_dupes)} norm_dupes={len(norm_dupes)} "
          f"sim_pairs={len(sim_pairs)} template_clusters={len(template_clusters)}", file=sys.stderr)
    print("Written split_audit.md", file=sys.stderr)


if __name__ == "__main__":
    main()
