"""verification/pubmed_client.py — NCBI E-utilities (esearch→esummary, JSON mode)."""

from __future__ import annotations

from typing import Optional

import httpx

from . import http_client
from .models import ExternalRecord

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def _parse(item: dict) -> ExternalRecord:
    doi = None
    for aid in item.get("articleids", []) or []:
        if aid.get("idtype") == "doi":
            doi = aid.get("value")
            break
    year = None
    pubdate = item.get("pubdate") or ""
    if pubdate[:4].isdigit():
        year = int(pubdate[:4])
    return ExternalRecord(
        source="pubmed",
        title=item.get("title", "").rstrip("."),
        authors=[a.get("name") for a in item.get("authors", []) if a.get("name")],
        year=year,
        journal=item.get("fulljournalname") or item.get("source"),
        doi=doi,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{item.get('uid')}/" if item.get("uid") else None,
        raw={"uid": item.get("uid")},
    )


async def search(client: httpx.AsyncClient, query: str, rows: int = 5) -> list[ExternalRecord]:
    es = await http_client.get_json(
        client, _ESEARCH,
        params={"db": "pubmed", "term": query[:300], "retmax": rows, "retmode": "json"},
    )
    if es is None:
        return None
    ids = (es.get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []
    summ = await http_client.get_json(
        client, _ESUMMARY,
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
    )
    result = (summ or {}).get("result") or {}
    return [_parse(result[i]) for i in ids if i in result]


async def lookup_doi(client: httpx.AsyncClient, doi: str) -> Optional[ExternalRecord]:
    records = await search(client, f"{doi}[doi]", rows=1)
    return records[0] if records else None
