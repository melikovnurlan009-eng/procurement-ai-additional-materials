from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .config import Settings
from .graph_store import GraphStore
from .llm import GraphAnswerer
from .retrieval_profile import get_profile
from .retrieval_v2 import ProfiledRetriever
from .retriever import HybridRetriever, RetrievedNode
from .vector_store import QdrantVectorStore


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8_000)
    limit: int = Field(default=12, ge=1, le=100)
    candidates: int | None = Field(default=None, ge=5, le=300)
    graph_hops: int | None = Field(default=None, ge=0, le=3)
    semantic: bool = True
    node_types: list[str] | None = None
    authority_classes: list[str] | None = None


class AnswerRequest(SearchRequest):
    limit: int = Field(default=16, ge=1, le=60)


def create_app(settings: Settings | None = None) -> FastAPI:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    cfg = settings or Settings.from_env()
    cfg.ensure_state_dir()
    graph = GraphStore(cfg.sqlite_path)

    from .cli import build_embedder

    embedder = None
    vectors = None
    answerer = None
    if cfg.embedding_provider == "local" or cfg.embedding_api_key:
        embedder = build_embedder(cfg)
    if embedder is not None:
        vectors = QdrantVectorStore(
            url=cfg.qdrant_url,
            api_key=cfg.qdrant_api_key,
            collection=cfg.qdrant_collection,
            dimensions=embedder.dimensions,
        )
    if cfg.chat_api_key:
        answerer = GraphAnswerer(
            api_key=cfg.chat_api_key,
            model=cfg.chat_model,
            base_url=cfg.chat_base_url,
        )
    profile_name = cfg.retrieval_profile
    use_profiled = profile_name != "baseline_v1"
    retriever = HybridRetriever(graph=graph, embedder=embedder, vectors=vectors)
    profiled = (
        ProfiledRetriever(graph=graph, embedder=embedder, vectors=vectors, profile=profile_name)
        if use_profiled
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        graph.close()

    app = FastAPI(
        title="Procurement Knowledge Graph RAG",
        version="1.0.0",
        description="Hybrid semantic, lexical and graph retrieval with cited LLM answers.",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "graph": graph.stats(),
            "semantic_configured": embedder is not None,
            "answering_configured": answerer is not None,
            "chat_model": cfg.chat_model,
            "embedding_model": getattr(embedder, "model", cfg.embedding_model),
            "embedding_provider": cfg.embedding_provider,
            "embedding_dimensions": getattr(embedder, "dimensions", None),
            "embedding_input_version": cfg.embedding_input_version,
            "retrieval_profile": profile_name,
            "retrieval_profile_fingerprint": get_profile(profile_name).fingerprint(),
            "qdrant_collection": cfg.qdrant_collection,
            "vector_index": _vector_index_state(),
        }

    def _vector_index_state() -> dict[str, Any]:
        """Reported so a caller can tell a complete index from a partial one."""
        if vectors is None:
            return {"available": False, "reason": "no embedder configured"}
        try:
            info = vectors.client.get_collection(cfg.qdrant_collection)
            return {
                "available": True,
                "points": info.points_count,
                "status": str(info.status),
                "dimensions": info.config.params.vectors.size,
            }
        except Exception as exc:
            return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}

    @app.get("/nodes/by-id")
    def node_by_id(node_id: str = Query(min_length=1)) -> dict[str, Any]:
        node = graph.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        return node

    @app.get("/neighbors")
    def neighbors(
        node_id: str = Query(min_length=1),
        hops: int = Query(default=1, ge=1, le=3),
        per_node_limit: int = Query(default=30, ge=1, le=200),
    ) -> dict[str, Any]:
        if not graph.get_node(node_id):
            raise HTTPException(status_code=404, detail="Node not found")
        links = graph.neighbors([node_id], hops=hops, per_node_limit=per_node_limit)
        nodes = graph.get_nodes(link["neighbor_id"] for link in links)
        return {"node_id": node_id, "links": links, "nodes": nodes}

    @app.post("/search")
    def search(request: SearchRequest) -> dict[str, Any]:
        if profiled is not None:
            result = profiled.search(
                query=request.query,
                semantic=request.semantic,
                limit=request.limit,
                node_types=request.node_types,
                authority_classes=request.authority_classes,
            )
            return result.as_dict()
        try:
            results = retriever.search(
                query=request.query,
                limit=request.limit,
                candidates=request.candidates or cfg.search_candidates,
                graph_hops=(
                    request.graph_hops if request.graph_hops is not None else cfg.graph_hops
                ),
                semantic=request.semantic,
                node_types=request.node_types,
                authority_classes=request.authority_classes,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "query": request.query,
            "count": len(results),
            "results": [r.as_dict() for r in results],
        }

    @app.post("/answer")
    def answer(request: AnswerRequest) -> dict[str, Any]:
        if not answerer:
            raise HTTPException(
                status_code=503,
                detail="A model API key and endpoint are required for answers",
            )
        retrieval_diagnostics: dict[str, Any] = {}
        try:
            if profiled is not None:
                profiled_result = profiled.search(
                    query=request.query,
                    semantic=True,
                    limit=request.limit,
                    node_types=request.node_types,
                    authority_classes=request.authority_classes,
                )
                retrieval_diagnostics = {
                    "profile": profiled_result.profile,
                    "profile_fingerprint": profiled_result.profile_fingerprint,
                    **profiled_result.diagnostics,
                }
                results = [
                    RetrievedNode(
                        node_id=candidate.node_id,
                        score=candidate.final_score,
                        node=candidate.node,
                        channels=candidate.channels,
                        graph_links=candidate.graph_path,
                    )
                    for candidate in profiled_result.results
                ]
            else:
                results = retriever.search(
                    query=request.query,
                    limit=request.limit,
                    candidates=request.candidates or cfg.search_candidates,
                    graph_hops=(
                        request.graph_hops if request.graph_hops is not None else cfg.graph_hops
                    ),
                    semantic=True,
                    node_types=request.node_types,
                    authority_classes=request.authority_classes,
                )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        try:
            result = answerer.answer(
                question=request.query,
                results=results,
                context_chars=cfg.answer_context_chars,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Model provider error: {exc}") from exc
        return {**result.as_dict(), "retrieval": retrieval_diagnostics}

    return app


app = create_app()
