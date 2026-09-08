"""Versioned retrieval configurations.

Retrieval behaviour is an experimental variable, so every parameter lives in a named,
fingerprinted profile that a run manifest can record and a later run can reload. Profiles are
immutable once an experiment references them; a changed parameter means a new profile.

`baseline_v1` documents the frozen baseline exactly. It is served by the original
`HybridRetriever` and is never executed through the v2 path, so it cannot drift.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from .node_features import EMPTY, FRAGMENT, SHORT, SUBSTANTIVE

# Node types that hold text. Everything else is structure: useful to traverse through,
# useless as evidence, because containers in this corpus carry no text at all.
CONTENT_NODE_TYPES = {
    "legal_statement": 1.00,
    "web_statement": 0.85,
    "pdf_statement": 0.80,
    "table_row_statement": 0.70,
    "manifest_statement": 0.40,
}

# Applied to the node's *effective* authority, after inheritance from its source document.
AUTHORITY_WEIGHTS = {
    "primary_legislation": 1.30,
    "secondary_legislation": 1.20,
    "statutory_policy_statement": 1.00,
    "official_guidance": 0.90,
    "official_operational_or_practice_material": 0.80,
    "treaty_or_international_instrument": 0.70,
    "legacy_eu_law": 0.60,
    "independent_commentary": 0.50,
    "supporting_material": 0.50,
}

# How usable the text is as standalone evidence.
CONTENT_CLASS_WEIGHTS = {
    SUBSTANTIVE: 1.00,
    FRAGMENT: 0.75,
    SHORT: 0.45,
    EMPTY: 0.00,
}

# Typed traversal. `contains` is structural transit, not a legal relationship, so it is
# weighted low; it earns its place only because passing through an empty container is the
# only route to a sibling provision.
RELATION_WEIGHTS = {
    "cross_refers_to": 1.00,
    "cites_legislation": 0.90,
    "amends": 0.85,
    "commences": 0.80,
    "applies_or_modifies": 0.80,
    "modifies": 0.75,
    "affects": 0.70,
    "links_to": 0.40,
    "mentions_document": 0.30,
    "contains": 0.35,
}


@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    description: str

    # candidate generation
    lexical_top_k: int = 60
    vector_top_k: int = 60

    # fusion
    rrf_k: int = 60
    lexical_weight: float = 0.9
    semantic_weight: float = 1.0
    graph_weight: float = 0.45

    # what may be returned as evidence
    require_text: bool = True
    min_words: int = 6
    node_type_weights: dict[str, float] = field(default_factory=lambda: dict(CONTENT_NODE_TYPES))
    content_class_weights: dict[str, float] = field(
        default_factory=lambda: dict(CONTENT_CLASS_WEIGHTS)
    )
    authority_weights: dict[str, float] = field(default_factory=lambda: dict(AUTHORITY_WEIGHTS))
    default_authority_weight: float = 0.80
    default_node_type_weight: float = 0.0  # unknown/container types are not evidence
    repealed_penalty: float = 0.82

    # graph expansion
    graph_enabled: bool = True
    # Semantic hops: content node -> content node. Transiting an empty structural container
    # does NOT consume this budget, because in this corpus two sibling provisions are four
    # structural steps apart (statement -> subsection -> section -> subsection -> statement)
    # and would otherwise be unreachable at any sane hop count.
    max_hops: int = 2
    max_transit_depth: int = 6
    transit_weight: float = 0.85
    hop_decay: float = 0.60
    relation_weights: dict[str, float] = field(default_factory=lambda: dict(RELATION_WEIGHTS))
    allowed_relations: tuple[str, ...] | None = None  # None = every relation with a weight
    transit_through_empty: bool = True
    seed_count: int = 12
    max_expanded_nodes: int = 40
    per_node_edge_limit: int = 60

    # output
    deduplicate_by_text: bool = True
    # "exact"      - identical text_hash only (what the baseline would have caught)
    # "normalized" - also collapses whitespace, unicode punctuation and case, which is
    #                required because the same passage differs by one character between
    #                its HTML and PDF extractions
    dedup_strategy: str = "normalized"
    final_top_k: int = 16

    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict:
        return {**asdict(self), "fingerprint": self.fingerprint()}


BASELINE_V1 = RetrievalProfile(
    name="baseline_v1",
    description=(
        "Frozen baseline. Documented here for run manifests only; it is executed by the "
        "original HybridRetriever, never by the v2 path. lexical/vector top-k 40, RRF k=60, "
        "weights 0.9/1.0, 1 hop over all relations, no type or content filtering, "
        "authority prior read from the node itself (inoperative for 84% of nodes), "
        "no content deduplication, final top-k 12/16."
    ),
    lexical_top_k=40,
    vector_top_k=40,
    graph_weight=0.0,
    require_text=False,
    min_words=0,
    node_type_weights={},
    content_class_weights={},
    authority_weights={},
    default_node_type_weight=1.0,
    default_authority_weight=1.0,
    max_hops=1,
    deduplicate_by_text=False,
    dedup_strategy="exact",
    seed_count=12,
    per_node_edge_limit=30,
)

HYBRID_V2 = RetrievalProfile(
    name="hybrid_v2",
    description=(
        "Repairs the four measured baseline defects: authority inherited from the source "
        "document (coverage 16.1% -> 99.3%); contentless container nodes excluded as evidence "
        "and traversed through instead, which is what finally makes sibling provisions "
        "reachable; typed relation weights; graph results fused as a first-class channel "
        "rather than a score that cannot compete; content-level deduplication."
    ),
)

PROFILES: dict[str, RetrievalProfile] = {p.name: p for p in (BASELINE_V1, HYBRID_V2)}


def get_profile(name: str) -> RetrievalProfile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(
            f"Unknown retrieval profile {name!r}. Available: {', '.join(sorted(PROFILES))}"
        ) from None
