"""Node-level features that retrieval needs but the corpus does not store directly.

Two problems in procurement_corpus_v1 are addressed here without mutating the corpus:

1. Authority metadata is missing on the nodes retrieval actually returns. Only 16.1% of
   nodes carry `authority_class`/`binding_status`, and almost none of the leaf statement
   nodes do, so the baseline authority prior evaluated to 1.0 for the vast majority of
   results. Every node does carry `source_id`, and the document node for that source does
   carry authority metadata, so authority can be inherited: coverage rises to 99.3%.

2. Roughly two thirds of nodes cannot answer a question on their own - 24.9% hold no text,
   17.7% hold fewer than six words, 21.2% are sentence fragments. They are legitimate parts
   of the structure but poor retrieval targets, and they need to be classified so retrieval
   can weight or exclude them.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# A fragment either stops mid-clause or opens as a continuation of its parent.
_TRAILING_CONNECTOR = re.compile(r"(\band\b|\bor\b|[,;:—-])\s*$", re.IGNORECASE)
_OPENS_MID_CLAUSE = re.compile(r"^([a-z(]|[ivx]+\.|\(?[a-z0-9]\))")

EMPTY = "empty"
SHORT = "short"
FRAGMENT = "fragment"
SUBSTANTIVE = "substantive"


def content_class(node: dict[str, Any], min_words: int = 6) -> str:
    """Classify how usable a node's text is as standalone evidence."""
    text = str(node.get("text") or "").strip()
    if not text:
        return EMPTY
    if len(text.split()) < min_words:
        return SHORT
    if _TRAILING_CONNECTOR.search(text) or _OPENS_MID_CLAUSE.match(text):
        return FRAGMENT
    return SUBSTANTIVE


@dataclass(frozen=True)
class Authority:
    authority_class: str | None
    binding_status: str | None
    hierarchy_rank: float | None
    document_id: str | None
    document_title: str | None
    inherited: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority_class": self.authority_class,
            "binding_status": self.binding_status,
            "hierarchy_rank": self.hierarchy_rank,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "inherited": self.inherited,
        }


UNKNOWN_AUTHORITY = Authority(None, None, None, None, None, False)


class AuthorityResolver:
    """Resolves a node's effective authority, inheriting from its source document.

    The mapping is built once per process from the document nodes and cached. It is derived
    data: nothing is written back to the corpus, so procurement_corpus_v1 is unchanged and an
    experiment can record exactly how authority was resolved.
    """

    def __init__(self, graph: Any):
        self._by_source: dict[str, Authority] = {}
        self._build(graph)

    def _build(self, graph: Any) -> None:
        rows = graph.conn.execute(
            "SELECT raw_json FROM nodes WHERE node_type = 'document'"
        ).fetchall()
        for row in rows:
            doc = json.loads(row["raw_json"])
            source_id = doc.get("source_id")
            if not source_id:
                continue
            self._by_source[str(source_id)] = Authority(
                authority_class=doc.get("authority_class"),
                binding_status=doc.get("binding_status"),
                hierarchy_rank=doc.get("hierarchy_rank"),
                document_id=doc.get("id"),
                document_title=doc.get("title"),
                inherited=True,
            )

    @property
    def source_count(self) -> int:
        return len(self._by_source)

    def resolve(self, node: dict[str, Any]) -> Authority:
        """A node's own metadata always wins; the source document fills the gaps."""
        own_class = node.get("authority_class")
        own_binding = node.get("binding_status")
        own_rank = node.get("hierarchy_rank")
        inherited = self._by_source.get(str(node.get("source_id") or ""))

        if own_class or own_binding or own_rank is not None:
            return Authority(
                authority_class=own_class or (inherited.authority_class if inherited else None),
                binding_status=own_binding or (inherited.binding_status if inherited else None),
                hierarchy_rank=own_rank if own_rank is not None
                else (inherited.hierarchy_rank if inherited else None),
                document_id=inherited.document_id if inherited else None,
                document_title=inherited.document_title if inherited else None,
                inherited=False,
            )
        return inherited or UNKNOWN_AUTHORITY


# Typographic variants of the same sentence appear across formats: the HTML and PDF renderings
# of one guidance passage differ by a single non-breaking space or curly quote, so hashing the
# raw text fails to recognise them as duplicates.
_PUNCT_MAP = str.maketrans(
    {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00a0": " ",
        "\u200b": "", "\ufeff": "",
    }
)


# HTML renderings of legislation cross-references leave a space inside brackets that the PDF
# extraction does not: "(see section 104 )." against "(see section 104).".
_SPACE_BEFORE_CLOSER = re.compile(r"\s+([)\]},.;:!?])")
_SPACE_AFTER_OPENER = re.compile(r"([(\[{])\s+")


def normalized_text_key(text: str) -> str:
    """Whitespace-, punctuation- and case-insensitive key for near-duplicate detection."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text).translate(_PUNCT_MAP)
    collapsed = " ".join(folded.split())
    collapsed = _SPACE_BEFORE_CLOSER.sub(r"\1", collapsed)
    collapsed = _SPACE_AFTER_OPENER.sub(r"\1", collapsed)
    return collapsed.casefold()
