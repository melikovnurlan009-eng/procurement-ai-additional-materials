#!/usr/bin/env python3
"""Hybrid + graph-expanded + authority-aware retrieval over the chunk corpus.

Pipeline
--------
    query -> BM25 (SQLite FTS5)      \\
             dense (BGE-M3 / Qdrant)  ) -> RRF fusion -> legal anchors
                                     /                    -> bounded graph expansion
                                                          -> authority/regime rerank
                                                          -> evidence bundle

Every stage is separately switchable so the thesis arms can be evaluated in isolation:

    A  dense only              --no-lexical --no-graph --no-rerank
    B  lexical only            --no-dense --no-graph --no-rerank
    C  hybrid                  --no-graph --no-rerank
    D  hybrid + rerank         --no-graph
    E  hybrid + graph          --no-rerank
    F  hybrid + graph + rerank  (default)

Design decisions that matter
----------------------------
Fusion is Reciprocal Rank Fusion, not score addition: BM25 scores and cosine
similarities are not on a comparable scale, and normalising them introduces a hidden
tunable that would silently drive results.

Graph expansion is bounded by hop count AND relation type AND per-hop fan-out. Legal
graphs are dense - PA2023 alone has thousands of cross-references - so unbounded
traversal returns the whole statute and destroys precision.

Authority is applied as an explicit multiplicative prior, never learned from the query.
Professional commentary must not outrank primary legislation because its phrasing
happens to match the question more closely.

Legacy regime handling is conservative: PCR2015 evidence is demoted unless the query
signals a legacy/transitional question, because answering a current-law question with
repealed law is a correctness failure, not a ranking nuisance.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

RETRIEVAL_VERSION = "1.0.0"
DEFAULT_DB = "state/chunk_index_merged.sqlite3"
DEFAULT_COLLECTION = "chunks__bge_m3__v1"

# Explicit, configurable, and logged with every run - never hardcoded silently.
AUTHORITY_WEIGHTS: dict[str, float] = {
    "PRIMARY_LEGISLATION": 1.00,
    "SECONDARY_LEGISLATION": 0.97,
    "OFFICIAL_TECHNICAL_GUIDANCE": 0.90,
    "OFFICIAL_GOVERNMENT_GUIDANCE": 0.88,
    "OFFICIAL_REGULATOR_GUIDANCE": 0.86,
    "PROCUREMENT_POLICY": 0.84,
    "OFFICIAL_WORKFLOW": 0.78,
    "OFFICIAL_TRAINING": 0.74,
    "PROFESSIONAL_INTERPRETATION": 0.62,
    "PROFESSIONAL_CASE_ANALYSIS": 0.62,
    "INDUSTRY_PRACTICE": 0.55,
    # Emitted by the professional-sources scraper; mapped explicitly so practitioner
    # commentary is weighted by a stated policy rather than falling through to a default.
    "NON_AUTHORITATIVE_PROFESSIONAL": 0.62,
    "OFFICIAL_SPECIALIST_GUIDANCE": 0.86,
    "OFFICIAL_PA23_TECHNICAL_GUIDANCE": 0.90,
    "OFFICIAL_PRACTICE_GUIDANCE": 0.84,
}

# Statute competes against guidance in one fused, one authority-weighted ranking, and
# structurally loses even when it is the right answer: guidance echoes a query's own
# phrasing while statute uses defined terms, so cosine and the cross-encoder both reward
# guidance's surface overlap. Measured on the 300-query anchor set: restricting the pool
# to legislation-only recovers gold at rank 1 for 26% of the queries production otherwise
# gets wrong (59/230) - not a fix for the majority, but a real, cheap one where legislation
# is competitive within its own class yet never reaches the top of the mixed pool.
LEGISLATION_CLASSES = ("PRIMARY_LEGISLATION", "SECONDARY_LEGISLATION")
DEFAULT_AUTHORITY_WEIGHT = 0.60

# Regime intent. The previous design had two defects, both visible on the applicability
# suite where all nine queries failed.
#
# First, mentioning an instrument was read as wanting it: "I need the current rule, NOT an
# old PCR 2015 rule" triggered legacy mode. Negation is now detected.
#
# Second, and more consequential, legacy mode only REMOVED the penalty on PCR2015 - it set
# the weight to 1.0 while PA2023 also defaulted to 1.0, so neither was preferred. Since
# PA2023 material is more abundant and better chunked, it continued to win on queries that
# explicitly asked for PCR 2015. A prior that expresses a preference has to demote the
# alternative as well as spare the target, so the weights below are symmetric.
LEGACY_TERMS = (r"pcr\s?2015|public contracts regulations 2015|2015 regulations|legacy|"
                r"transitional|before the procurement act|old (?:procurement )?regime|pre-?2023|repealed|previously")
CURRENT_TERMS = (r"procurement act 2023|pa\s?2023|procurement regulations 2024|pr\s?2024|"
                 r"new regime|current(ly)? (rule|regime|law|position)|under the act")
NEGATED = re.compile(r"\b(not|rather than|instead of|excluding|do not|don't|avoid)\b[^.?!]{0,60}?(%s)"
                     % LEGACY_TERMS, re.I)
LEGACY_SIGNALS = re.compile(r"\b(%s)\b" % LEGACY_TERMS, re.I)
CURRENT_SIGNALS = re.compile(r"\b(%s)\b" % CURRENT_TERMS, re.I)


# Instrument aliases, expanded before matching. Legislation never cites itself, so the only
# string identifying PCR 2015 reg 72 as PCR 2015 is its `citation` field - "Public Contracts
# Regulations 2015 reg 72". A practitioner writes "PCR 2015". BM25 tokenises the abbreviation
# and the full name as unrelated terms, so the most discriminating term in the query matches
# nothing, and the abbreviation actively steers retrieval toward the 509 guidance chunks that
# DISCUSS PCR 2015 rather than the regulations themselves. Measured: with the abbreviation the
# gold provision was absent from the top 40 of both channels; with the full name it ranked 1.
#
# The alias is APPENDED rather than substituted, so the original wording still contributes and
# a query that already uses the full name is unaffected.
INSTRUMENT_ALIASES = [
    (re.compile(r"\bPCR\s?-?\s?2015\b", re.I), "Public Contracts Regulations 2015"),
    (re.compile(r"\bPA\s?-?\s?2023\b", re.I), "Procurement Act 2023"),
    (re.compile(r"\bPR\s?-?\s?2024\b", re.I), "Procurement Regulations 2024"),
    (re.compile(r"\bUCR\s?-?\s?2016\b", re.I), "Utilities Contracts Regulations 2016"),
    (re.compile(r"\bCCR\s?-?\s?2016\b", re.I), "Concession Contracts Regulations 2016"),
    (re.compile(r"\bDSPCR\s?-?\s?2011\b", re.I), "Defence and Security Public Contracts Regulations 2011"),
    (re.compile(r"\bFOIA\b", re.I), "Freedom of Information Act 2000"),
    (re.compile(r"\bDPA\s?-?\s?2018\b", re.I), "Data Protection Act 2018"),
]


def expand_instrument_aliases(query: str) -> str:
    """Append the full instrument name wherever an abbreviation appears."""
    extra = []
    for rx, full in INSTRUMENT_ALIASES:
        if rx.search(query or "") and full.lower() not in (query or "").lower():
            extra.append(full)
    return f"{query} {' '.join(extra)}" if extra else query


def regime_intent(query: str) -> str:
    """Which regime does this query want? LEGACY, CURRENT or NEUTRAL."""
    q = query or ""
    legacy = bool(LEGACY_SIGNALS.search(q))
    negated = bool(NEGATED.search(q))
    current = bool(CURRENT_SIGNALS.search(q))
    if legacy and not negated:
        # An explicit legacy mention wins even alongside a current-regime mention, because
        # "under PCR 2015, ... do not answer from the Procurement Act 2023" names both.
        return "legacy_query"
    if current or negated:
        return "current_query"
    return "current_query"


REGIME_WEIGHTS = {
    # Asymmetric AND boosting. Two earlier shapes failed on the applicability suite.
    #
    # Penalty-only ("current" demotes PCR2015, "legacy" sets it to 1.0) expresses no
    # preference at all in legacy mode: the preferred regime gets no lift while 82.6% of the
    # corpus carries no regime label and is also 1.0, so the unlabelled majority decides the
    # ranking by volume.
    #
    # Slot reservation and hard filtering were measured and did nothing for the same reason -
    # there is too little labelled material for either to act on.
    #
    # Boosting the preferred regime moved applicability hit@10 from 0.000 to 0.222 and
    # overall hit@10 from 0.393 to 0.447 on the same candidates. Unlabelled chunks stay at
    # 1.0 throughout: material such as the Data Protection Act is regime-NEUTRAL, not
    # off-regime, and must not be penalised for lacking a label.
    "current_query": {"PA2023": 1.60, "PR2024": 1.60, "PCR2015": 0.45},
    "legacy_query":  {"PCR2015": 1.60, "PA2023": 0.45, "PR2024": 0.45},
}

# Jurisdiction prior. The corpus retains 213 EU chunks (Official Journal directives) that
# informed the pre-Brexit regime. They are kept because legacy and transitional questions
# can turn on them, but they must not outrank domestic law on a UK question: measured, an
# EU directive ranked first on "can we split up a contract to avoid the procurement rules"
# and the resulting answer inverted the section 12 anti-avoidance position. A multiplicative
# demotion is used rather than a hard filter, for the same reason PCR2015 is demoted rather
# than removed - the material stays reachable when it is genuinely what the query is about.
JURISDICTION_WEIGHTS: dict[str, float] = {"EU": 0.35}
DEFAULT_JURISDICTION_WEIGHT = 1.0

# HAS_CHUNK is deliberately EXCLUDED by default. It is a structural relation
# (document -> its own chunks), so expanding it returns same-document siblings rather
# than legally connected provisions: measured, it flooded the graph channel and cut
# anchor recall from 0.618 to 0.510. The legal relations are the ones worth traversing.
EXPANSION_RELATIONS = ("CROSS_REFERS_TO", "REFERENCES")
EXPANSION_RELATIONS_WITH_STRUCTURE = ("CROSS_REFERS_TO", "REFERENCES", "HAS_CHUNK")


@dataclass
class Trace:
    """Everything needed to explain and debug a single query."""
    query: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    legacy_query: bool = False
    lexical_hits: list[dict[str, Any]] = field(default_factory=list)
    dense_hits: list[dict[str, Any]] = field(default_factory=list)
    fused: list[dict[str, Any]] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    edges_traversed: list[dict[str, Any]] = field(default_factory=list)
    graph_added: list[dict[str, Any]] = field(default_factory=list)
    final: list[dict[str, Any]] = field(default_factory=list)


# Function words carry no retrieval signal but dominate an OR query: measured on this
# corpus, "for" matches 588 of 743 chunks and "can" 236, while the terms that actually
# discriminate - "cartel" (26), "rigging" (18) - are swamped. IDF alone does not rescue
# this, because every chunk still enters the candidate set.
FTS_STOPWORDS = {
    "a","an","and","are","as","at","be","been","but","by","can","could","do","does","for",
    "from","had","has","have","how","i","if","in","into","is","it","its","may","might","must",
    "of","on","or","should","so","such","than","that","the","their","them","then","there",
    "these","they","this","to","under","was","we","were","what","when","where","which","who",
    "why","will","with","would","you","your","about","any","all",
}


def fts_query(text: str) -> str:
    """FTS5 MATCH string over content terms only.

    Quoting every term keeps punctuation from being read as FTS syntax. Stopwords are
    dropped; if a query is nothing but stopwords the original terms are used rather than
    returning an empty match.
    """
    terms = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-']+", text) if len(t) > 1]
    content = [t for t in terms if t.lower() not in FTS_STOPWORDS]
    use = content or terms
    return " OR ".join(f'"{t}"' for t in use) or '""'


class ChunkRetriever:
    def __init__(self, db_path: Path, collection: str = DEFAULT_COLLECTION,
                 qdrant_url: str | None = None, model_name: str | None = None):
        # SQLite connections are bound to the thread that created them, so a retriever
        # shared by a threaded server must hand out one connection per thread rather than
        # reusing a single handle. Disabling the check instead would silently permit
        # cross-thread use of one connection.
        self._db_path = db_path
        self._local = threading.local()
        self.collection = collection
        self.qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.model_name = model_name or os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-m3")
        self._model = None
        self._client = None

    @property
    def con(self) -> sqlite3.Connection:
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(self._db_path)
            con.row_factory = sqlite3.Row
            self._local.con = con
        return con

    # ---------------------------------------------------------------- channels
    def lexical(self, query: str, k: int) -> list[dict[str, Any]]:
        sql = (
            "SELECT c.chunk_id, bm25(chunks_fts) AS score FROM chunks_fts "
            "JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id "
            "WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?"
        )
        try:
            rows = self.con.execute(sql, (fts_query(query), k)).fetchall()
        except sqlite3.OperationalError:
            return []
        # bm25() returns lower-is-better; invert so higher is better everywhere.
        return [{"chunk_id": r["chunk_id"], "score": -r["score"], "channel": "lexical"} for r in rows]

    def dense(self, query: str, k: int) -> list[dict[str, Any]]:
        try:
            from qdrant_client import QdrantClient
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return []
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
            self._client = QdrantClient(url=self.qdrant_url, timeout=60)
        vec = self._model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        res = self._client.query_points(
            collection_name=self.collection, query=vec.tolist(), limit=k, with_payload=True
        ).points
        return [
            {"chunk_id": p.payload.get("chunk_id"), "score": float(p.score), "channel": "dense"}
            for p in res
        ]

    # ------------------------------------------------------------------ fusion
    @staticmethod
    def rrf(channels: list[list[dict[str, Any]]], k_const: int = 60) -> list[dict[str, Any]]:
        scores: dict[str, float] = {}
        provenance: dict[str, list[str]] = {}
        for ranked in channels:
            for rank, hit in enumerate(ranked, 1):
                cid = hit["chunk_id"]
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k_const + rank)
                provenance.setdefault(cid, []).append(f"{hit['channel']}#{rank}")
        return [
            {"chunk_id": cid, "fusion_score": s, "channels": provenance[cid]}
            for cid, s in sorted(scores.items(), key=lambda kv: -kv[1])
        ]

    # ------------------------------------------------------------------- graph
    def anchors_for(self, chunk_ids: list[str]) -> list[str]:
        """Legal identity of retrieved chunks: provision first, else document."""
        if not chunk_ids:
            return []
        q = ",".join("?" * len(chunk_ids))
        rows = self.con.execute(
            f"SELECT chunk_id, parent_node_id, document_id FROM chunks WHERE chunk_id IN ({q})",
            chunk_ids,
        ).fetchall()
        out = []
        for r in rows:
            # The chunk id itself is an anchor: guidance and commentary citations are
            # recorded as CHUNK --REFERENCES--> PROVISION, so anchoring only on the
            # parent provision or document would miss the entire guidance->law layer.
            out.append(r["chunk_id"])
            if r["parent_node_id"]:
                out.append(r["parent_node_id"])
            out.append(r["document_id"])
        return [a for a in dict.fromkeys(out) if a]

    def expand(self, anchors: list[str], hops: int, per_hop: int,
               relations: tuple[str, ...], trace: Trace,
               exclude_regimes: tuple[str, ...] = (),
               exclude_jurisdictions: tuple[str, ...] = ()) -> list[str]:
        """Bounded traversal. Returns chunk ids reachable from the anchors.

        Regime filtering is applied HERE, not only at reranking. Legacy legislation is
        disproportionately central in the citation graph - PCR2015 is the target of 2,376
        cross-references against PA2023's 2,217, because the older instrument accumulated
        internal references over a decade. Expanding into it for a current-law question
        floods the graph channel with repealed provisions, and a downstream score penalty
        cannot recover a result set that has already been crowded out. Demotion is the
        right instrument at ranking time; exclusion is the right one at traversal time.
        """
        frontier = list(anchors)
        seen_nodes = set(anchors)
        node_order: list[str] = []
        reached_chunks: list[str] = []
        rel_clause = ",".join("?" * len(relations))
        for hop in range(1, hops + 1):
            if not frontier:
                break
            q = ",".join("?" * len(frontier))
            # Traverse on retrieval_target_id, falling back to target_id where the
            # densification pass has not run. target_id remains the exact legal reference;
            # retrieval_target_id is that reference rolled up to the granularity that was
            # actually chunked. Before this, 39.8% of legal edges pointed at sub-provision
            # nodes with no chunk, so the traversal silently dropped them.
            # Deduplicate on (source, target, relation). A provision may cite the same
            # target from several subsections, and rolling sources up to provision level
            # collapses those into identical edges: measured, 30.9% of legal edges are
            # duplicates this way, with one pair appearing 26 times. Because the fan-out
            # cap is applied by LIMIT, duplicates consume traversal budget without
            # reaching anything new - only 75.1% of a source's edges lead somewhere
            # distinct. MAX(confidence) keeps the strongest evidence for the pair.
            rows = self.con.execute(
                f"SELECT COALESCE(retrieval_source_id, source_id) AS source_id, relation, "
                f"COALESCE(retrieval_target_id, target_id) AS target_id, "
                f"MIN(target_id) AS legal_target_id, MAX(confidence) AS confidence, "
                f"MIN(resolution_status) AS resolution_status "
                f"FROM edges WHERE COALESCE(retrieval_source_id, source_id) IN ({q}) "
                f"AND relation IN ({rel_clause}) "
                f"GROUP BY source_id, target_id, relation "
                f"ORDER BY confidence DESC LIMIT ?",
                (*frontier, *relations, per_hop),
            ).fetchall()
            next_frontier = []
            for r in rows:
                trace.edges_traversed.append(
                    {"hop": hop, "source": r["source_id"], "relation": r["relation"],
                     "target": r["target_id"], "legal_target": r["legal_target_id"],
                     "confidence": r["confidence"], "status": r["resolution_status"]}
                )
                tgt = r["target_id"]
                if tgt in seen_nodes:
                    continue
                seen_nodes.add(tgt)
                node_order.append(tgt)
                next_frontier.append(tgt)
            frontier = next_frontier
        # Map reached provisions/documents to their chunks, preserving discovery order so
        # the graph channel is RANKED (nearer hops and higher-confidence edges first)
        # rather than an unordered bag.
        ordered_targets = [n for n in node_order if n not in set(anchors)]
        exclude_clause = ""
        params_extra: list[str] = []
        if exclude_regimes:
            exclude_clause += (" AND (legal_regime IS NULL OR legal_regime NOT IN (%s))"
                               % ",".join("?" * len(exclude_regimes)))
            params_extra += list(exclude_regimes)
        if exclude_jurisdictions:
            # Regime exclusion alone leaves EU-jurisdiction chunks reachable: they carry no
            # legal_regime (they predate the PA2023/PCR2015/PR2024 split entirely), so the
            # regime clause's own "legal_regime IS NULL" branch passes them through. The
            # 0.35x jurisdiction demotion in search()'s final scoring does not help here -
            # it discounts a candidate already in the pool, but traversal is what put it
            # there ahead of a chunk that never entered the graph channel at all.
            exclude_clause += (" AND (jurisdiction IS NULL OR jurisdiction NOT IN (%s))"
                               % ",".join("?" * len(exclude_jurisdictions)))
            params_extra += list(exclude_jurisdictions)
        for node in ordered_targets:
            rows = self.con.execute(
                "SELECT chunk_id FROM chunks WHERE (parent_node_id = ? OR document_id = ? "
                "OR chunk_id = ?)" + exclude_clause,
                (node, node, node, *params_extra),
            ).fetchall()
            for r in rows:
                if r["chunk_id"] not in reached_chunks:
                    reached_chunks.append(r["chunk_id"])
        return reached_chunks

    # ---------------------------------------------------------------- metadata
    def load(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not chunk_ids:
            return {}
        q = ",".join("?" * len(chunk_ids))
        rows = self.con.execute(f"SELECT * FROM chunks WHERE chunk_id IN ({q})", chunk_ids).fetchall()
        # Superseded chunks are duplicate ingestions of an instrument already held in a
        # parsed, provision-level form. They carry no legal identity, are far coarser, and
        # compete for the same result slots. Dropping them here removes them from every
        # channel at once, because every channel's output passes through load().
        out = {}
        for r in rows:
            d = dict(r)
            if d.get("superseded_by"):
                continue
            # Blocks the content filter identified as page furniture rather than content:
            # advice footers, copyright notices, contact blocks, navigation listings.
            # Validated against 900 LLM labels at 0% false-positive on GOOD chunks.
            if d.get("filtered_out"):
                continue
            out[d["chunk_id"]] = d
        return out

    # ---------------------------------------------------------------- pipeline
    def search(self, query: str, top_k: int = 10, candidates: int = 40,
               use_lexical: bool = True, use_dense: bool = True, use_graph: bool = True,
               use_rerank: bool = True, hops: int = 1, per_hop: int = 40,
               graph_weight: float = 0.60, graph_channel_cap: int | None = None,
               use_legislation_lane: bool = True, legislation_lane_top_n: int = 3,
               expand_query: bool | str = False,
               expansion_relations: tuple[str, ...] = EXPANSION_RELATIONS) -> tuple[list[dict[str, Any]], Trace]:
        trace = Trace(query=query)
        # Vocabulary bridge, applied BEFORE matching. The question itself is unchanged;
        # only the string handed to the lexical and dense channels is augmented, because
        # the measured failure is at the first stage rather than in ranking.
        # Applied to the matching string only; `query` itself is what gets logged, traced
        # and evaluated, so the intervention stays confined to the first stage.
        retrieval_query = expand_instrument_aliases(query)
        if expand_query:
            from query_expansion import QueryExpander
            if not hasattr(self, "_expander"):
                self._expander = QueryExpander()
            exp = self._expander.expand(query)
            # Expand only when the question actually uses non-statutory phrasing.
            # Applied unconditionally, expansion raised recall on the practitioner-phrased
            # suite from 0.438 to 0.625 but cut the semantic suite from 0.800 to 0.467:
            # added terminology dilutes a query that already matches the statute. Gating on
            # a detected colloquialism confines the intervention to the case it addresses.
            has_colloquialism = bool(exp.get("colloquialisms_detected"))
            if expand_query == "always" or has_colloquialism:
                retrieval_query = exp.get("expanded_query") or query
            trace.config["query_expansion"] = {
                "statutory_terms": exp.get("statutory_terms"),
                "colloquialisms_detected": exp.get("colloquialisms_detected"),
                "source": exp.get("source"),
            }
        regime_key = regime_intent(query)
        trace.legacy_query = regime_key == "legacy_query"
        trace.config = {
            "retrieval_version": RETRIEVAL_VERSION, "top_k": top_k, "candidates": candidates,
            "lexical": use_lexical, "dense": use_dense, "graph": use_graph, "rerank": use_rerank,
            "hops": hops, "per_hop": per_hop, "graph_weight": graph_weight,
            "graph_channel_cap": graph_channel_cap,
            "authority_weights": AUTHORITY_WEIGHTS, "jurisdiction_weights": JURISDICTION_WEIGHTS, "expansion_relations": list(expansion_relations),
            "use_legislation_lane": use_legislation_lane, "legislation_lane_top_n": legislation_lane_top_n,
        }

        channels = []
        if use_lexical:
            trace.lexical_hits = self.lexical(retrieval_query, candidates)
            channels.append(trace.lexical_hits)
        if use_dense:
            trace.dense_hits = self.dense(retrieval_query, candidates)
            channels.append(trace.dense_hits)
        if not channels:
            return [], trace

        first_pass = self.rrf(channels)
        seeds = [f["chunk_id"] for f in first_pass[:top_k]]
        retrieved = {f["chunk_id"] for f in first_pass}
        graph_only: set[str] = set()

        if use_graph and seeds:
            trace.anchors = self.anchors_for(seeds)
            # A current-law question should not be expanded into repealed law, or into
            # pre-Brexit EU directives that carry no legal_regime of their own.
            exclude = () if trace.legacy_query else ("PCR2015",)
            exclude_juris = () if trace.legacy_query else ("EU",)
            trace.config["expansion_excluded_regimes"] = list(exclude)
            trace.config["expansion_excluded_jurisdictions"] = list(exclude_juris)
            added = self.expand(trace.anchors, hops, per_hop, expansion_relations, trace,
                                exclude_regimes=exclude, exclude_jurisdictions=exclude_juris)
            # Graph results join fusion as a THIRD RANKED CHANNEL.
            #
            # An earlier revision scored them as strongest_seed * graph_weight. That can
            # never work with RRF: fused scores decay only to ~87% of rank 1 by rank 10,
            # so any multiplicative discount below that ratio pushes graph evidence out
            # of the result set by construction - 15 chunks added per query, none able
            # to surface. Rank-based fusion makes them compete on the same footing.
            # The graph channel competes on rank, so its LENGTH is a real parameter: a
            # long channel introduces many candidates that displace true positives from a
            # fixed top-k. Capping it is a sensitivity knob, reported rather than tuned.
            capped = added[:graph_channel_cap] if graph_channel_cap else added
            graph_channel = [
                {"chunk_id": cid, "score": 1.0 / rank, "channel": "graph"}
                for rank, cid in enumerate(capped, 1)
            ]
            if graph_channel:
                channels.append(graph_channel)
                graph_only = {c["chunk_id"] for c in graph_channel} - retrieved
            trace.graph_added = [{"chunk_id": c} for c in list(graph_only)[:50]]

        fused = self.rrf(channels)
        trace.fused = fused[:top_k]
        scored = {f["chunk_id"]: f["fusion_score"] for f in fused}

        meta = self.load(list(scored))
        results = []
        for cid, base_score in scored.items():
            m = meta.get(cid)
            if not m:
                continue
            authority = AUTHORITY_WEIGHTS.get(m.get("authority_class"), DEFAULT_AUTHORITY_WEIGHT)

            regime_w = REGIME_WEIGHTS[regime_key].get(m.get("legal_regime"), 1.0)
            juris_w = JURISDICTION_WEIGHTS.get(m.get("jurisdiction"), DEFAULT_JURISDICTION_WEIGHT)
            final = base_score * (authority * regime_w * juris_w) if use_rerank else base_score
            results.append(
                {
                    "chunk_id": cid,
                    "final_score": final,
                    "fusion_score": base_score,
                    "authority_weight": authority if use_rerank else None,
                    "regime_weight": regime_w if use_rerank else None,
                    "jurisdiction_weight": juris_w if use_rerank else None,
                    "jurisdiction": m.get("jurisdiction"),
                    "via_graph_only": cid in graph_only,
                    "authority_class": m.get("authority_class"),
                    "legal_regime": m.get("legal_regime"),
                    "citation": m.get("citation"),
                    "retrieval_title": m.get("retrieval_title"),
                    "source_url": m.get("source_url"),
                    "document_id": m.get("document_id"),
                    "text": m.get("text"),
                }
            )
        results.sort(key=lambda r: -r["final_score"])
        if use_legislation_lane:
            lane_check = results[:legislation_lane_top_n]
            if not any(r["authority_class"] in LEGISLATION_CLASSES for r in lane_check):
                lane_candidates = [r for r in results if r["authority_class"] in LEGISLATION_CLASSES]
                if lane_candidates:
                    winner = lane_candidates[0]  # already sorted by final_score desc
                    results.remove(winner)
                    results.insert(0, winner)
                    trace.config["legislation_lane_promoted"] = winner["chunk_id"]
        results = results[:top_k]
        trace.final = [
            {k: v for k, v in r.items() if k != "text"} for r in results
        ]
        return results, trace

    def search_two_lanes(self, query: str, top_k_legislation: int = 5, top_k_other: int = 5,
                          candidates: int = 100, use_graph: bool = True, hops: int = 1,
                          per_hop: int = 40, graph_channel_cap: int | None = None,
                          expansion_relations: tuple[str, ...] = EXPANSION_RELATIONS,
                          ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Trace]:
        """Legislation and everything-else, ranked and returned as two SEPARATE lists.

        `search()` merges every source into one ranked list and, when legislation falls
        out of the top few places, promotes its single best candidate into that list.
        That is a patch on a single ranking, not a different architecture: guidance and
        statute still compete for the same slots before the patch fires, and only one
        legislation chunk ever gets rescued regardless of how many are actually relevant.

        Measured on the 150-query test set: a real split - candidates generated once,
        then partitioned by authority_class and weighted within each partition
        independently, never compared against each other - gives the legislation lane
        58.7% hit@10, ahead of every merged configuration tried (RRF 40.7%, dense-only
        46.7%). The candidate pool is widened past search()'s default (100 vs 40) because
        a partition only has as many candidates as survive the split; a narrow shared
        pool starves whichever lane is thinner for a given query.

        The two lists are not reconciled into a single ranking here. Presentation
        (leading with law, deduplicating, capping a combined bundle) is the caller's
        job - answer_query.py and chunk_api.py - so that decision stays visible and
        auditable rather than hidden inside retrieval.
        """
        trace = Trace(query=query)
        retrieval_query = expand_instrument_aliases(query)
        regime_key = regime_intent(query)
        trace.legacy_query = regime_key == "legacy_query"
        trace.config = {
            "retrieval_version": RETRIEVAL_VERSION, "mode": "two_lane",
            "top_k_legislation": top_k_legislation, "top_k_other": top_k_other,
            "candidates": candidates, "graph": use_graph, "hops": hops, "per_hop": per_hop,
        }

        trace.lexical_hits = self.lexical(retrieval_query, candidates)
        trace.dense_hits = self.dense(retrieval_query, candidates)
        channels = [trace.lexical_hits, trace.dense_hits]

        first_pass = self.rrf(channels)
        seeds = [f["chunk_id"] for f in first_pass[:max(top_k_legislation, top_k_other)]]
        retrieved = {f["chunk_id"] for f in first_pass}
        graph_only: set[str] = set()

        if use_graph and seeds:
            trace.anchors = self.anchors_for(seeds)
            exclude = () if trace.legacy_query else ("PCR2015",)
            exclude_juris = () if trace.legacy_query else ("EU",)
            trace.config["expansion_excluded_regimes"] = list(exclude)
            trace.config["expansion_excluded_jurisdictions"] = list(exclude_juris)
            added = self.expand(trace.anchors, hops, per_hop, expansion_relations, trace,
                                exclude_regimes=exclude, exclude_jurisdictions=exclude_juris)
            capped = added[:graph_channel_cap] if graph_channel_cap else added
            graph_channel = [{"chunk_id": cid, "score": 1.0 / rank, "channel": "graph"}
                             for rank, cid in enumerate(capped, 1)]
            if graph_channel:
                channels.append(graph_channel)
                graph_only = {c["chunk_id"] for c in graph_channel} - retrieved
            trace.graph_added = [{"chunk_id": c} for c in list(graph_only)[:50]]

        fused = self.rrf(channels)
        scored = {f["chunk_id"]: f["fusion_score"] for f in fused}
        meta = self.load(list(scored))

        legislation, other = [], []
        for cid, base_score in scored.items():
            m = meta.get(cid)
            if not m:
                continue
            authority = AUTHORITY_WEIGHTS.get(m.get("authority_class"), DEFAULT_AUTHORITY_WEIGHT)
            regime_w = REGIME_WEIGHTS[regime_key].get(m.get("legal_regime"), 1.0)
            juris_w = JURISDICTION_WEIGHTS.get(m.get("jurisdiction"), DEFAULT_JURISDICTION_WEIGHT)
            row = {
                "chunk_id": cid, "final_score": base_score * authority * regime_w * juris_w,
                "fusion_score": base_score, "authority_weight": authority, "regime_weight": regime_w,
                "jurisdiction_weight": juris_w, "jurisdiction": m.get("jurisdiction"),
                "via_graph_only": cid in graph_only, "authority_class": m.get("authority_class"),
                "legal_regime": m.get("legal_regime"), "citation": m.get("citation"),
                "retrieval_title": m.get("retrieval_title"), "source_url": m.get("source_url"),
                "document_id": m.get("document_id"), "text": m.get("text"),
            }
            (legislation if m.get("authority_class") in LEGISLATION_CLASSES else other).append(row)

        legislation.sort(key=lambda r: -r["final_score"])
        other.sort(key=lambda r: -r["final_score"])
        legislation, other = legislation[:top_k_legislation], other[:top_k_other]
        trace.final = [{k: v for k, v in r.items() if k != "text"} for r in legislation + other]
        return legislation, other, trace


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--db", default=DEFAULT_DB, type=Path)
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--candidates", type=int, default=40)
    ap.add_argument("--no-lexical", action="store_true")
    ap.add_argument("--no-dense", action="store_true")
    ap.add_argument("--no-graph", action="store_true")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--hops", type=int, default=1)
    ap.add_argument("--per-hop", type=int, default=40)
    ap.add_argument("--debug", action="store_true", help="print the full retrieval trace")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-text", type=int, default=0, help="chars of evidence text to show")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    db = args.db if args.db.is_absolute() else root / args.db
    r = ChunkRetriever(db, args.collection)
    results, trace = r.search(
        args.query, top_k=args.top_k, candidates=args.candidates,
        use_lexical=not args.no_lexical, use_dense=not args.no_dense,
        use_graph=not args.no_graph, use_rerank=not args.no_rerank,
        hops=args.hops, per_hop=args.per_hop,
    )

    if args.json:
        print(json.dumps({"results": results, "trace": asdict(trace)}, indent=2, ensure_ascii=False))
        return 0

    print(f"\nQUERY: {trace.query}")
    print(f"legacy-regime query: {trace.legacy_query}")
    print(f"channels: lexical={len(trace.lexical_hits)} dense={len(trace.dense_hits)} "
          f"fused={len(trace.fused)} anchors={len(trace.anchors)} "
          f"edges={len(trace.edges_traversed)} graph_added={len(trace.graph_added)}")
    print("-" * 100)
    for i, res in enumerate(results, 1):
        tag = " [GRAPH-ONLY]" if res["via_graph_only"] else ""
        print(f"{i:2d}. {res['final_score']:.5f}{tag}  [{res['authority_class']}"
              f"{'/' + res['legal_regime'] if res['legal_regime'] else ''}]")
        print(f"    {res['citation'] or res['document_id']}")
        print(f"    {res['retrieval_title']}")
        if args.show_text:
            print(f"    {(res['text'] or '')[:args.show_text]}...")
    if args.debug:
        print("\n--- TRACE ---")
        print(json.dumps(asdict(trace), indent=2, ensure_ascii=False)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
