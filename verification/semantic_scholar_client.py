"""verification/semantic_scholar_client.py — Semantic Scholar Graph API (parse-only).

Optional TRACE_AI_S2_KEY env var; unauthenticated ≈ 1 req/s (enforced centrally
in http_client)."""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote

import httpx

from . import http_client
from .models import ExternalRecord

_BASE = "https://api.semanticscholar.org/graph/v1/paper"
_FIELDS = "title,authors,year,venue,externalIds,url"


def _headers() -> dict:
    key = os.environ.get("TRACE_AI_S2_KEY")
    return {"x-api-key": key} if key else {}


def _parse(item: dict) -> ExternalRecord:
    ext = item.get("externalIds") or {}
    return ExternalRecord(
        source="semantic_scholar",
        title=item.get("title"),
        authors=[a.get("name") for a in item.get("authors", []) if a.get("name")],
        year=item.get("year"),
        journal=item.get("venue"),
        doi=ext.get("DOI"),
        url=item.get("url"),
        raw={"paperId": item.get("paperId")},
    )


async def lookup_doi(client: httpx.AsyncClient, doi: str) -> Optional[ExternalRecord]:
    data = await http_client.get_json(
        client, f"{_BASE}/DOI:{quote(doi, safe='/')}",
        params={"fields": _FIELDS}, headers=_headers(),
    )
    return _parse(data) if data and (data.get("title") or data.get("paperId")) else None


async def search_title(client: httpx.AsyncClient, title: str, rows: int = 5) -> list[ExternalRecord]:
    data = await http_client.get_json(
        client, f"{_BASE}/search",
        params={"query": title[:300], "limit": rows, "fields": _FIELDS},
        headers=_headers(),
    )
    if data is None:
        return None
    return [_parse(i) for i in data.get("data", [])]
