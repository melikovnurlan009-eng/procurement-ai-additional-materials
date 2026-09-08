"""Minimal typed interfaces. Hidden evaluation requirements never enter runtime calls."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Protocol
from .io import digest

BINDING = {"PRIMARY_LEGISLATION", "SECONDARY_LEGISLATION"}
OFFICIAL = BINDING | {"OFFICIAL_GOVERNMENT_GUIDANCE", "OFFICIAL_TECHNICAL_GUIDANCE", "OFFICIAL_REGULATOR_GUIDANCE", "OFFICIAL_WORKFLOW", "PROCUREMENT_POLICY", "OFFICIAL_TRAINING", "OFFICIAL_SPECIALIST_GUIDANCE", "OFFICIAL_PA23_TECHNICAL_GUIDANCE", "OFFICIAL_PRACTICE_GUIDANCE"}

@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_message: str
    history: tuple[dict, ...] = ()
    as_of: str = "2026-09-07"

    @classmethod
    def from_public(cls, obj: dict) -> "Scenario":
        # Intentional allowlist; silently passing gold through **kwargs is forbidden.
        forbidden = {"requirements", "gold_evidence", "reference_evidence", "qrels", "expected_answer", "gold_legal_node_ids"}
        if forbidden.intersection(obj):
            raise ValueError("Runtime scenario contains hidden evaluation information")
        return cls(obj["scenario_id"], obj["user_message"], tuple(obj.get("history", [])), obj.get("as_of", "2026-09-07"))

@dataclass
class Evidence:
    chunk_id: str
    text: str
    citation: str = ""
    source_url: str = ""
    authority_class: str = "UNKNOWN"
    legal_regime: str = "UNKNOWN"
    jurisdiction: str = "UNKNOWN"
    canonical_ids: list[str] = field(default_factory=list)
    score: float = 0.0
    lane: str = "other"
    content_sha256: str = ""
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.chunk_id or not self.text.strip():
            raise ValueError("Evidence must have a real identifier and nonempty text")
        actual = digest(self.text)
        if self.content_sha256 and self.content_sha256 != actual:
            raise ValueError("Evidence text changed under an existing hash")
        self.content_sha256 = actual
        if self.authority_class in BINDING:
            self.lane = "legislation"

    @classmethod
    def from_dict(cls, row: dict) -> "Evidence":
        allowed = cls.__dataclass_fields__
        return cls(**{k: v for k, v in row.items() if k in allowed})

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass(frozen=True)
class SearchRequest:
    query: str
    mode: str = "legal"   # lexical, dense, hybrid, legal
    graph: bool = False
    candidates: int = 100
    depth: int = 20
    hops: int = 1
    fanout: int = 20
    target_anchor: str | None = None
    lane: str = "both"
    priors: bool = False

@dataclass
class SearchResponse:
    evidence: list[Evidence]
    trace: dict = field(default_factory=dict)

class Backend(Protocol):
    capabilities: set[str]
    def search(self, request: SearchRequest) -> SearchResponse: ...
    def expand_from(self, anchor: str, query: str, request: SearchRequest) -> SearchResponse: ...

class JsonModel(Protocol):
    def complete(self, system: str, payload: dict) -> dict: ...


def validate_requirement_set(spec: dict) -> None:
    reqs = spec.get("requirements", [])
    if not reqs:
        raise ValueError("No evaluator requirements")
    seen = set()
    for r in reqs:
        if r["id"] in seen:
            raise ValueError("Duplicate requirement id")
        seen.add(r["id"])
        if r["source_policy"] not in {"BINDING_REQUIRED", "OFFICIAL_ALLOWED", "ANY_SUPPORTED"}:
            raise ValueError("Invalid source policy")
        if not r.get("description"):
            raise ValueError("Empty requirement")
    if not any(r.get("mandatory", True) for r in reqs):
        raise ValueError("No mandatory requirements")
