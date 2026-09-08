from __future__ import annotations

from typing import Any

import requests


def normalize_base_url(base_url: str) -> str:
    cleaned = base_url.strip()
    if not cleaned:
        return "http://127.0.0.1:8005"
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned.rstrip("/")
    return f"http://{cleaned.rstrip('/')}"


def build_search_payload(query: str, limit: int = 8, semantic: bool = True) -> dict[str, Any]:
    return {"query": query, "limit": limit, "semantic": semantic}


def build_answer_payload(query: str, limit: int = 8, semantic: bool = True) -> dict[str, Any]:
    return {"query": query, "limit": limit, "semantic": semantic}


def call_search(base_url: str, query: str, limit: int = 8, semantic: bool = True) -> dict[str, Any]:
    url = f"{normalize_base_url(base_url)}/search"
    response = requests.post(url, json=build_search_payload(query, limit=limit, semantic=semantic), timeout=30)
    response.raise_for_status()
    return response.json()


def call_answer(base_url: str, query: str, limit: int = 8, semantic: bool = True) -> dict[str, Any]:
    url = f"{normalize_base_url(base_url)}/answer"
    response = requests.post(url, json=build_answer_payload(query, limit=limit, semantic=semantic), timeout=60)
    response.raise_for_status()
    return response.json()
