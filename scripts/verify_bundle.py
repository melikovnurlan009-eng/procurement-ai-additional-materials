#!/usr/bin/env python3
"""
Automated bundle validator. Run from the bundle root:

    python3 scripts/verify_bundle.py

Exits 0 only if all required checks pass. This does not call any external API or database; it is
a static/offline check of the bundle's own internal consistency.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES = []
WARNINGS = []


def fail(msg):
    FAILURES.append(msg)


def warn(msg):
    WARNINGS.append(msg)


def check_required_files():
    required = [
        "README.md", "TECHNICAL_APPENDIX.md", "MANIFEST.sha256",
        "environment/environment_notes.md", "environment/requirements-lock.txt",
        "scripts/verify_freeze.py",
        "provenance/artifact_manifest.csv", "provenance/missing_artifacts.md",
        "provenance/CHANGELOG_FINALIZATION.md", "provenance/FINAL_VALIDATION_REPORT.md",
    ]
    for rel in required:
        if not (ROOT / rel).exists():
            fail(f"required file missing: {rel}")


def check_no_absolute_machine_paths():
    patterns = [re.compile(r"/Users/[A-Za-z0-9_.\-]+/"), re.compile(r"C:\\\\Users\\\\")]
    for p in ROOT.rglob("*.py"):
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        for pat in patterns:
            if pat.search(text):
                fail(f"absolute machine path found in executable source: {p.relative_to(ROOT)}")


def check_no_secrets():
    secret_pat = re.compile(r"sk-[A-Za-z0-9]{20,}")
    exts = (".py", ".md", ".json", ".txt", ".env", ".yml", ".yaml")
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in exts:
            try:
                text = p.read_text(errors="ignore")
            except Exception:
                continue
            for m in secret_pat.finditer(text):
                # Heuristic: a real OpenAI key is exactly 'sk-' + 20-51 alnum with no hyphens
                # nearby; URL slugs matched by a looser pattern are excluded by requiring no
                # surrounding hyphenated words.
                start = max(0, m.start() - 3)
                if text[start:m.start()] and text[start:m.start()][-1].isalpha():
                    continue
                fail(f"possible secret pattern in {p.relative_to(ROOT)}")
    for p in ROOT.rglob(".env*"):
        if p.name in (".env.example", ".env.sample", ".env.template"):
            continue  # deliberately-committed templates, contain no real secret -- checked below
        fail(f".env-like file present: {p.relative_to(ROOT)}")
    example_env = ROOT / ".env.example"
    if example_env.exists():
        text = example_env.read_text()
        for m in secret_pat.finditer(text):
            fail(f"possible real secret leaked into .env.example: match at offset {m.start()}")


def check_no_pycache():
    for p in ROOT.rglob("__pycache__"):
        fail(f"__pycache__ present: {p.relative_to(ROOT)}")
    for p in ROOT.rglob("*.pyc"):
        fail(f".pyc present: {p.relative_to(ROOT)}")
    for p in ROOT.rglob(".DS_Store"):
        fail(f".DS_Store present: {p.relative_to(ROOT)}")


def check_manifest_hashes():
    manifest_path = ROOT / "MANIFEST.sha256"
    if not manifest_path.exists():
        fail("MANIFEST.sha256 missing, cannot verify manifest hashes")
        return
    n_checked = 0
    n_mismatch = 0
    for line in manifest_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        expected_hash, rel_path = parts
        rel_path = rel_path.strip()
        p = ROOT / rel_path
        if not p.exists():
            fail(f"MANIFEST.sha256 references missing file: {rel_path}")
            continue
        n_checked += 1
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h != expected_hash:
            n_mismatch += 1
            fail(f"MANIFEST.sha256 hash mismatch: {rel_path}")
    if n_checked == 0:
        warn("MANIFEST.sha256 contained no checkable entries")
    print(f"  manifest entries checked: {n_checked}, mismatches: {n_mismatch}")


def check_freeze():
    import subprocess
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_freeze.py")],
                            capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode != 0:
        fail("scripts/verify_freeze.py reported a mismatch")


def check_evaluation_data_and_schemas():
    prw = ROOT / "code" / "procurement_research_workbench_v1"
    for rel in ["data/dev/scenarios.jsonl", "data/test_sealed/scenarios.jsonl",
                "schemas/scenario.schema.json", "schemas/requirements.schema.json"]:
        if not (prw / rel).exists():
            fail(f"claimed evaluation data/schema file missing: {rel}")


def check_scenario_counts():
    prw = ROOT / "code" / "procurement_research_workbench_v1"
    dev = prw / "data" / "dev" / "scenarios.jsonl"
    test = prw / "data" / "test_sealed" / "scenarios.jsonl"
    if dev.exists():
        n = sum(1 for _ in open(dev))
        if n != 40:
            warn(f"data/dev/scenarios.jsonl has {n} scenarios, documented elsewhere as 40")
    if test.exists():
        n = sum(1 for _ in open(test))
        if n != 20:
            warn(f"data/test_sealed/scenarios.jsonl has {n} scenarios, documented elsewhere as 20")
    bench = ROOT / "code" / "evaluation" / "final_retrieval_benchmark" / "workbench_schema"
    for name, expected in [("scenarios_dev.jsonl", 40), ("scenarios_test.jsonl", 20)]:
        p = bench / name
        if p.exists():
            n = sum(1 for _ in open(p))
            if n != expected:
                warn(f"{name} has {n} scenarios, documented elsewhere as {expected}")


def check_duplicate_result_files():
    # Detect the same-named result table appearing in more than one place with different content.
    seen = {}
    for p in ROOT.rglob("FINAL_RESULTS_TABLE.csv"):
        seen.setdefault(p.name, []).append(p)
    for p in ROOT.rglob("PAIRWISE_STATISTICS.csv"):
        seen.setdefault(p.name, []).append(p)
    for name, paths in seen.items():
        if len(paths) > 1:
            hashes = {hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            if len(hashes) > 1:
                fail(f"conflicting duplicate copies of {name}: {[str(p.relative_to(ROOT)) for p in paths]}")
            else:
                warn(f"{len(paths)} identical copies of {name} found (not a conflict, but redundant)")


def check_readme_references_exist():
    readme = ROOT / "README.md"
    if not readme.exists():
        return
    text = readme.read_text()
    for m in re.finditer(r"`([a-zA-Z0-9_./\-]+\.(?:py|md|csv|json|jsonl|txt))`", text):
        rel = m.group(1)
        if rel.startswith("http"):
            continue
        if not (ROOT / rel).exists() and "/" in rel:
            warn(f"README.md references a path not found in bundle: {rel}")


def check_python_syntax():
    import py_compile
    n_checked = 0
    n_failed = 0
    for p in ROOT.rglob("*.py"):
        n_checked += 1
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as e:
            n_failed += 1
            fail(f"Python syntax error: {p.relative_to(ROOT)}: {e}")
    print(f"  python files syntax-checked: {n_checked}, failed: {n_failed}")


def main():
    print("=== Bundle validator ===")
    print("Checking required files...")
    check_required_files()
    print("Checking for absolute machine paths in source...")
    check_no_absolute_machine_paths()
    print("Checking for secrets...")
    check_no_secrets()
    print("Checking for packaging noise (__pycache__, .pyc, .DS_Store)...")
    check_no_pycache()
    print("Checking MANIFEST.sha256...")
    check_manifest_hashes()
    print("Checking frozen-source hashes (scripts/verify_freeze.py)...")
    check_freeze()
    print("Checking evaluation data/schema files exist...")
    check_evaluation_data_and_schemas()
    print("Checking documented scenario counts...")
    check_scenario_counts()
    print("Checking for conflicting duplicate result files...")
    check_duplicate_result_files()
    print("Checking README.md references resolve...")
    check_readme_references_exist()
    print("Checking Python syntax across all included scripts...")
    check_python_syntax()

    print()
    print(f"=== {len(FAILURES)} failure(s), {len(WARNINGS)} warning(s) ===")
    for w in WARNINGS:
        print("WARN:", w)
    for f in FAILURES:
        print("FAIL:", f)

    if FAILURES:
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
