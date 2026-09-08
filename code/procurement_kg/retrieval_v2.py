"""Profile-driven hybrid retrieval.

Separate module by design: `retriever.HybridRetriever` continues to serve the frozen
baseline unchanged, so baseline_v1 results stay reproducible while this path evolves.

What differs from the baseline, and why (each traceable to a measured defect):

* Contentless nodes are never returned as evidence. 24.9% of the corpus has no text at all,
  and every structural node - section, subsection, paragraph, document - is among them.
* Graph traversal passes *through* those empty containers instead of stopping at them. In the
  baseline, expanding from a statement reached only its own empty parent; transit makes the
  sibling provisions of a subsection reachable, which is the case that actually matters.
* Graph hits join fusion as a third ranked channel. In the baseline a graph node's score was
  seed_score x relation_weight x decay, structurally below the top-k cutoff, so graph
  expansion could never influence an answer.
* Authority is inherited from the source document, so the prior applies to 99.3% of nodes
  rather than 16.1%.
* Duplicate text is collapsed. 31% of texted nodes share text with another node, and the
  baseline spent up to three quarters of its context window on repeats.
* A failed semantic channel is reported, never silently swallowed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .graph_store import GraphStore
from .node_features import EMPTY, AuthorityResolver, content_class, normalized_text_key
from .retrieval_profile import RetrievalProfile, get_profile

if TYPE_CHECKING:
    from .embeddings import OpenAIEmbedder
    from .vector_store import QdrantVectorStore


@dataclass
class Candidate:
    node_id: str
    node: dict[str, Any]
    channels: list[str] = field(default_factory=list)
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    semantic_score: float | None = None
    graph_rank: int | None = None
    fusion_score: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)
    final_score: float = 0.0
    graph_path: list[dict[str, Any]] = field(default_factory=list)
    authority: dict[str, Any] = field(default_factory=dict)
    content_class: str = ""
    duplicates_absorbed: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "score": round(self.final_score, 8),
            "fusion_score": round(self.fusion_score, 8),
            "channels": self.channels,
            "ranks": {
                "lexical": self.lexical_rank,
                "semantic": self.semantic_rank,
                "graph": self.graph_rank,
            },
            "weights_applied": {k: round(v, 4) for k, v in self.weights.items()},
            "content_class": self.content_class,
            "authority": self.authority,
            "graph_path": self.graph_path,
            "duplicates_absorbed": self.duplicates_absorbed,
            "node": self.node,
        }


@dataclass
class RetrievalResult:
    """Results plus everything needed to explain and reproduce them."""

    query: str
    profile: str
    profile_fingerprint: str
    results: list[Candidate]
    diagnostics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "profile": self.profile,
            "profile_fingerprint": self.profile_fingerprint,
            "count": len(self.results),
            "diagnostics": self.diagnostics,
            "results": [candidate.as_dict() for candidate in self.results],
        }


class ProfiledRetriever:
    def __init__(
        self,
        graph: GraphStore,
        embedder: "OpenAIEmbedder | None" = None,
        vectors: "QdrantVectorStore | None" = None,
        profile: RetrievalProfile | str = "hybrid_v2",
    ):
        self.graph = graph
        self.embedder = embedder
        self.vectors = vectors
        self.profile = get_profile(profile) if isinstance(profile, str) else profile
        self.authority = AuthorityResolver(graph)

    # ---------- evidence eligibility ----------

    def _is_evidence(self, node: dict[str, Any], profile: RetrievalProfile) -> bool:
        klass = content_class(node, min_words=profile.min_words)
        if profile.require_text and klass == EMPTY:
            return False
        weight = profile.node_type_weights.get(
            str(node.get("node_type")), profile.default_node_type_weight
        )
        return weight > 0

    # ---------- candidate channels ----------

    def _lexical(self, query: str, profile: RetrievalProfile, **filters) -> list[dict[str, Any]]:
        hits = self.graph.lexical_search(query, limit=profile.lexical_top_k, **filters)
        return [{"node_id": hit.node_id, "node": hit.node} for hit in hits]

    def _semantic(
        self, query: str, profile: RetrievalProfile, **filters
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.embedder or not self.vectors:
            return [], "semantic channel not configured (no embedder or vector store)"
        try:
            vector = self.embedder.embed_query(query)
            rows = self.vectors.search(vector, limit=profile.vector_top_k, **filters)
            return rows, None
        except Exception as exc:  # reported, never silently swallowed
            return [], f"{type(exc).__name__}: {exc}"

    # ---------- graph expansion with transit ----------

    def _expand(
        self, seeds: list[str], profile: RetrievalProfile
    ) -> dict[str, dict[str, Any]]:
        """BFS from the seeds, emitting only content-bearing nodes.

        An empty container is transited rather than emitted: its own children (the seed's
        siblings) are the useful destination, and they sit one hop beyond it.
        """
        if not profile.graph_enabled or not seeds:
            return {}

        allowed = (
            set(profile.allowed_relations)
            if profile.allowed_relations is not None
            else set(profile.relation_weights)
        )
        seed_positions = {node_id: index for index, node_id in enumerate(seeds)}
        found: dict[str, dict[str, Any]] = {}
        visited: set[str] = set(seeds)
        # frontier item: (node_id, seed_id, score, path, semantic_hops, transit_depth)
        frontier: list[tuple[str, str, float, list[dict[str, Any]], int, int]] = [
            (node_id, node_id, 1.0, [], 0, 0) for node_id in seeds
        ]

        while frontier and len(found) < profile.max_expanded_nodes:
            edges = self.graph.edges_for(
                [item[0] for item in frontier],
                relations=allowed,
                limit_per_node=profile.per_node_edge_limit,
            )
            by_source: dict[str, list[dict[str, Any]]] = {}
            for edge in edges:
                by_source.setdefault(edge["from_id"], []).append(edge)

            neighbour_ids = {
                edge["neighbor_id"]
                for edge_list in by_source.values()
                for edge in edge_list
                if edge["neighbor_id"] not in visited
            }
            if not neighbour_ids:
                break
            nodes = self.graph.get_nodes(neighbour_ids)
            next_frontier: list[tuple[str, str, float, list[dict[str, Any]], int, int]] = []

            for current_id, seed_id, score, path, semantic_hops, depth in frontier:
                for edge in by_source.get(current_id, []):
                    neighbour_id = edge["neighbor_id"]
                    if neighbour_id in visited:
                        continue
                    node = nodes.get(neighbour_id)
                    if not node:
                        continue
                    step = {
                        "hop": depth + 1,
                        "semantic_hop": semantic_hops,
                        "from": current_id,
                        "relation": edge["relation"],
                        "provenance": edge["provenance"],
                        "to": neighbour_id,
                    }
                    new_path = path + [step]

                    if self._is_evidence(node, profile):
                        relation_weight = profile.relation_weights.get(edge["relation"], 0.0)
                        if relation_weight <= 0:
                            continue
                        visited.add(neighbour_id)
                        new_score = score * relation_weight * (profile.hop_decay ** semantic_hops)
                        if len(found) < profile.max_expanded_nodes:
                            found[neighbour_id] = {
                                "node": node,
                                "score": new_score,
                                "seed": seed_id,
                                "seed_position": seed_positions.get(seed_id, 999),
                                "path": new_path,
                                "semantic_hops": semantic_hops + 1,
                            }
                        # a content node may itself lead onward (cross-references)
                        if semantic_hops + 1 < profile.max_hops and depth + 1 < profile.max_transit_depth:
                            next_frontier.append(
                                (neighbour_id, seed_id, new_score, new_path, semantic_hops + 1, depth + 1)
                            )
                    elif profile.transit_through_empty and depth + 1 < profile.max_transit_depth:
                        # structural container: walk through it, do not spend a semantic hop
                        visited.add(neighbour_id)
                        next_frontier.append(
                            (
                                neighbour_id,
                                seed_id,
                                score * profile.transit_weight,
                                new_path,
                                semantic_hops,
                                depth + 1,
                            )
                        )
            frontier = next_frontier
        return found

    # ---------- scoring ----------

    def _apply_weights(self, candidate: Candidate, profile: RetrievalProfile) -> None:
        node = candidate.node
        authority = self.authority.resolve(node)
        candidate.authority = authority.as_dict()
        candidate.content_class = content_class(node, min_words=profile.min_words)

        type_weight = profile.node_type_weights.get(
            str(node.get("node_type")), profile.default_node_type_weight
        )
        authority_weight = profile.authority_weights.get(
            str(authority.authority_class), profile.default_authority_weight
        )
        content_weight = profile.content_class_weights.get(candidate.content_class, 1.0)
        status_weight = (
            profile.repealed_penalty
            if node.get("status") in {"repealed", "revoked", "prospective"}
            else 1.0
        )
        candidate.weights = {
            "node_type": type_weight,
            "authority": authority_weight,
            "content_class": content_weight,
            "status": status_weight,
        }
        candidate.final_score = (
            candidate.fusion_score
            * type_weight
            * authority_weight
            * content_weight
            * status_weight
        )

    # ---------- entry point ----------

    def search(
        self,
        query: str,
        profile: RetrievalProfile | str | None = None,
        limit: int | None = None,
        semantic: bool = True,
        node_types: list[str] | None = None,
        authority_classes: list[str] | None = None,
    ) -> RetrievalResult:
        active = self.profile if profile is None else (
            get_profile(profile) if isinstance(profile, str) else profile
        )
        if not query.strip():
            return RetrievalResult(query, active.name, active.fingerprint(), [], {"empty_query": True})

        filters = {"node_types": node_types, "authority_classes": authority_classes}
        lexical = self._lexical(query, active, **filters)
        semantic_rows: list[dict[str, Any]] = []
        semantic_error: str | None = None
        if semantic:
            semantic_rows, semantic_error = self._semantic(query, active, **filters)

        candidates: dict[str, Candidate] = {}

        def ensure(node_id: str, node: dict[str, Any]) -> Candidate:
            if node_id not in candidates:
                candidates[node_id] = Candidate(node_id=node_id, node=node)
            return candidates[node_id]

        # channel 1: lexical
        for rank, row in enumerate(lexical, start=1):
            if not self._is_evidence(row["node"], active):
                continue
            candidate = ensure(row["node_id"], row["node"])
            candidate.lexical_rank = rank
            candidate.channels.append("lexical")
            candidate.fusion_score += active.lexical_weight / (active.rrf_k + rank)

        # channel 2: semantic
        if semantic_rows:
            nodes = self.graph.get_nodes([row["node_id"] for row in semantic_rows])
            for rank, row in enumerate(semantic_rows, start=1):
                node = nodes.get(row["node_id"])
                if not node or not self._is_evidence(node, active):
                    continue
                candidate = ensure(row["node_id"], node)
                candidate.semantic_rank = rank
                candidate.semantic_score = row.get("score")
                candidate.channels.append("semantic")
                candidate.fusion_score += active.semantic_weight / (active.rrf_k + rank)

        # channel 3: graph expansion, seeded from the current best
        seeds = [
            node_id
            for node_id, _ in sorted(
                ((c.node_id, c.fusion_score) for c in candidates.values()),
                key=lambda item: item[1],
                reverse=True,
            )[: active.seed_count]
        ]
        expanded = self._expand(seeds, active)
        for rank, (node_id, info) in enumerate(
            sorted(expanded.items(), key=lambda kv: kv[1]["score"], reverse=True), start=1
        ):
            candidate = ensure(node_id, info["node"])
            candidate.graph_rank = rank
            if "graph" not in candidate.channels:
                candidate.channels.append("graph")
            candidate.graph_path = info["path"]
            candidate.fusion_score += active.graph_weight / (active.rrf_k + rank)

        for candidate in candidates.values():
            self._apply_weights(candidate, active)

        ordered = sorted(candidates.values(), key=lambda c: c.final_score, reverse=True)

        # content-level deduplication: keep the best-scoring copy, record the rest
        duplicates_removed = 0
        if active.deduplicate_by_text:
            seen: dict[str, Candidate] = {}
            deduped: list[Candidate] = []
            for candidate in ordered:
                text = str(candidate.node.get("text") or "")
                if active.dedup_strategy == "normalized":
                    key = normalized_text_key(text) or candidate.node_id
                else:
                    key = str(candidate.node.get("text_hash") or text.strip() or candidate.node_id)
                if key in seen:
                    seen[key].duplicates_absorbed.append(candidate.node_id)
                    duplicates_removed += 1
                    continue
                seen[key] = candidate
                deduped.append(candidate)
            ordered = deduped

        final_limit = limit or active.final_top_k
        diagnostics = {
            "lexical_candidates": len(lexical),
            "semantic_candidates": len(semantic_rows),
            "semantic_requested": semantic,
            "semantic_available": bool(semantic_rows),
            "semantic_error": semantic_error,
            "degraded_to_lexical_only": bool(semantic and not semantic_rows),
            "graph_seeds": seeds[:5],
            "graph_expanded_nodes": len(expanded),
            "candidates_before_dedup": len(candidates),
            "duplicates_removed": duplicates_removed,
            "returned": min(final_limit, len(ordered)),
            "authority_sources_known": self.authority.source_count,
        }
        return RetrievalResult(
            query=query,
            profile=active.name,
            profile_fingerprint=active.fingerprint(),
            results=ordered[:final_limit],
            diagnostics=diagnostics,
        )
