"""Versioned construction of the text sent to the embedding model.

Why this exists
---------------
In baseline_v1 the embedded string was `graph_store.searchable_text()`, which wraps the legal
text in metadata scaffolding (node type, parent id, source id, official URL, authority class,
binding status, jurisdiction, extent, effective date, status). Measured over the frozen
corpus, that scaffolding is 4-5x larger than the legal text it wraps: median 104 tokens of
input for a median 21 tokens of provision text. Opaque identifiers and URLs cannot contribute
retrieval signal, and the categorical fields are already stored as Qdrant payload filters, so
removing them from the embedded text loses no filtering capability.

Research-integrity rules
------------------------
* `baseline_v1` reproduces the frozen behaviour EXACTLY and must never be edited.
* A change in what gets embedded is a new version, never an edit to an existing one.
* Every embedded vector records the input version that produced it, so an index can never be
  silently mixed. See `GraphStore.mark_embedded` and the `embedding_state` table.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

# Field order and human labels used by baseline_v1. Kept here verbatim so the baseline
# behaviour is documented in one place; graph_store.searchable_text remains the executable
# definition used for the FTS index.
BASELINE_FIELDS: tuple[tuple[str, str], ...] = (
    ("title", "Title"),
    ("label", "Label"),
    ("text", "Text"),
    ("locator", "Locator"),
    ("node_type", "Type"),
    ("parent_id", "Parent node"),
    ("source_id", "Source"),
    ("url", "Official URL"),
    ("authority_class", "Authority"),
    ("binding_status", "Binding status"),
    ("jurisdiction", "Jurisdiction"),
    ("extent", "Extent"),
    ("effective_from", "Effective from"),
    ("status", "Status"),
)

# Fields deliberately excluded from post-baseline versions, with the reason recorded so the
# decision is auditable rather than folkloric.
EXCLUSION_RATIONALE: dict[str, str] = {
    "node_type": "schema vocabulary (22 values such as 'legal_statement'); describes the parser, not the law",
    "parent_id": "opaque identifier; no natural-language content",
    "source_id": "opaque 16-hex digest; no natural-language content",
    "url": "URL string; long, high token cost, no retrieval signal",
    "status": "2 values, 98.5% 'current_or_unspecified'; near-zero entropy",
    "authority_class": "10-value categorical; retained as a Qdrant payload filter instead",
    "binding_status": "10-value categorical, some values are long sentences; retained as a payload filter",
    "jurisdiction": "6-value categorical; retained in the node payload",
    "extent": "8-value code such as 'E+W+S+N.I.'; retained in the node payload",
    "effective_from": "date string; belongs in temporal filtering, not in the semantic vector",
}


def _clean(value: Any) -> str:
    return str(value).strip()


def _baseline_v1(node: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, label in BASELINE_FIELDS:
        value = node.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{label}: {value}")
    return "\n".join(parts).strip()


def _text_focused_v1(node: dict[str, Any]) -> str:
    """Legal text plus the minimal human-readable context that locates it.

    Keeps `title` (document or page title), `locator` (a section heading on web nodes, a
    provision number on legislation nodes) and `label` (the provision's own number/letter).
    Drops every opaque identifier, URL and low-cardinality categorical. No field-name
    prefixes: the model receives natural language, not a serialised record.
    """
    parts: list[str] = []
    for key in ("title", "locator", "label"):
        value = node.get(key)
        if value not in (None, "", [], {}):
            cleaned = _clean(value)
            if cleaned and cleaned not in parts:
                parts.append(cleaned)
    context = " - ".join(parts)
    text = _clean(node.get("text") or "")
    if context and text:
        return f"{context}\n{text}"
    return text or context


def _text_only_v1(node: dict[str, Any]) -> str:
    """Pure ablation control: the provision text and nothing else."""
    return _clean(node.get("text") or "")


SPECS: dict[str, dict[str, Any]] = {
    "baseline_v1": {
        "builder": _baseline_v1,
        "fields": [key for key, _ in BASELINE_FIELDS],
        "field_name_prefixes": True,
        "description": (
            "Frozen baseline_v1 behaviour: all 14 fields with 'Label: value' prefixes. "
            "Identical to graph_store.searchable_text. Never edit."
        ),
        "frozen": True,
    },
    "text_focused_v1": {
        "builder": _text_focused_v1,
        "fields": ["title", "locator", "label", "text"],
        "field_name_prefixes": False,
        "description": (
            "Legal text with minimal locating context; all opaque identifiers, URLs and "
            "low-cardinality categoricals removed. Categoricals remain available as vector "
            "payload filters."
        ),
        "excludes": sorted(EXCLUSION_RATIONALE),
        "frozen": False,
    },
    "text_only_v1": {
        "builder": _text_only_v1,
        "fields": ["text"],
        "field_name_prefixes": False,
        "description": "Ablation control: provision text alone, no context of any kind.",
        "frozen": False,
    },
}


def available_versions() -> list[str]:
    return sorted(SPECS)


def get_builder(version: str) -> Callable[[dict[str, Any]], str]:
    try:
        return SPECS[version]["builder"]
    except KeyError:
        raise ValueError(
            f"Unknown embedding input version {version!r}. Available: {', '.join(available_versions())}"
        ) from None


def build_embedding_input(
    node: dict[str, Any], version: str = "baseline_v1", max_chars: int | None = None
) -> str:
    """Return the exact string that should be sent to the embedding model."""
    result = get_builder(version)(node)
    return result[:max_chars] if max_chars else result


def spec_fingerprint(version: str) -> str:
    """Stable hash of a version's declared specification, for run manifests.

    Detects an accidental edit to a version that experiments already reference.
    """
    spec = SPECS[version]
    payload = {
        "version": version,
        "fields": spec["fields"],
        "field_name_prefixes": spec["field_name_prefixes"],
        "excludes": spec.get("excludes", []),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def describe(version: str) -> dict[str, Any]:
    spec = SPECS[version]
    return {
        "input_version": version,
        "fields": spec["fields"],
        "field_name_prefixes": spec["field_name_prefixes"],
        "excludes": spec.get("excludes", []),
        "description": spec["description"],
        "frozen": spec.get("frozen", False),
        "spec_fingerprint": spec_fingerprint(version),
    }
