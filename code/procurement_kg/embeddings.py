from __future__ import annotations

from collections.abc import Sequence

from openai import OpenAI


class OpenAIEmbedder:
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: str | None = None,
    ):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for semantic embeddings")
        kwargs: dict[str, object] = {"api_key": api_key, "max_retries": 5, "timeout": 90.0}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(
            model=self.model,
            input=list(texts),
            dimensions=self.dimensions,
            encoding_format="float",
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(texts):
            raise RuntimeError("Embedding API returned a different number of vectors than inputs")
        return [item.embedding for item in ordered]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]
