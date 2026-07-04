"""verification/openalex_client.py — OpenAlex API (parse-only)."""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import httpx

from . import http_client
from .models import ExternalRecord

_BASE = "https://api.openalex.org/works"


def _parse(item: dict) -> ExternalRecord:
    authors = []
    for auth in item.get("authorships", []) or []:
        name = (auth.get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    doi = item.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]
    loc = (item.get("primary_location") or {}).get("source") or {}
    return ExternalRecord(
        source="openalex",
        title=item.get("title"),
        authors=authors,
        year=item.get("publication_year"),
        journal=loc.get("display_name"),
        publisher=loc.get("host_organization_name"),
        doi=doi,
        url=(item.get("primary_location") or {}).get("landing_page_url") or item.get("id"),
        raw={"id": item.get("id")},
    )


async def lookup_doi(client: httpx.AsyncClient, doi: str) -> Optional[ExternalRecord]:
    data = await http_client.get_json(
        client, f"{_BASE}/https://doi.org/{quote(doi, safe='/')}",
        params={"mailto": http_client.MAILTO},
    )
    return _parse(data) if data and data.get("id") else None


async def search_title(client: httpx.AsyncClient, title: str, rows: int = 5) -> list[ExternalRecord]:
    data = await http_client.get_json(
        client, _BASE,
        params={"search": title[:300], "per-page": rows, "mailto": http_client.MAILTO},
    )
    if data is None:
        return None
    return [_parse(i) for i in data.get("results", [])]
