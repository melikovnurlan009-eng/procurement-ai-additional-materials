from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .embedding_input import build_embedding_input
from .node_features import EMPTY, content_class


TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)


@dataclass(frozen=True)
class SearchHit:
    node_id: str
    score: float
    channel: str
    node: dict[str, Any]


def searchable_text(node: dict[str, Any], max_chars: int | None = None) -> str:
    """Build a stable embedding/search representation without inventing legal meaning."""
    parts: list[str] = []
    field_labels = (
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
    for key, label in field_labels:
        value = node.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{label}: {value}")
    result = "\n".join(parts).strip()
    return result[:max_chars] if max_chars else result


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GraphStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self._create_schema()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT,
                parent_id TEXT,
                source_id TEXT,
                title TEXT,
                label TEXT,
                text TEXT,
                locator TEXT,
                url TEXT,
                authority_class TEXT,
                binding_status TEXT,
                hierarchy_rank REAL,
                text_hash TEXT NOT NULL,
                searchable TEXT NOT NULL,
                raw_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_source ON nodes(source_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_nodes_authority ON nodes(authority_class);

            CREATE TABLE IF NOT EXISTS edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                relation TEXT NOT NULL,
                provenance TEXT NOT NULL DEFAULT '',
                weight REAL NOT NULL DEFAULT 1.0,
                raw_json TEXT NOT NULL,
                PRIMARY KEY (source, target, relation, provenance)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
            CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);

            CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(
                node_id UNINDEXED,
                content,
                tokenize='porter'
            );

            CREATE TABLE IF NOT EXISTS embedding_state (
                node_id TEXT NOT NULL,
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                input_version TEXT NOT NULL DEFAULT 'baseline_v1',
                text_hash TEXT NOT NULL,
                point_id TEXT NOT NULL,
                embedded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (node_id, model, dimensions, input_version)
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def reset_graph(self) -> None:
        self.conn.executescript(
            "DELETE FROM node_fts; DELETE FROM edges; DELETE FROM nodes; DELETE FROM embedding_state;"
        )
        self.conn.commit()

    @staticmethod
    def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"Expected object at {path}:{line_number}")
                yield value

    def ingest_nodes(
        self,
        rows: Iterable[dict[str, Any]],
        batch_size: int = 5_000,
        index_fts: bool = True,
    ) -> int:
        count = 0
        node_batch: list[tuple[Any, ...]] = []
        fts_batch: list[tuple[str, str]] = []
        parent_edge_batch: list[tuple[Any, ...]] = []

        def flush() -> None:
            if not node_batch:
                return
            if index_fts:
                self.conn.executemany(
                    "DELETE FROM node_fts WHERE node_id = ?", ((r[0],) for r in node_batch)
                )
            self.conn.executemany(
                """
                INSERT INTO nodes (
                    id, node_type, parent_id, source_id, title, label, text, locator, url,
                    authority_class, binding_status, hierarchy_rank, text_hash, searchable, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    node_type=excluded.node_type, parent_id=excluded.parent_id,
                    source_id=excluded.source_id, title=excluded.title, label=excluded.label,
                    text=excluded.text, locator=excluded.locator, url=excluded.url,
                    authority_class=excluded.authority_class,
                    binding_status=excluded.binding_status,
                    hierarchy_rank=excluded.hierarchy_rank, text_hash=excluded.text_hash,
                    searchable=excluded.searchable, raw_json=excluded.raw_json
                """,
                node_batch,
            )
            if index_fts:
                self.conn.executemany(
                    "INSERT INTO node_fts(node_id, content) VALUES (?, ?)", fts_batch
                )
            self.conn.executemany(
                """
                INSERT INTO edges(source, target, relation, provenance, weight, raw_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, target, relation, provenance) DO UPDATE SET
                    weight=excluded.weight, raw_json=excluded.raw_json
                """,
                parent_edge_batch,
            )
            self.conn.commit()
            node_batch.clear()
            fts_batch.clear()
            parent_edge_batch.clear()

        for node in rows:
            node_id = str(node.get("id", "")).strip()
            if not node_id:
                raise ValueError("Every node must have a non-empty id")
            content = searchable_text(node)
            digest = str(node.get("text_hash") or text_hash(content))
            raw = json.dumps(node, ensure_ascii=False, separators=(",", ":"))
            node_batch.append(
                (
                    node_id,
                    node.get("node_type"),
                    node.get("parent_id"),
                    node.get("source_id"),
                    node.get("title"),
                    node.get("label"),
                    node.get("text"),
                    node.get("locator"),
                    node.get("url"),
                    node.get("authority_class"),
                    node.get("binding_status"),
                    node.get("hierarchy_rank"),
                    digest,
                    content,
                    raw,
                )
            )
            if content and index_fts:
                fts_batch.append((node_id, content))
            parent_id = node.get("parent_id")
            if parent_id:
                edge = {
                    "source": str(parent_id),
                    "target": node_id,
                    "relation": "contains",
                    "provenance": "derived_parent_id",
                }
                parent_edge_batch.append(
                    (
                        str(parent_id),
                        node_id,
                        "contains",
                        "derived_parent_id",
                        1.0,
                        json.dumps(edge, ensure_ascii=False, separators=(",", ":")),
                    )
                )
            count += 1
            if count % batch_size == 0:
                flush()
        flush()
        return count

    def _upsert_edge(self, edge: dict[str, Any]) -> None:
        source = str(edge.get("source", "")).strip()
        target = str(edge.get("target", "")).strip()
        relation = str(edge.get("relation", "related_to")).strip() or "related_to"
        if not source or not target:
            raise ValueError("Every edge must have non-empty source and target")
        provenance = str(edge.get("provenance", ""))
        weight = float(edge.get("weight", 1.0))
        raw = json.dumps(edge, ensure_ascii=False, separators=(",", ":"))
        self.conn.execute(
            """
            INSERT INTO edges(source, target, relation, provenance, weight, raw_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, target, relation, provenance) DO UPDATE SET
                weight=excluded.weight, raw_json=excluded.raw_json
            """,
            (source, target, relation, provenance, weight, raw),
        )

    def ingest_edges(self, rows: Iterable[dict[str, Any]], batch_size: int = 10_000) -> int:
        count = 0
        edge_batch: list[tuple[Any, ...]] = []

        def flush() -> None:
            if not edge_batch:
                return
            self.conn.executemany(
                """
                INSERT INTO edges(source, target, relation, provenance, weight, raw_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, target, relation, provenance) DO UPDATE SET
                    weight=excluded.weight, raw_json=excluded.raw_json
                """,
                edge_batch,
            )
            self.conn.commit()
            edge_batch.clear()

        for edge in rows:
            source = str(edge.get("source", "")).strip()
            target = str(edge.get("target", "")).strip()
            relation = str(edge.get("relation", "related_to")).strip() or "related_to"
            if not source or not target:
                raise ValueError("Every edge must have non-empty source and target")
            provenance = str(edge.get("provenance", ""))
            weight = float(edge.get("weight", 1.0))
            raw = json.dumps(edge, ensure_ascii=False, separators=(",", ":"))
            edge_batch.append((source, target, relation, provenance, weight, raw))
            count += 1
            if count % batch_size == 0:
                flush()
        flush()
        return count

    def ingest_jsonl(
        self, nodes_path: str | Path, edges_path: str | Path, reset: bool = False
    ) -> tuple[int, int]:
        if reset:
            self.reset_graph()
        node_count = self.ingest_nodes(self.read_jsonl(nodes_path), index_fts=not reset)
        if reset:
            self.rebuild_fts()
        edge_count = self.ingest_edges(self.read_jsonl(edges_path))
        self.set_metadata("nodes_path", str(Path(nodes_path).resolve()))
        self.set_metadata("edges_path", str(Path(edges_path).resolve()))
        return node_count, edge_count

    def rebuild_fts(self) -> None:
        """Bulk-build FTS after a reset, which is much faster for a complete corpus load."""
        self.conn.execute("DELETE FROM node_fts")
        self.conn.execute(
            "INSERT INTO node_fts(node_id, content) "
            "SELECT id, searchable FROM nodes WHERE searchable <> ''"
        )
        self.conn.execute("INSERT INTO node_fts(node_fts) VALUES ('optimize')")
        self.conn.commit()

    def set_metadata(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_metadata(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def stats(self) -> dict[str, int]:
        return {
            "nodes": int(self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]),
            "edges": int(self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]),
            "embeddings": int(
                self.conn.execute("SELECT COUNT(*) FROM embedding_state").fetchone()[0]
            ),
        }

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return json.loads(row["raw_json"]) if row else None

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT raw_json FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return self._decode(row)

    def get_nodes(self, node_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = list(dict.fromkeys(node_ids))
        if not ids:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for offset in range(0, len(ids), 500):
            chunk = ids[offset : offset + 500]
            marks = ",".join("?" for _ in chunk)
            rows = self.conn.execute(
                f"SELECT id, raw_json FROM nodes WHERE id IN ({marks})", chunk
            ).fetchall()
            result.update({row["id"]: json.loads(row["raw_json"]) for row in rows})
        return result

    def lexical_search(
        self,
        query: str,
        limit: int = 20,
        node_types: list[str] | None = None,
        authority_classes: list[str] | None = None,
    ) -> list[SearchHit]:
        tokens = TOKEN_RE.findall(query)
        if not tokens:
            return []
        # Natural-language questions contain words absent from the legal provision. OR keeps
        # recall high while BM25 still rewards nodes matching several important terms.
        fts_query = " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
        clauses = ["node_fts MATCH ?"]
        params: list[Any] = [fts_query]
        if node_types:
            clauses.append("n.node_type IN (%s)" % ",".join("?" for _ in node_types))
            params.extend(node_types)
        if authority_classes:
            clauses.append("n.authority_class IN (%s)" % ",".join("?" for _ in authority_classes))
            params.extend(authority_classes)
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT n.id, n.raw_json, bm25(node_fts) AS rank
            FROM node_fts JOIN nodes n ON n.id = node_fts.node_id
            WHERE {" AND ".join(clauses)}
            ORDER BY rank ASC LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            SearchHit(
                node_id=row["id"],
                score=1.0 / (1.0 + abs(float(row["rank"]))),
                channel="lexical",
                node=json.loads(row["raw_json"]),
            )
            for row in rows
        ]

    def neighbors(
        self,
        node_ids: Iterable[str],
        hops: int = 1,
        per_node_limit: int = 30,
    ) -> list[dict[str, Any]]:
        frontier = set(node_ids)
        seen = set(frontier)
        output: list[dict[str, Any]] = []
        for depth in range(1, max(0, hops) + 1):
            next_frontier: set[str] = set()
            for node_id in frontier:
                rows = self.conn.execute(
                    """
                    SELECT source, target, relation, provenance, weight
                    FROM edges WHERE source = ? OR target = ?
                    LIMIT ?
                    """,
                    (node_id, node_id, per_node_limit),
                ).fetchall()
                for row in rows:
                    other = row["target"] if row["source"] == node_id else row["source"]
                    output.append(
                        {
                            "source": row["source"],
                            "target": row["target"],
                            "relation": row["relation"],
                            "provenance": row["provenance"],
                            "weight": row["weight"],
                            "depth": depth,
                            "neighbor_id": other,
                        }
                    )
                    if other not in seen:
                        seen.add(other)
                        next_frontier.add(other)
            frontier = next_frontier
            if not frontier:
                break
        return output

    def edges_for(
        self,
        node_ids: Iterable[str],
        relations: Iterable[str] | None = None,
        limit_per_node: int = 60,
    ) -> list[dict[str, Any]]:
        """Edges touching each node, in either direction, oriented away from that node.

        Returns `from_id` (the node asked about) and `neighbor_id` (the other end) so callers
        can traverse without re-deriving direction. Unlike `neighbors`, this applies a
        relation filter in SQL and orients each row, which typed traversal needs.
        """
        ids = list(dict.fromkeys(node_ids))
        if not ids:
            return []
        relation_list = list(relations) if relations is not None else None
        if relation_list is not None and not relation_list:
            return []

        output: list[dict[str, Any]] = []
        for node_id in ids:
            params: list[Any] = [node_id, node_id]
            clause = ""
            if relation_list is not None:
                clause = " AND relation IN (%s)" % ",".join("?" for _ in relation_list)
                params.extend(relation_list)
            params.append(limit_per_node)
            rows = self.conn.execute(
                f"""
                SELECT source, target, relation, provenance, weight
                FROM edges
                WHERE (source = ? OR target = ?){clause}
                LIMIT ?
                """,
                params,
            ).fetchall()
            for row in rows:
                neighbour = row["target"] if row["source"] == node_id else row["source"]
                if neighbour == node_id:
                    continue
                output.append(
                    {
                        "from_id": node_id,
                        "neighbor_id": neighbour,
                        "source": row["source"],
                        "target": row["target"],
                        "relation": row["relation"],
                        "provenance": row["provenance"],
                        "weight": row["weight"],
                    }
                )
        return output

    def embedding_state_has_input_version(self) -> bool:
        """False for databases created before embedding input versioning was introduced."""
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(embedding_state)").fetchall()
        }
        return "input_version" in columns

    def require_embedding_state_migration(self) -> None:
        if not self.embedding_state_has_input_version():
            raise RuntimeError(
                "embedding_state predates embedding input versioning. Run:\n"
                "  python scripts/migrations/001_embedding_state_input_version.py "
                f"--sqlite {self.path}\n"
                "The migration preserves existing rows and labels them input_version='baseline_v1'."
            )

    def embedding_candidates(
        self,
        model: str,
        dimensions: int,
        max_chars: int,
        force: bool = False,
        input_version: str = "baseline_v1",
        content_only: bool = False,
    ) -> Iterator[tuple[dict[str, Any], str, str]]:
        """Yield (node, embedding_input_text, content_hash) for nodes needing embedding.

        Nodes whose embedding input is empty under the chosen version are skipped: under
        text-focused versions a metadata-only node has nothing to embed. The count of skipped
        nodes is therefore a property of the input version and is reported by embedding_plan.
        """
        self.require_embedding_state_migration()
        query = """
            SELECT n.raw_json, n.text_hash,
                   e.text_hash AS embedded_hash
            FROM nodes n
            LEFT JOIN embedding_state e
              ON e.node_id=n.id AND e.model=? AND e.dimensions=? AND e.input_version=?
        """
        for row in self.conn.execute(query, (model, dimensions, input_version)):
            node = json.loads(row["raw_json"])
            if content_only and content_class(node) == EMPTY:
                # A structural container has no text to embed. Under text-focused input
                # versions it would otherwise be embedded from its title alone, producing a
                # vector that retrieval is configured never to return as evidence.
                continue
            content = build_embedding_input(node, version=input_version, max_chars=max_chars)
            if not content.strip():
                continue
            digest = text_hash(content)
            if force or row["embedded_hash"] != digest:
                yield node, content, digest

    def embedding_plan(
        self,
        model: str,
        dimensions: int,
        max_chars: int,
        force: bool = False,
        input_version: str = "baseline_v1",
        content_only: bool = False,
    ) -> dict[str, Any]:
        count = 0
        characters = 0
        for _, content, _ in self.embedding_candidates(
            model=model,
            dimensions=dimensions,
            max_chars=max_chars,
            force=force,
            input_version=input_version,
            content_only=content_only,
        ):
            count += 1
            characters += len(content)
        total_nodes = int(self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0])
        return {
            "input_version": input_version,
            "nodes_to_embed": count,
            "characters_to_embed": characters,
            "rough_tokens": characters // 4,
            "nodes_in_graph": total_nodes,
        }

    def mark_embedded(
        self,
        entries: Iterable[tuple[str, str, int, str, str]],
        input_version: str = "baseline_v1",
    ) -> None:
        self.require_embedding_state_migration()
        self.conn.executemany(
            """
            INSERT INTO embedding_state(
                node_id, model, dimensions, input_version, text_hash, point_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id, model, dimensions, input_version) DO UPDATE SET
                text_hash=excluded.text_hash, point_id=excluded.point_id,
                embedded_at=CURRENT_TIMESTAMP
            """,
            [
                (node_id, model, dimensions, input_version, digest, point_id)
                for node_id, model, dimensions, digest, point_id in entries
            ],
        )
        self.conn.commit()

    def embedding_index_state(self) -> list[dict[str, Any]]:
        """Per (model, dimensions, input_version) vector counts, for index manifests."""
        if not self.embedding_state_has_input_version():
            return []
        return [
            {
                "model": row[0],
                "dimensions": int(row[1]),
                "input_version": row[2],
                "vectors": int(row[3]),
                "first_embedded_at": row[4],
                "last_embedded_at": row[5],
            }
            for row in self.conn.execute(
                """
                SELECT model, dimensions, input_version, COUNT(*),
                       MIN(embedded_at), MAX(embedded_at)
                FROM embedding_state
                GROUP BY model, dimensions, input_version
                ORDER BY 4 DESC
                """
            )
        ]
