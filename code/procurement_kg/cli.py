from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import Settings
from .embeddings import OpenAIEmbedder
from .evaluate import evaluate_retrieval, load_questions
from .graph_store import GraphStore
from .ingest import embed_graph
from .llm import GraphAnswerer
from .retriever import HybridRetriever
from .vector_store import QdrantVectorStore


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="procurement-kg",
        description="Ingest, embed, search and answer over the procurement knowledge graph.",
    )
    sub = root.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Stream nodes and edges JSONL into SQLite")
    ingest.add_argument("--nodes", required=True)
    ingest.add_argument("--edges", required=True)
    ingest.add_argument("--reset", action="store_true")

    embed = sub.add_parser("embed", help="Embed new or changed nodes into Qdrant")
    embed.add_argument("--force", action="store_true")
    embed.add_argument(
        "--input-version",
        help="Embedding input construction (default: EMBEDDING_INPUT_VERSION or baseline_v1)",
    )
    embed.add_argument(
        "--content-only",
        action="store_true",
        help="Skip structural nodes that have no text of their own",
    )

    plan = sub.add_parser("embedding-plan", help="Estimate the pending embedding workload")
    plan.add_argument("--force", action="store_true")
    plan.add_argument("--input-version")
    plan.add_argument("--content-only", action="store_true")

    sub.add_parser("embedding-inputs", help="Show the available embedding input versions")

    search = sub.add_parser("search", help="Search the indexed graph")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=12)
    search.add_argument("--lexical-only", action="store_true")
    search.add_argument("--graph-hops", type=int)

    ask = sub.add_parser("ask", help="Retrieve graph evidence and generate a cited answer")
    ask.add_argument("question")
    ask.add_argument("--limit", type=int, default=16)
    ask.add_argument("--graph-hops", type=int)

    evaluate = sub.add_parser("evaluate", help="Measure retrieval MRR and recall@k")
    evaluate.add_argument("--questions", required=True)
    evaluate.add_argument("--k", type=int, default=10)
    evaluate.add_argument("--lexical-only", action="store_true")
    evaluate.add_argument("--graph-hops", type=int)

    serve = sub.add_parser("serve", help="Run the FastAPI service")
    serve.add_argument("--reload", action="store_true")
    return root


def build_embedder(cfg: Settings):
    """Local open-weights model, or the configured hosted endpoint."""
    if cfg.embedding_provider == "local":
        from .embeddings_local import LocalEmbedder

        return LocalEmbedder(
            model=cfg.local_embedding_model,
            device=cfg.local_embedding_device,
            revision=cfg.local_embedding_revision,
            batch_size=cfg.embedding_batch_size,
        )
    if not cfg.embedding_api_key:
        return None
    return OpenAIEmbedder(
        cfg.embedding_api_key,
        cfg.embedding_model,
        cfg.embedding_dimensions,
        cfg.embedding_base_url,
    )


def components(cfg: Settings, require_openai: bool = True):
    local = cfg.embedding_provider == "local"
    if require_openai and not local and not cfg.embedding_api_key:
        raise SystemExit("EMBEDDING_API_KEY is required. Copy .env.example to .env and set it.")
    graph = GraphStore(cfg.sqlite_path)
    embedder = None
    vectors = None
    if local or cfg.embedding_api_key:
        embedder = build_embedder(cfg)
        # the model is the authority on its own width; a mismatched env var must not
        # silently create a collection the vectors cannot fit into
        dimensions = getattr(embedder, "dimensions", cfg.embedding_dimensions)
        vectors = QdrantVectorStore(
            cfg.qdrant_url,
            cfg.qdrant_collection,
            dimensions,
            cfg.qdrant_api_key,
        )
    return graph, embedder, vectors


def main(argv: list[str] | None = None) -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    args = parser().parse_args(argv)
    cfg = Settings.from_env()
    cfg.ensure_state_dir()

    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "procurement_kg.service:app",
            host=cfg.api_host,
            port=cfg.api_port,
            reload=args.reload,
        )
        return

    if args.command == "ingest":
        with GraphStore(cfg.sqlite_path) as graph:
            nodes, edges = graph.ingest_jsonl(args.nodes, args.edges, reset=args.reset)
            print(json.dumps({"ingested_nodes": nodes, "ingested_edges": edges, **graph.stats()}))
        return

    if args.command == "embedding-inputs":
        from .embedding_input import available_versions, describe

        print(json.dumps([describe(v) for v in available_versions()], indent=2))
        return

    if args.command == "embedding-plan":
        version = args.input_version or cfg.embedding_input_version
        with GraphStore(cfg.sqlite_path) as graph:
            result = graph.embedding_plan(
                cfg.embedding_model,
                cfg.embedding_dimensions,
                cfg.embedding_max_chars,
                force=args.force,
                input_version=version,
                content_only=args.content_only,
            )
            print(
                json.dumps(
                    {**result, "model": cfg.embedding_model, "dimensions": cfg.embedding_dimensions}
                )
            )
        return

    require_openai = args.command in {"embed", "ask"} or not getattr(args, "lexical_only", False)
    graph, embedder, vectors = components(cfg, require_openai=require_openai)
    try:
        if args.command == "embed":
            assert embedder and vectors
            version = args.input_version or cfg.embedding_input_version
            print(
                f"embedding input_version={version} model={cfg.embedding_model} "
                f"dimensions={cfg.embedding_dimensions} collection={cfg.qdrant_collection}",
                file=sys.stderr,
            )
            count = embed_graph(
                graph,
                embedder,
                vectors,
                batch_size=cfg.embedding_batch_size,
                max_chars=cfg.embedding_max_chars,
                force=args.force,
                progress=lambda n: print(f"embedded={n}", file=sys.stderr),
                input_version=version,
                content_only=args.content_only,
            )
            print(
                json.dumps(
                    {
                        "embedded_nodes": count,
                        "input_version": version,
                        "index_state": graph.embedding_index_state(),
                        **graph.stats(),
                    }
                )
            )
            return

        retriever = HybridRetriever(graph, embedder, vectors)
        hops = args.graph_hops if args.graph_hops is not None else cfg.graph_hops
        if args.command == "search":
            results = retriever.search(
                args.query,
                limit=args.limit,
                candidates=cfg.search_candidates,
                graph_hops=hops,
                semantic=not args.lexical_only,
            )
            print(
                json.dumps([result.as_dict() for result in results], ensure_ascii=False, indent=2)
            )
            return

        if args.command == "ask":
            if not cfg.chat_api_key:
                raise SystemExit("OPENAI_API_KEY is required for `ask`. Set it in .env.")
            results = retriever.search(
                args.question,
                limit=args.limit,
                candidates=cfg.search_candidates,
                graph_hops=hops,
                semantic=True,
            )
            answerer = GraphAnswerer(cfg.chat_api_key, cfg.chat_model, cfg.chat_base_url)
            answer = answerer.answer(args.question, results, cfg.answer_context_chars)
            print(json.dumps(answer.as_dict(), ensure_ascii=False, indent=2))
            return

        if args.command == "evaluate":
            questions = load_questions(args.questions)
            result = evaluate_retrieval(
                retriever,
                questions,
                k=args.k,
                semantic=not args.lexical_only,
                candidates=cfg.search_candidates,
                graph_hops=(args.graph_hops if args.graph_hops is not None else cfg.graph_hops),
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        graph.close()


if __name__ == "__main__":
    main()
