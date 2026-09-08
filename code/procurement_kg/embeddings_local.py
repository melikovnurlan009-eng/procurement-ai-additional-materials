"""Local, self-hosted embeddings via sentence-transformers.

Added because the hosted embedding endpoint is unavailable (the configured NVIDIA key
returns 403) and because an internally deployable system cannot depend on a third-party
endpoint. A local open-weights model is also strictly better for reproducibility: it is
pinned by revision hash rather than by a provider alias that can change under you.

Optional dependency: install with `pip install -e '.[local-embeddings]'`.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# Query/passage prefixes are model-specific and materially affect retrieval quality.
# E5-family models are asymmetric and REQUIRE them; BGE-M3 and Arctic v2.0 do not use them.
MODEL_PREFIXES: dict[str, dict[str, str]] = {
    "intfloat/e5-large-v2": {"query": "query: ", "passage": "passage: "},
    "intfloat/e5-base-v2": {"query": "query: ", "passage": "passage: "},
    "intfloat/multilingual-e5-large": {"query": "query: ", "passage": "passage: "},
    "BAAI/bge-m3": {"query": "", "passage": ""},
    "Snowflake/snowflake-arctic-embed-l-v2.0": {"query": "", "passage": ""},
    "Qwen/Qwen3-Embedding-0.6B": {"query": "", "passage": ""},
}

DEFAULT_PREFIXES = {"query": "", "passage": ""}


class LocalEmbedder:
    """Drop-in replacement for OpenAIEmbedder backed by a local model.

    Exposes the same `embed` / `embed_query` interface, plus `model` and `dimensions`, so the
    ingestion and retrieval paths need no special-casing.
    """

    def __init__(
        self,
        model: str = "BAAI/bge-m3",
        device: str | None = None,
        normalize: bool = True,
        revision: str | None = None,
        batch_size: int = 32,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise ImportError(
                "LocalEmbedder needs sentence-transformers. "
                "Install with: pip install 'sentence-transformers>=3,<6'"
            ) from exc

        if device is None:
            import torch

            device = (
                "cuda" if torch.cuda.is_available()
                else "mps" if torch.backends.mps.is_available()
                else "cpu"
            )

        kwargs: dict[str, Any] = {"device": device}
        if revision:
            kwargs["revision"] = revision
        self.encoder = SentenceTransformer(model, **kwargs)
        self.model = model
        self.device = device
        self.revision = revision
        self.normalize = normalize
        self.batch_size = batch_size
        # renamed in sentence-transformers 6; support both
        getter = getattr(self.encoder, "get_embedding_dimension", None) or (
            self.encoder.get_sentence_embedding_dimension
        )
        self.dimensions = int(getter())
        self.prefixes = MODEL_PREFIXES.get(model, DEFAULT_PREFIXES)

    def _encode(self, texts: Sequence[str], prefix: str) -> list[list[float]]:
        if not texts:
            return []
        prepared = [f"{prefix}{text}" for text in texts]
        vectors = self.encoder.encode(
            prepared,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(list(texts), self.prefixes["passage"])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text], self.prefixes["query"])[0]

    def manifest(self) -> dict[str, Any]:
        """Everything needed to rebuild this exact embedder later."""
        return {
            "provider": "local:sentence-transformers",
            "model": self.model,
            "revision": self.revision or "UNPINNED - record the resolved commit before publishing",
            "dimensions": self.dimensions,
            "device": self.device,
            "normalize_embeddings": self.normalize,
            "query_prefix": self.prefixes["query"],
            "passage_prefix": self.prefixes["passage"],
        }
