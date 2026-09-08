#!/usr/bin/env python3
"""Fetch, extract and re-chunk every PDF in the corpus. Resumable, staged, not ingested.

Replaces the lane that measured 88% INCOMPLETE - 30.7% of the corpus by chunks and 50.5% by
characters - where the chunker's smallest unit was a whole page and 87 of 89 pages in a
sample document began mid-sentence.

Per document: fetch -> PyMuPDF page text (lossless, paragraph-joined, hyphens repaired) ->
model emits fully-formed chunks -> verified two ways. Per-chunk fidelity catches fabrication;
source recall catches omission, which fidelity alone cannot see.

Each stage writes to disk and is skipped if already done, so the run resumes after any
interruption. Nothing enters the index.
"""
from __future__ import annotations

import argparse, csv, json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--urls", default="evaluation/pdf_extraction_samples/all_pdf_urls.csv", type=Path)
    ap.add_argument("--pdf-dir", default="data/pdf_raw", type=Path)
    ap.add_argument("--pages-dir", default="data/pdf_pages", type=Path)
    ap.add_argument("--chunks-dir", default="data/pdf_chunks_mini", type=Path)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-mb", type=float, default=60.0)
    ap.add_argument("--pause", type=float, default=0.4)
    a = ap.parse_args()
    for d in (a.pdf_dir, a.pages_dir, a.chunks_dir):
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader((ROOT / a.urls).open(encoding="utf-8")))
    if a.limit:
        rows = rows[: a.limit]
    print(f"documents: {len(rows)}", flush=True)

    import requests
    from extract_pdf_pages import extract as extract_pages
    sess = requests.Session()
    sess.headers.update({"User-Agent": "procurement-kg-rag research (MSc, Univ. of Manchester)"})

    done = fetched = extracted = chunked = skipped = failed = 0
    log = []
    for i, r in enumerate(rows, 1):
        did = r["document_id"]; url = r["url"]
        pdf = ROOT / a.pdf_dir / f"{did}.pdf"
        pages = ROOT / a.pages_dir / f"{did}.pages.json"
        chunks = ROOT / a.chunks_dir / f"{did}.chunks.json"
        if chunks.exists():
            skipped += 1
            if i % 25 == 0: print(f"  [{i}/{len(rows)}] {skipped} already done", flush=True)
            continue
        try:
            if not pdf.exists():
                resp = sess.get(url, timeout=180)
                resp.raise_for_status()
                if len(resp.content) > a.max_mb * 1e6:
                    log.append({"document_id": did, "status": "skipped_too_large",
                                "mb": round(len(resp.content) / 1e6, 1)})
                    print(f"  [{i}] SKIP {did} ({len(resp.content)/1e6:.0f} MB > {a.max_mb})", flush=True)
                    continue
                pdf.write_bytes(resp.content); fetched += 1
                time.sleep(a.pause)
            if not pages.exists():
                rec = extract_pages(pdf)
                pages.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
                extracted += 1
            # Cap per-document wall time. A document that cannot finish is skipped and
            # recorded rather than allowed to hold the queue.
            budget = max(180, int(len(pages.read_text(encoding="utf-8")) / 9000) * 90 + 180)
            out = subprocess.run(
                [sys.executable, str(ROOT / "chunk_pdf_text.py"), str(pages),
                 "--model", a.model, "--out", str(a.chunks_dir)],
                capture_output=True, text=True, cwd=str(ROOT), env={**os.environ},
                timeout=budget)
            if not chunks.exists():
                raise RuntimeError((out.stderr or out.stdout or "no output")[-200:])
            d = json.loads(chunks.read_text(encoding="utf-8"))
            chunked += 1; done += 1
            log.append({"document_id": did, "status": "ok", "chunks": d["chunks"],
                        "source_recall": d.get("source_recall"),
                        "fidelity": d["fidelity"]["mean_coverage"]})
            print(f"  [{i}/{len(rows)}] {did[:14]} {d['chunks']:4d} chunks  "
                  f"recall {d.get('source_recall')}  fid {d['fidelity']['mean_coverage']}", flush=True)
        except subprocess.TimeoutExpired:
            failed += 1
            log.append({"document_id": did, "status": "timeout"})
            print(f"  [{i}/{len(rows)}] TIMEOUT {did[:14]} - skipped", flush=True)
            continue
        except Exception as exc:
            failed += 1
            log.append({"document_id": did, "status": "failed", "error": str(exc)[:180]})
            print(f"  [{i}/{len(rows)}] FAILED {did[:14]}: {str(exc)[:110]}", flush=True)

    rep = {"generated_at": datetime.now(timezone.utc).isoformat(), "model": a.model,
           "documents": len(rows), "fetched": fetched, "extracted": extracted,
           "chunked": chunked, "already_done": skipped, "failed": failed,
           "ingested": False, "log": log}
    (ROOT / "evaluation" / "pdf_pipeline_report.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")
    print(f"\nchunked {chunked}, skipped {skipped}, failed {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
