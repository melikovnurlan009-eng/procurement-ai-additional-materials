from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from qdrant_client import QdrantClient, models


POINT_NAMESPACE = uuid.UUID("fe591eec-908d-5f15-8097-c757e295af96")


def point_id_for_node(node_id: str) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, node_id))


class QdrantVectorStore:
    def __init__(
        self,
        url: str,
        collection: str,
        dimensions: int,
        api_key: str | None = None,
    ):
        if url in {":memory:", "memory"}:
            self.client = QdrantClient(location=":memory:")
        else:
            self.client = QdrantClient(url=url, api_key=api_key, timeout=60)
        self.collection = collection
        self.dimensions = dimensions

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            info = self.client.get_collection(self.collection)
            configured = getattr(info.config.params.vectors, "size", None)
            if configured is not None and int(configured) != self.dimensions:
                raise ValueError(
                    f"Qdrant collection has {configured} dimensions, expected {self.dimensions}. "
                    "Use a different QDRANT_COLLECTION or recreate the existing collection."
                )
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=self.dimensions,
                distance=models.Distance.COSINE,
                on_disk=True,
            ),
            on_disk_payload=True,
        )
        for field in ("node_type", "authority_class", "binding_status", "source_id"):
            self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

    def upsert(
        self,
        nodes: Sequence[dict[str, Any]],
        vectors: Sequence[Sequence[float]],
    ) -> list[str]:
        if len(nodes) != len(vectors):
            raise ValueError("nodes and vectors must have the same length")
        point_ids = [point_id_for_node(str(node["id"])) for node in nodes]
        points = []
        for point_id, node, vector in zip(point_ids, nodes, vectors, strict=True):
            payload = {
                "node_id": node["id"],
                "node_type": node.get("node_type"),
                "parent_id": node.get("parent_id"),
                "source_id": node.get("source_id"),
                "title": node.get("title"),
                "label": node.get("label"),
                "locator": node.get("locator"),
                "url": node.get("url"),
                "authority_class": node.get("authority_class"),
                "binding_status": node.get("binding_status"),
                "hierarchy_rank": node.get("hierarchy_rank"),
            }
            payload = {key: value for key, value in payload.items() if value is not None}
            points.append(models.PointStruct(id=point_id, vector=list(vector), payload=payload))
        self.client.upsert(collection_name=self.collection, points=points, wait=True)
        return point_ids

    @staticmethod
    def _filter(
        node_types: list[str] | None,
        authority_classes: list[str] | None,
    ) -> models.Filter | None:
        conditions: list[models.FieldCondition] = []
        if node_types:
            conditions.append(
                models.FieldCondition(key="node_type", match=models.MatchAny(any=node_types))
            )
        if authority_classes:
            conditions.append(
                models.FieldCondition(
                    key="authority_class", match=models.MatchAny(any=authority_classes)
                )
            )
        return models.Filter(must=conditions) if conditions else None

    def search(
        self,
        vector: Sequence[float],
        limit: int = 20,
        node_types: list[str] | None = None,
        authority_classes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        response = self.client.query_points(
            collection_name=self.collection,
            query=list(vector),
            query_filter=self._filter(node_types, authority_classes),
            with_payload=True,
            limit=limit,
        )
        return [
            {
                "node_id": str(point.payload["node_id"]),
                "score": float(point.score),
                "payload": dict(point.payload or {}),
            }
            for point in response.points
            if point.payload and point.payload.get("node_id")
        ]
