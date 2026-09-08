#!/usr/bin/env python3
"""
Convert evaluation/final_retrieval_benchmark/{scenarios_all,gold_evidence}.jsonl into the
procurement_research_workbench_v1 schema (schemas/scenario.schema.json,
schemas/requirements.schema.json) WITHOUT changing any fact, wording, requirement content, or
split membership. This is a structural reformat only:

- scenario_id, requirement ids, and all citation/chunk_id references are PRESERVED VERBATIM.
- Public scenario record: only scenario_id, scenario_group_id, split, suite, topic, as_of,
  user_message, history, synthetic, authoring_status -- matching additionalProperties:false in
  scenario.schema.json. user_message = scenario_text + "\n\n" + query, concatenated verbatim
  (no added preamble, no rewording) -- this project's scenarios do not carry the other
  package's common "assume an English..." preamble sentence, and none is added here; that is a
  real, disclosed difference between the two datasets, not a fix.
- Private requirements record: everything else (organisation_type, user_role, difficulty,
  regime_context, requires_graph, requires_multiple_evidence_items, notes, and the full
  essential/strong-supporting/acceptable-alternative evidence with real verified chunk_ids)
  moves here, under extra fields the requirements schema permits (it has no
  additionalProperties:false). None of this is read by the runtime controller -- confirmed by
  grep against prw/*.py: only id/description/mandatory/source_policy/allow_conditional are
  consumed programmatically from each requirement.

suite name mapping (structural relabelling only, not a semantic change):
  exact_anchor -> statutory
  semantic -> semantic
  vocabulary_mismatch -> vocabulary
  graph_multi_hop -> multi_evidence
  applicability -> applicability
  practical_guidance -> guidance
  authority -> authority
  compound -> compound

source_policy is derived, not invented: BINDING_REQUIRED if every essential_evidence item for
that requirement is a LEGAL_PROVISION; OFFICIAL_ALLOWED if any essential_evidence item is a
DOCUMENT_OR_CHUNK (guidance) -- i.e. exactly the distinction already present in this project's
own gold (target_type field), just re-expressed in the other package's vocabulary.
"""
import json, re, hashlib
from pathlib import Path
from collections import defaultdict

BENCH_DIR = Path(__file__).resolve().parent
WORKBENCH_DIR = BENCH_DIR.parent.parent / "procurement_research_workbench_v1"

SUITE_MAP = {
    "exact_anchor": "statutory",
    "semantic": "semantic",
    "vocabulary_mismatch": "vocabulary",
    "graph_multi_hop": "multi_evidence",
    "applicability": "applicability",
    "practical_guidance": "guidance",
    "authority": "authority",
    "compound": "compound",
}

INSTRUMENT_CODES = [
    (re.compile(r"Procurement Act 2023 \(Commencement", re.I), "commencement2024"),
    (re.compile(r"Procurement Act 2023", re.I), "pa"),
    (re.compile(r"Procurement Regulations 2024", re.I), "pr"),
    (re.compile(r"Public Contracts Regulations 2015", re.I), "pcr2015"),
    (re.compile(r"Freedom of Information Act 2000", re.I), "foia"),
    (re.compile(r"Late Payment of Commercial Debts", re.I), "latepayment1998"),
]


def load_jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def instrument_code(citation):
    for pat, code in INSTRUMENT_CODES:
        if pat.search(citation or ""):
            return code
    return "guidance"


