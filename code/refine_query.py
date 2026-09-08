#!/usr/bin/env python3
"""Interpret a user's correction to a previous answer and reformulate the retrieval query.

Closes the loop the report's limitations flagged: answer generation was implemented but
never measured at scale, and the assistant had no way to use a user's own feedback to
retrieve again. This module does one narrow thing - given the original question, the
system's previous answer (with its citations), and the user's correction, ask an LLM to
diagnose what went wrong and produce a better retrieval query - and returns that diagnosis
so the caller can decide whether to re-retrieve, not silently re-retrieve on its behalf.

The reformulated query is deliberately NOT the correction text itself. A user's correction
("no, I mean the old regime") names what is wrong, not necessarily good retrieval
vocabulary; treating it as the query verbatim conflates "what the user said" with "what
should be searched for". The model is asked to produce a self-contained query that
reflects the corrected intent, referencing the original question's subject.
"""
from __future__ import annotations

import json
import os

REFINE_SYSTEM_PROMPT = """A user asked a UK public procurement law question, received an answer, and \
pushed back on it. Diagnose what the correction actually means, then produce ONE self-contained \
retrieval query that reflects the corrected intent - not the correction text verbatim, but a proper \
question a legal retrieval system should search for next.

Diagnose which of these the correction indicates (pick the best fit, one value):
- WRONG_REGIME: the answer used the wrong legal regime (current vs legacy PCR2015, or vice versa)
- WRONG_PROVISION: the answer addressed a different, related legal concept than the one asked about
- TOO_GENERAL: the answer was correct in kind but not specific enough (general guidance instead of the exact rule)
- MISSING_ASPECT: the user wants an additional aspect of the same question answered, not a correction
- DIFFERENT_QUESTION: the correction is actually a new, unrelated question
- UNCLEAR: the correction does not give enough information to act on

Return JSON only: {"diagnosis": "...", "reasoning": "one sentence", "new_query": "..."}"""


def refine(original_query: str, previous_answer: str, correction: str, model: str = "gpt-4o-mini") -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=60.0, max_retries=3)

    payload = {
        "original_question": original_query,
        "previous_answer": previous_answer,
        "user_correction": correction,
    }
    resp = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "system", "content": REFINE_SYSTEM_PROMPT},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("original_query")
    ap.add_argument("previous_answer")
    ap.add_argument("correction")
    ap.add_argument("--model", default="gpt-4o-mini")
    a = ap.parse_args()
    result = refine(a.original_query, a.previous_answer, a.correction, a.model)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
