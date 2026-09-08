#!/usr/bin/env python3
"""
Verify the frozen evaluation record (prw_freeze_record.json) against the actual code/config
files included in this bundle. Recomputes SHA-256 for every file the freeze record names and
compares against the recorded hash. Exits non-zero on any mismatch.

Usage (from the bundle root):
    python3 scripts/verify_freeze.py
"""
import hashlib
import json
import sys
from pathlib import Path

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
FREEZE_RECORD = BUNDLE_ROOT / "results" / "final_reports" / "prw_freeze_record.json"
PRW_ROOT = BUNDLE_ROOT / "code" / "procurement_research_workbench_v1"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def main() -> int:
    if not FREEZE_RECORD.exists():
        print(f"FAIL: freeze record not found at {FREEZE_RECORD}")
        return 1
    record = json.loads(FREEZE_RECORD.read_text())

    failures = []
    checked = 0

    for rel_path, expected_hash in record.get("code_hashes", {}).items():
        p = PRW_ROOT / rel_path
        checked += 1
        if not p.exists():
            failures.append(f"MISSING: {rel_path}")
            continue
        actual = sha256_file(p)
        if actual != expected_hash:
            failures.append(f"HASH MISMATCH: {rel_path} (expected {expected_hash[:16]}..., got {actual[:16]}...)")

    for i, config_hash in enumerate(record.get("config_hashes", [])):
        # config_hashes in the freeze record are positional against whatever --configs list was
        # passed at freeze time; this bundle includes retrieval.json and models.json under
        # code/procurement_research_workbench_v1/configs/.
        candidates = list((PRW_ROOT / "configs").glob("*.json"))
        checked += 1
        if not any(sha256_file(c) == config_hash for c in candidates):
            failures.append(f"CONFIG HASH NOT MATCHED BY ANY FILE IN configs/: index {i}, expected {config_hash[:16]}...")

    print(f"Checked {checked} hashes from {FREEZE_RECORD.relative_to(BUNDLE_ROOT)}.")
    if failures:
        print(f"FAIL: {len(failures)} mismatch(es):")
        for f in failures:
            print("  -", f)
        return 1

    print("PASS: all frozen-source hashes match the included code exactly.")
    print("Note: this verifies code/config integrity only, not that a fresh LLM call would")
    print("reproduce prior judgments (LLM calls are not deterministic -- see")
    print("environment/environment_notes.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
