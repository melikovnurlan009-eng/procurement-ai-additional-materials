#!/usr/bin/env python3
"""Query-side bridge from practitioner vocabulary to statutory vocabulary.

Motivation
----------
The evaluation showed retrieval collapsing on queries phrased as a practitioner would
phrase them rather than as the statute does: recall of 0.00-0.20 against 0.25-0.75 on
conventionally worded queries. The cause is not ranking but the first stage. "Blacklist"
and "debarment" are related by legal convention rather than by distributional similarity,
so an embedding model trained on general text does not bridge them, and graph expansion
cannot help because traversing a citation first requires retrieving something that makes
the citation.

This stage therefore acts BEFORE retrieval. It maps colloquial phrasing onto the terms the
legislation actually uses, so the lexical and dense channels have something to match.

Constraints
-----------
* The question is never rewritten or answered. The model returns terminology only.
* Expansion terms are appended to the query for retrieval; the original query is what is
  shown, logged and evaluated, so the change is confined to the matching stage.
* Every expansion is cached by query hash, making runs reproducible and cheap to repeat.
* Statutory locators already present in the query are preserved verbatim, since those are
  precisely the high-value rare tokens BM25 depends on.

Usage
-----
    python query_expansion.py --query "Can we blacklist a company?"
    python query_expansion.py --warm evaluation/eval_corpus_canonical.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPANSION_VERSION = "1.0.0"
PROMPT_VERSION = "statutory_vocabulary_v1"
DEFAULT_CACHE = Path("data/evaluation/query_expansion_cache.jsonl")

SYSTEM_PROMPT = """You map plain-English UK public procurement questions onto the vocabulary used in the legislation.

You are given a question. Return the statutory and official terminology that the answer would be written in, so a search engine can match the legislation.

Rules:
- Return TERMS ONLY. Never answer the question, never explain, never add commentary.
- Prefer the exact words used in the Procurement Act 2023, the Procurement Regulations 2024 and the Public Contracts Regulations 2015.
- Include the statutory term for any colloquialism. Examples of the mapping required:
  "blacklist" -> debarment, debarment list, excluded supplier
  "cooling off period" -> standstill period
  "goes bust" -> insolvency, excluded supplier
  "chop a contract into smaller pieces" -> estimated value, division into lots
  "buy directly without competition" -> direct award, direct award justification
  "tell the market what we plan to buy" -> pipeline notice, planned procurement notice
- If the question already uses statutory wording, return that wording.
- Include the relevant statutory concept nouns, not verbs or general words.
- 4 to 10 terms. No duplicates. No sentences."""

SCHEMA = {
    "type": "object",
    "properties": {
        "statutory_terms": {"type": "array", "items": {"type": "string"}},
        "likely_instruments": {"type": "array", "items": {"type": "string"}},
        "colloquialisms_detected": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["statutory_terms", "likely_instruments", "colloquialisms_detected"],
    "additionalProperties": False,
}

LOCATOR_RE = re.compile(r"\b(section|regulation|schedule|reg|s)\s*\d+[A-Za-z]?\b", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_key(query: str, model: str) -> str:
    return hashlib.sha256(f"{PROMPT_VERSION}|{model}|{query}".encode()).hexdigest()[:24]


class QueryExpander:
    """Cached statutory-vocabulary expansion. Falls back to the original query on error."""

    def __init__(self, model: str | None = None, cache_path: Path | None = None,
                 enabled: bool = True):
        self.model = model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        self.cache_path = cache_path or DEFAULT_CACHE
        self.enabled = enabled
        self._cache: dict[str, dict[str, Any]] = {}
        if self.cache_path.exists():
            for line in self.cache_path.open(encoding="utf-8"):
                if line.strip():
                    row = json.loads(line)
                    self._cache[row["key"]] = row
        self._client = None

    def _call(self, query: str) -> dict[str, Any]:
        from openai import OpenAI

        if self._client is None:
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": query}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "statutory_terms",
                                             "schema": SCHEMA, "strict": True}},
        )
        return json.loads(resp.choices[0].message.content)

    def expand(self, query: str) -> dict[str, Any]:
        if not self.enabled:
            return {"query": query, "expanded_query": query, "statutory_terms": [],
                    "source": "disabled"}
        key = cache_key(query, self.model)
        if key in self._cache:
            row = self._cache[key]
            return {**row, "source": "cache"}
        try:
            out = self._call(query)
        except Exception as exc:  # never let expansion break retrieval
            return {"query": query, "expanded_query": query, "statutory_terms": [],
                    "source": f"error:{type(exc).__name__}"}

        terms = [t.strip() for t in out.get("statutory_terms", []) if t.strip()]
        # Statutory locators in the original are the rare tokens BM25 relies on; keep them.
        locators = LOCATOR_RE.findall(query)
        expanded = query if not terms else f"{query} {' '.join(dict.fromkeys(terms))}"
        row = {
            "key": key, "query": query, "expanded_query": expanded,
            "statutory_terms": terms,
            "likely_instruments": out.get("likely_instruments", []),
            "colloquialisms_detected": out.get("colloquialisms_detected", []),
            "locators_preserved": bool(locators),
            "model": self.model, "prompt_version": PROMPT_VERSION,
            "expansion_version": EXPANSION_VERSION, "created_at": now_iso(),
        }
        self._cache[key] = row
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {**row, "source": "api"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--query")
    ap.add_argument("--warm", type=Path, help="pre-expand every query in a corpus JSONL")
    ap.add_argument("--model", default=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    ap.add_argument("--cache", default=DEFAULT_CACHE, type=Path)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    cache = args.cache if args.cache.is_absolute() else root / args.cache
    ex = QueryExpander(args.model, cache)

    if args.query:
        print(json.dumps(ex.expand(args.query), indent=2, ensure_ascii=False))
        return 0

    if args.warm:
        path = args.warm if args.warm.is_absolute() else root / args.warm
        rows = [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]
        stats = {"api": 0, "cache": 0, "error": 0, "with_colloquialism": 0}
        for r in rows:
            out = ex.expand(r["query"])
            src = out.get("source", "")
            stats["error" if src.startswith("error") else src] = \
                stats.get("error" if src.startswith("error") else src, 0) + 1
            if out.get("colloquialisms_detected"):
                stats["with_colloquialism"] += 1
        print(json.dumps({"queries": len(rows), **stats, "cache": str(cache.relative_to(root))},
                         indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
