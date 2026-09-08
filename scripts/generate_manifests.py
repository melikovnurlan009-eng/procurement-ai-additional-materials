#!/usr/bin/env python3
"""Generate MANIFEST.sha256 (every file, for integrity verification) and
provenance/artifact_manifest.csv (curated, human-readable inventory by category)."""
import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git"}
SKIP_NAMES = {"MANIFEST.sha256"}


def sha256_file(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def iter_files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SKIP_NAMES:
            continue
        yield p


def gen_manifest_sha256():
    lines = []
    for p in iter_files():
        rel = p.relative_to(ROOT)
        lines.append(f"{sha256_file(p)}  {rel}")
    (ROOT / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")
    print(f"MANIFEST.sha256: {len(lines)} files")


CATEGORY_RULES = [
    ("code/scrapers/", "corpus_acquisition_code"),
    ("code/procurement_kg/", "graph_construction_code"),
    ("corpus_manifests/", "corpus_acquisition_manifest"),
    ("code/evaluation/final_retrieval_benchmark/", "standalone_benchmark_code_and_data"),
    ("code/procurement_research_workbench_v1/prw/", "frozen_evaluation_code"),
    ("code/procurement_research_workbench_v1/data/", "evaluation_test_dataset"),
    ("code/procurement_research_workbench_v1/schemas/", "evaluation_schema"),
    ("code/procurement_research_workbench_v1/configs/", "retrieval_and_model_config"),
    ("code/procurement_research_workbench_v1/tests/", "evaluation_unit_tests"),
    ("code/unused_demo_api/", "unused_demo_code_not_evaluated"),
    ("results/runs/", "raw_dev_test_retrieval_outputs"),
    ("results/judgments/", "raw_llm_judgment_outputs"),
    ("results/pool/", "pooled_candidate_data"),
    ("results/evaluate_output/", "derived_dev_test_metrics"),
    ("results/final_reports/", "final_thesis_reports_and_tables"),
    ("environment/", "environment_record"),
    ("provenance/", "provenance_and_changelog"),
    ("scripts/", "verification_scripts"),
]


def categorize(rel_str):
    for prefix, cat in CATEGORY_RULES:
        if rel_str.startswith(prefix):
            return cat
    return "top_level_documentation"


def gen_artifact_manifest():
    # Directory-level rollup for very large/bulky directories (per-scenario cache-like content),
    # file-level detail everywhere else.
    ROLLUP_DIRS = [
        "code/evaluation/final_retrieval_benchmark/retrieval_runs",
        "results/runs",
        "results/judgments",
        "results/pool",
    ]
    rows = []
    rolled_up_prefixes = []
    for d in ROLLUP_DIRS:
        p = ROOT / d
        if p.exists():
            files = [f for f in p.rglob("*") if f.is_file()]
            if files:
                total_size = sum(f.stat().st_size for f in files)
                rows.append({
                    "relative_path": d + "/", "artifact_type": "directory_rollup",
                    "description": f"{len(files)} files, raw per-scenario/per-candidate data",
                    "required_for": "full_traceability_of_reported_metrics",
                    "generated_or_source": "generated", "frozen": "no",
                    "size_bytes": total_size, "sha256": "see_MANIFEST.sha256_for_individual_files",
                    "provenance": "produced by the workbench/standalone-benchmark pipelines during this project's evaluation runs",
                    "notes": f"{len(files)} individual files rolled up here for readability; every file is individually hashed in MANIFEST.sha256",
                })
                rolled_up_prefixes.append(d)

    for p in sorted(ROOT.rglob("*")):
        if p.is_dir() or p.name in SKIP_NAMES:
            continue
        rel = str(p.relative_to(ROOT))
        if any(rel.startswith(rp) for rp in rolled_up_prefixes):
            continue
        cat = categorize(rel)
        frozen = "yes" if "prw/" in rel and rel.endswith(".py") else "no"
        rows.append({
            "relative_path": rel, "artifact_type": cat,
            "description": "", "required_for": cat,
            "generated_or_source": "source" if "/code/" in "/" + rel else "generated",
            "frozen": frozen, "size_bytes": p.stat().st_size,
            "sha256": sha256_file(p), "provenance": "this session's thesis project work",
            "notes": "",
        })

    out = ROOT / "provenance" / "artifact_manifest.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["relative_path", "artifact_type", "description",
                                          "required_for", "generated_or_source", "frozen",
                                          "size_bytes", "sha256", "provenance", "notes"])
        w.writeheader()
        w.writerows(rows)
    print(f"provenance/artifact_manifest.csv: {len(rows)} rows")


if __name__ == "__main__":
    gen_artifact_manifest()  # must run before MANIFEST.sha256 so the CSV itself gets hashed too
    gen_manifest_sha256()
