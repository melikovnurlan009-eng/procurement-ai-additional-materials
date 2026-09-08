from __future__ import annotations

from collections.abc import Callable
from itertools import islice
from typing import Iterator, TypeVar

from .embeddings import OpenAIEmbedder
from .graph_store import GraphStore
from .vector_store import QdrantVectorStore


T = TypeVar("T")


def batched(iterator: Iterator[T], size: int) -> Iterator[list[T]]:
    while batch := list(islice(iterator, size)):
        yield batch


def embed_graph(
    graph: GraphStore,
    embedder: OpenAIEmbedder,
    vectors: QdrantVectorStore,
    batch_size: int = 64,
    max_chars: int = 24_000,
    force: bool = False,
    progress: Callable[[int], None] | None = None,
    input_version: str = "baseline_v1",
    content_only: bool = False,
) -> int:
    """Embed changed nodes only, checkpointing after each successful Qdrant upsert.

    Refuses to write into a Qdrant collection that was previously built from a different
    embedding input version: mixing constructions inside one index would make retrieval
    results uninterpretable and is exactly the kind of silent contamination a versioned
    pipeline exists to prevent.
    """
    guard_key = f"index:{vectors.collection}:input_version"
    recorded = graph.get_metadata(guard_key)
    if recorded is not None and recorded != input_version:
        raise RuntimeError(
            f"Qdrant collection {vectors.collection!r} was built with input_version="
            f"{recorded!r}, but this run uses {input_version!r}. Use a different "
            "QDRANT_COLLECTION for the new version rather than mixing them."
        )
    vectors.ensure_collection()
    graph.set_metadata(guard_key, input_version)
    graph.set_metadata(f"index:{vectors.collection}:model", embedder.model)
    graph.set_metadata(f"index:{vectors.collection}:dimensions", str(embedder.dimensions))
    candidates = graph.embedding_candidates(
        model=embedder.model,
        dimensions=embedder.dimensions,
        max_chars=max_chars,
        force=force,
        input_version=input_version,
        content_only=content_only,
    )
    processed = 0
    for batch in batched(candidates, batch_size):
        nodes = [item[0] for item in batch]
        texts = [item[1] for item in batch]
        hashes = [item[2] for item in batch]
        embeddings = embedder.embed(texts)
        point_ids = vectors.upsert(nodes, embeddings)
        graph.mark_embedded(
            (
                (str(node["id"]), embedder.model, embedder.dimensions, digest, point_id)
                for node, digest, point_id in zip(nodes, hashes, point_ids, strict=True)
            ),
            input_version=input_version,
        )
        processed += len(batch)
        if progress:
            progress(processed)
    return processed
