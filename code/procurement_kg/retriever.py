from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .graph_store import GraphStore

if TYPE_CHECKING:
    from .embeddings import OpenAIEmbedder
    from .vector_store import QdrantVectorStore


RELATION_WEIGHTS = {
    "cites": 1.0,
    "cross_refers_to": 1.0,
    "amends": 1.0,
    "commences": 0.95,
    "implements": 0.95,
    "applies_to": 0.9,
    "interprets": 0.9,
    "contains": 0.72,
    "lists_source": 0.55,
    "related_to": 0.5,
}


@dataclass
class RetrievedNode:
    node_id: str
    score: float
    node: dict[str, Any]
    channels: list[str] = field(default_factory=list)
    graph_links: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "score": round(self.score, 8),
            "channels": self.channels,
            "graph_links": self.graph_links,
            "node": self.node,
        }


def reciprocal_rank_fusion(
    rankings: list[tuple[str, list[str], float]], k: int = 60
) -> tuple[dict[str, float], dict[str, list[str]]]:
    scores: dict[str, float] = {}
    channels: dict[str, list[str]] = {}
    for channel, node_ids, weight in rankings:
        for rank, node_id in enumerate(node_ids, start=1):
            scores[node_id] = scores.get(node_id, 0.0) + weight / (k + rank)
            channels.setdefault(node_id, []).append(channel)
    return scores, channels


def authority_multiplier(node: dict[str, Any]) -> float:
    """Small reranking prior, not a claim that rank alone resolves legal conflicts."""
    multiplier = 1.0
    if node.get("binding_status") == "binding":
        multiplier += 0.08
    rank = node.get("hierarchy_rank")
    if isinstance(rank, (int, float)) and rank > 0:
        multiplier += min(0.10, 0.10 / float(rank))
    if node.get("status") in {"repealed", "revoked", "prospective"}:
        multiplier *= 0.82
    return multiplier


class HybridRetriever:
    def __init__(
        self,
        graph: GraphStore,
        embedder: "OpenAIEmbedder | None" = None,
        vectors: "QdrantVectorStore | None" = None,
    ):
        self.graph = graph
        self.embedder = embedder
        self.vectors = vectors

    def search(
        self,
        query: str,
        limit: int = 12,
        candidates: int = 40,
        graph_hops: int = 1,
        semantic: bool = True,
        node_types: list[str] | None = None,
        authority_classes: list[str] | None = None,
    ) -> list[RetrievedNode]:
        if not query.strip():
            return []
        lexical = self.graph.lexical_search(
            query,
            limit=candidates,
            node_types=node_types,
            authority_classes=authority_classes,
        )
        vector_rows: list[dict[str, Any]] = []
        if semantic:
            if not self.embedder or not self.vectors:
                raise RuntimeError("Semantic search requires OPENAI_API_KEY and Qdrant")
            try:
                query_vector = self.embedder.embed_query(query)
                vector_rows = self.vectors.search(
                    query_vector,
                    limit=candidates,
                    node_types=node_types,
                    authority_classes=authority_classes,
                )
            except Exception:
                vector_rows = []

        if vector_rows:
            rankings = [
                ("semantic", [row["node_id"] for row in vector_rows], 1.0),
                ("lexical", [hit.node_id for hit in lexical], 0.9),
            ]
        else:
            rankings = [("lexical", [hit.node_id for hit in lexical], 0.9)]

        scores, channels = reciprocal_rank_fusion(rankings)
        lexical_nodes = {hit.node_id: hit.node for hit in lexical}
        all_nodes = self.graph.get_nodes(scores)
        all_nodes.update(lexical_nodes)

        ranked_seed_ids = sorted(scores, key=scores.get, reverse=True)[: min(12, candidates)]
        graph_links = self.graph.neighbors(ranked_seed_ids, hops=graph_hops)
        links_by_neighbor: dict[str, list[dict[str, Any]]] = {}
        for link in graph_links:
            neighbor_id = link["neighbor_id"]
            links_by_neighbor.setdefault(neighbor_id, []).append(link)
            relation_weight = RELATION_WEIGHTS.get(link["relation"], 0.45)
            source_score = max(scores.get(link["source"], 0.0), scores.get(link["target"], 0.0))
            graph_score = source_score * relation_weight * (0.58 ** link["depth"])
            if graph_score > scores.get(neighbor_id, 0.0):
                scores[neighbor_id] = graph_score
                channels.setdefault(neighbor_id, []).append("graph")

        missing_ids = [node_id for node_id in scores if node_id not in all_nodes]
        all_nodes.update(self.graph.get_nodes(missing_ids))

        output: list[RetrievedNode] = []
        for node_id, score in scores.items():
            node = all_nodes.get(node_id)
            if not node:
                continue
            output.append(
                RetrievedNode(
                    node_id=node_id,
                    score=score * authority_multiplier(node),
                    node=node,
                    channels=list(dict.fromkeys(channels.get(node_id, []))),
                    graph_links=links_by_neighbor.get(node_id, [])[:8],
                )
            )
        output.sort(key=lambda item: item.score, reverse=True)
        return output[:limit]
