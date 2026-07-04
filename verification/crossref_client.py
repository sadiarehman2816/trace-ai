"""verification/crossref_client.py — Crossref REST API (parse-only)."""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import httpx

from . import http_client
from .models import ExternalRecord

_BASE = "https://api.crossref.org/works"


def _parse(item: dict) -> ExternalRecord:
    authors = []
    for a in item.get("author", []) or []:
        family, given = a.get("family"), a.get("given")
        if family:
            authors.append(f"{family}, {given}" if given else family)
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    titles = item.get("title") or []
    containers = item.get("container-title") or []
    return ExternalRecord(
        source="crossref",
        title=titles[0] if titles else None,
        authors=authors,
        year=year,
        journal=containers[0] if containers else None,
        publisher=item.get("publisher"),
        doi=item.get("DOI"),
        url=item.get("URL"),
        raw=item,
    )


async def lookup_doi(client: httpx.AsyncClient, doi: str) -> Optional[ExternalRecord]:
    data = await http_client.get_json(client, f"{_BASE}/{quote(doi, safe='')}")
    msg = (data or {}).get("message")
    return _parse(msg) if msg else None


async def search_bibliographic(client: httpx.AsyncClient, query: str, rows: int = 5) -> list[ExternalRecord]:
    data = await http_client.get_json(
        client, _BASE,
        params={"query.bibliographic": query[:300], "rows": rows, "mailto": http_client.MAILTO},
    )
    if data is None:
        return None
    items = ((data.get("message") or {}).get("items")) or []
    return [_parse(i) for i in items]


async def search_title_author(client: httpx.AsyncClient, title: str, author: str, rows: int = 5) -> list[ExternalRecord]:
    data = await http_client.get_json(
        client, _BASE,
        params={"query.title": title[:300], "query.author": author[:100],
                "rows": rows, "mailto": http_client.MAILTO},
    )
    items = ((data or {}).get("message") or {}).get("items") or []
    return [_parse(i) for i in items]