def content_hash(scenario, gold):
    payload = json.dumps({"scenario": scenario, "gold": gold}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def convert():
    scenarios = load_jsonl(BENCH_DIR / "scenarios_all.jsonl")
    gold_by_id = {g["scenario_id"]: g for g in load_jsonl(BENCH_DIR / "gold_evidence.jsonl")}

    out_scenarios = []
    out_requirements = []
    hash_manifest = {}

    for sc in scenarios:
        sid = sc["scenario_id"]
        g = gold_by_id[sid]

        # ---- public scenario record ----
        user_message = (sc["scenario_text"].strip() + "\n\n" + sc["query"].strip())
        public_record = {
            "scenario_id": sid,
            "scenario_group_id": sid,  # each scenario is its own independent group -- no
                                       # paraphrase/follow-up linkage was constructed, so no
                                       # shared group id is fabricated; this is the honest
                                       # default, not an invented narrative slug.
            "split": sc["split"],
            "suite": SUITE_MAP[sc["suite"]],
            "topic": sc["topic"],
            "as_of": "2026-09-07",
            "user_message": user_message,
            "history": [],
            "synthetic": True,
            "authoring_status": "MODEL_AUTHORED_SOURCE_GUIDED_NOT_EXPERT_VALIDATED",
        }
        out_scenarios.append(public_record)

        # ---- private requirements record ----
        req_records = []
        ref_codes = {sc["topic"]}
        missing_facts = []
        for req_meta, req_gold in zip(sc["evidence_requirements"], g["requirements"]):
            assert req_meta["requirement_id"] == req_gold["requirement_id"], \
                f"requirement id mismatch in {sid}: {req_meta['requirement_id']} vs {req_gold['requirement_id']}"
            essential = req_gold.get("essential_evidence", [])
            target_types = {e.get("target_type") for e in essential}
            if target_types and target_types <= {"LEGAL_PROVISION"}:
                source_policy = "BINDING_REQUIRED"
            elif "DOCUMENT_OR_CHUNK" in target_types:
                source_policy = "OFFICIAL_ALLOWED"
            elif not essential:
                # requirement supported only by strong_supporting_evidence (no essential item) --
                # treat as ANY_SUPPORTED since nothing is mandated as binding-only.
                source_policy = "ANY_SUPPORTED"
            else:
                source_policy = "BINDING_REQUIRED"

            desc = req_meta["description"]
            allow_conditional = bool(re.search(
                r"\bflag\b|\bnot given\b|\bnot establish|\bdoes not (?:supply|establish)|"
                r"\bnot supplied\b|\bunresolved\b", desc, re.I))
            if allow_conditional:
                missing_facts.append(desc)

            for e in essential:
                ref_codes.add(instrument_code(e.get("citation", "")))
            for e in req_gold.get("strong_supporting_evidence", []):
                ref_codes.add(instrument_code(e.get("citation", "")))

            req_records.append({
                "id": req_meta["requirement_id"],
                "description": desc,
                "mandatory": bool(req_meta.get("mandatory", True)),
                "source_policy": source_policy,
                "allow_conditional": allow_conditional,
                "assessment_unit": "atomic_information_requirement",
                # -- extra, non-schema-mandated fields below: not read by runtime controller,
                # kept for independent-reviewer / reference-excerpt provenance only --
                "verified_evidence_reference": {
                    "essential_evidence": req_gold.get("essential_evidence", []),
                    "strong_supporting_evidence": req_gold.get("strong_supporting_evidence", []),
                    "acceptable_alternatives": req_gold.get("acceptable_alternatives", []),
                    "requirement_grade_if_satisfied": req_gold.get("requirement_grade_if_satisfied", 3),
                },
            })

        private_record = {
            "scenario_id": sid,
            "scenario_group_id": sid,
            "split": sc["split"],
            "author_note": (
                "Requirements state what evidence is needed; verified_evidence_reference on "
                "each requirement is real, corpus-verified provenance (every citation confirmed "
                "present in the live corpus this session -- see "
                "evaluation/final_retrieval_benchmark/gold_resolution_report.json), not an "
                "invented closed list, and not itself consulted by the runtime bundle judge, "
                "which assesses retrieved evidence against the requirement description text."
            ),
            "corpus_support_status": "CORPUS_VERIFIED",
            "label_status": "UNJUDGED",
            "missing_facts": missing_facts,
            "reference_source_ids": sorted(ref_codes),
            "reference_status": "SPECIFIC_PROVISIONS_VERIFIED_IN_LIVE_CORPUS_REQUIREMENT_LABELS_UNJUDGED",
            "reference_targets_are_exhaustive": False,
            "regime_context": sc.get("regime_context"),
            "requirements": req_records,
            # -- extra scenario-authoring metadata, private-only, not part of either base schema --
            "scenario_metadata": {
                "difficulty": sc.get("difficulty"),
                "user_role": sc.get("user_role"),
                "organisation_type": sc.get("organisation_type"),
                "regime_confidence": sc.get("regime_confidence"),
                "retrieval_intents": sc.get("retrieval_intents"),
                "requires_multiple_evidence_items": sc.get("requires_multiple_evidence_items"),
                "requires_graph": sc.get("requires_graph"),
                "original_suite_label": sc.get("suite"),
                "construction_notes": sc.get("notes"),
            },
        }
        out_requirements.append(private_record)
        hash_manifest[sid] = content_hash(public_record, private_record)

    return out_scenarios, out_requirements, hash_manifest


def write_split(out_scenarios, out_requirements, hash_manifest):
    by_split = defaultdict(lambda: {"scenarios": [], "requirements": []})
    for s in out_scenarios:
        by_split[s["split"]]["scenarios"].append(s)
    req_by_id = {r["scenario_id"]: r for r in out_requirements}
    for split, bucket in by_split.items():
        for s in bucket["scenarios"]:
            bucket["requirements"].append(req_by_id[s["scenario_id"]])

    out_dir = BENCH_DIR / "workbench_schema"
    out_dir.mkdir(exist_ok=True)
    for split in ("dev", "test"):
        bucket = by_split[split]
        with (out_dir / f"scenarios_{split}.jsonl").open("w") as f:
            for s in bucket["scenarios"]:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        with (out_dir / f"requirements_{split}.jsonl").open("w") as f:
            for r in bucket["requirements"]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{split}: {len(bucket['scenarios'])} scenarios, {len(bucket['requirements'])} requirement records")

    json.dump(hash_manifest, open(out_dir / "content_hash_manifest.json", "w"), indent=2)
    print(f"Written to {out_dir}")


if __name__ == "__main__":
    out_scenarios, out_requirements, hash_manifest = convert()
    write_split(out_scenarios, out_requirements, hash_manifest)
