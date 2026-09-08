from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .retriever import HybridRetriever


def load_questions(path: str | Path) -> list[dict[str, Any]]:
    questions = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("question") or not row.get("relevant_node_ids"):
                raise ValueError(f"{path}:{line_number} needs question and relevant_node_ids")
            questions.append(row)
    return questions


def evaluate_retrieval(
    retriever: HybridRetriever,
    questions: list[dict[str, Any]],
    k: int = 10,
    semantic: bool = True,
    candidates: int = 40,
    graph_hops: int = 1,
) -> dict[str, Any]:
    reciprocal_ranks: list[float] = []
    recalls: list[float] = []
    details = []
    for row in questions:
        relevant = set(row["relevant_node_ids"])
        results = retriever.search(
            row["question"],
            limit=k,
            candidates=candidates,
            graph_hops=graph_hops,
            semantic=semantic,
        )
        retrieved = [result.node_id for result in results]
        first_rank = next(
            (rank for rank, node_id in enumerate(retrieved, start=1) if node_id in relevant),
            None,
        )
        hits = relevant.intersection(retrieved)
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)
        recalls.append(len(hits) / len(relevant))
        details.append(
            {
                "question": row["question"],
                "relevant": sorted(relevant),
                "retrieved": retrieved,
                "first_relevant_rank": first_rank,
                "recall": len(hits) / len(relevant),
            }
        )
    size = len(questions)
    return {
        "questions": size,
        "k": k,
        "semantic": semantic,
        "mrr": sum(reciprocal_ranks) / size if size else 0.0,
        "recall_at_k": sum(recalls) / size if size else 0.0,
        "details": details,
    }
