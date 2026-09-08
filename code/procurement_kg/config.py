from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _project_default_sqlite_path() -> Path:
    return PROJECT_ROOT / "state" / "procurement_kg.sqlite3"


def _sqlite_path_from_env() -> Path:
    project_default = _project_default_sqlite_path()
    env_value = os.getenv("KG_SQLITE_PATH")
    if not env_value:
        return project_default

    candidate = Path(env_value).expanduser()
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()

    if candidate.exists():
        try:
            with sqlite3.connect(candidate) as connection:
                node_count = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                fts_count = connection.execute("SELECT COUNT(*) FROM node_fts").fetchone()[0]
            if node_count and fts_count:
                return candidate
        except Exception:
            pass

    return project_default


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _nvidia_api_key() -> str | None:
    direct = os.getenv("NVIDIA_API_KEY") or os.getenv("EMBEDDING_API_KEY")
    if direct:
        return direct

    payload = os.getenv("NVIDIA_API_KEYS_JSON")
    if payload:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            for key in ("anar", "nurlan", "nurlan_1", "nurlan_2", "nurlan_4", "anar_2", "anar_3", "murad", "murad_2", "murad_3", "murad_4", "murad_5", "murad_6", "azerin", "zeyneb", "polad", "yusif", "rashad", "rashad_2", "rashad_3", "rashad_4", "rashad_5", "pavel", "akbar", "fidan", "dmitriy", "haciaga", "turan", "sebuhi", "lale", "ozcan", "polad_2", "polad_3", "polad_4", "polad_5", "polad_6", "polad_7", "polad_8", "polad_9", "polad_10", "polad_11", "uzeyir"):
                value = data.get(key)
                if isinstance(value, list) and value:
                    first = value[0]
                    if isinstance(first, str) and first.startswith("nvapi-"):
                        return first
    return None


def _nvidia_base_url() -> str | None:
    return os.getenv("NVIDIA_BASE_URL") or os.getenv("EMBEDDING_BASE_URL") or "https://integrate.api.nvidia.com/v1"


def _chat_api_key() -> str | None:
    return os.getenv("OPENAI_API_KEY") or None


def _chat_base_url() -> str | None:
    return os.getenv("OPENAI_BASE_URL") or None


@dataclass(frozen=True)
class Settings:
    sqlite_path: Path
    qdrant_url: str
    qdrant_api_key: str | None
    qdrant_collection: str
    embedding_api_key: str | None
    embedding_base_url: str | None
    chat_api_key: str | None
    chat_base_url: str | None
    chat_model: str
    embedding_model: str
    embedding_dimensions: int
    embedding_batch_size: int
    embedding_max_chars: int
    embedding_input_version: str
    embedding_provider: str
    retrieval_profile: str
    local_embedding_model: str
    local_embedding_device: str | None
    local_embedding_revision: str | None
    search_candidates: int
    graph_hops: int
    answer_context_chars: int
    api_host: str
    api_port: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            sqlite_path=_sqlite_path_from_env(),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "procurement_law_nodes"),
            embedding_api_key=_nvidia_api_key(),
            embedding_base_url=_nvidia_base_url(),
            chat_api_key=_chat_api_key(),
            chat_base_url=_chat_base_url(),
            chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_dimensions=_int("OPENAI_EMBEDDING_DIMENSIONS", 1536),
            embedding_batch_size=_int("EMBEDDING_BATCH_SIZE", 64),
            embedding_max_chars=_int("EMBEDDING_MAX_CHARS", 24_000),
            # Defaults to the frozen baseline construction so an unconfigured checkout
            # still reproduces baseline_v1 exactly. Set EMBEDDING_INPUT_VERSION to opt in.
            embedding_input_version=os.getenv("EMBEDDING_INPUT_VERSION", "baseline_v1"),
            # "local" runs an open-weights model on this machine (no API key, no network).
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "api"),
            # baseline_v1 keeps the frozen retriever; hybrid_v2 uses the repaired path.
            retrieval_profile=os.getenv("RETRIEVAL_PROFILE", "baseline_v1"),
            local_embedding_model=os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-m3"),
            local_embedding_device=os.getenv("LOCAL_EMBEDDING_DEVICE") or None,
            local_embedding_revision=os.getenv("LOCAL_EMBEDDING_REVISION") or None,
            search_candidates=_int("SEARCH_CANDIDATES", 40),
            graph_hops=_int("GRAPH_HOPS", 1),
            answer_context_chars=_int("ANSWER_CONTEXT_CHARS", 48_000),
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=_int("API_PORT", 8000),
        )

    def ensure_state_dir(self) -> None:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
