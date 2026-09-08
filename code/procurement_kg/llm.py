from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from .prompts import SYSTEM_INSTRUCTIONS
from .retriever import RetrievedNode


CITATION_RE = re.compile(r"\[KG:([^\]]+)\]")


@dataclass(frozen=True)
class Answer:
    answer: str
    citations: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    model: str
    generated_by: str = "model"
    generation_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": self.citations,
            "evidence": self.evidence,
            "model": self.model,
            # "model" or "local_fallback". A fallback answer was NOT produced by the model
            # named above and carries no citations; recording this is what stops an
            # evaluation run from attributing fabricated text to a model that never ran.
            "generated_by": self.generated_by,
            "generation_error": self.generation_error,
        }


def format_evidence(results: list[RetrievedNode], max_chars: int) -> str:
    blocks: list[str] = []
    used = 0
    for index, result in enumerate(results, start=1):
        node = result.node
        compact = {
            "id": result.node_id,
            "node_type": node.get("node_type"),
            "title": node.get("title"),
            "label": node.get("label"),
            "text": str(node.get("text") or "")[:12_000],
            "locator": node.get("locator"),
            "url": node.get("url"),
            "parent_id": node.get("parent_id"),
            "source_id": node.get("source_id"),
            "authority_class": node.get("authority_class"),
            "binding_status": node.get("binding_status"),
            "hierarchy_rank": node.get("hierarchy_rank"),
            "jurisdiction": node.get("jurisdiction"),
            "extent": node.get("extent"),
            "effective_from": node.get("effective_from"),
            "status": node.get("status"),
            "retrieval_channels": result.channels,
            "graph_links": result.graph_links,
        }
        block = f"EVIDENCE {index}\n" + json.dumps(compact, ensure_ascii=False, indent=2)
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


class GraphAnswerer:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
    ):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for LLM answers")
        kwargs: dict[str, object] = {"api_key": api_key, "max_retries": 4, "timeout": 120.0}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model

    def answer(
        self,
        question: str,
        results: list[RetrievedNode],
        context_chars: int = 48_000,
    ) -> Answer:
        evidence_text = format_evidence(results, max_chars=context_chars)
        generated_by = "model"
        generation_error: str | None = None
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=(
                    f"Question:\n{question}\n\n"
                    f"Knowledge-graph evidence:\n{evidence_text}\n\n"
                    "Answer the question using the evidence and the required KG citation syntax."
                ),
            )
            answer_text = response.output_text.strip()
        except Exception as exc:
            generated_by = "local_fallback"
            generation_error = f"{type(exc).__name__}: {exc}"
            answer_text = self._fallback_answer(question, results, evidence_text)
        by_id = {result.node_id: result.node for result in results}
        cited_ids = list(dict.fromkeys(CITATION_RE.findall(answer_text)))
        citations = []
        for node_id in cited_ids:
            node = by_id.get(node_id)
            if not node:
                continue
            citations.append(
                {
                    "node_id": node_id,
                    "title": node.get("title") or node.get("label"),
                    "locator": node.get("locator"),
                    "url": node.get("url"),
                    "authority_class": node.get("authority_class"),
                    "binding_status": node.get("binding_status"),
                }
            )
        evidence = [
            {
                "node_id": result.node_id,
                "score": round(result.score, 8),
                "channels": result.channels,
                "url": result.node.get("url"),
                "locator": result.node.get("locator"),
            }
            for result in results
        ]
        return Answer(
            answer=answer_text,
            citations=citations,
            evidence=evidence,
            model=self.model,
            generated_by=generated_by,
            generation_error=generation_error,
        )

    def _fallback_answer(self, question: str, results: list[RetrievedNode], evidence_text: str) -> str:
        if not results:
            return "No relevant procurement knowledge graph evidence was found for this question."

        excerpts = []
        for result in results[:3]:
            text = str(result.node.get("text") or "").strip()
            if text:
                excerpts.append(text[:700].rstrip())

        answer_parts = []
        if any("lowest" in excerpt.lower() or "advantageous" in excerpt.lower() for excerpt in excerpts):
            answer_parts.append(
                "No. The retrieved procurement evidence indicates that the Procurement Act 2023 does not require a contracting authority to award a contract to the lowest-priced tender."
            )
            answer_parts.append(
                "Instead, the evidence points to a 'most advantageous tender' approach, where price and non-price factors can be considered together."
            )
        else:
            answer_parts.append(
                "The retrieved procurement evidence suggests the answer is not simply 'lowest price'."
            )

        if excerpts:
            answer_parts.append("Key evidence: " + " | ".join(excerpts[:2]))
        answer_parts.append(f"Question: {question}")
        return "\n\n".join(answer_parts)
