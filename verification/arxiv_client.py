"""verification/arxiv_client.py — arXiv Atom API (stdlib XML parsing).

1 req / 3 s honoured centrally in http_client."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

from . import http_client
from .models import ExternalRecord

_BASE = "https://export.arxiv.org/api/query"
_NS = {"a": "http://www.w3.org/2005/Atom"}


def _parse_entry(entry) -> ExternalRecord:
    title = (entry.findtext("a:title", default="", namespaces=_NS) or "").strip()
    title = re.sub(r"\s+", " ", title)
    authors = [
        (a.findtext("a:name", default="", namespaces=_NS) or "").strip()
        for a in entry.findall("a:author", _NS)
    ]
    published = entry.findtext("a:published", default="", namespaces=_NS) or ""
    year = int(published[:4]) if published[:4].isdigit() else None
    link = entry.findtext("a:id", default=None, namespaces=_NS)
    doi = None
    for el in entry.iter():
        if el.tag.endswith("doi") and el.text:
            doi = el.text.strip()
    return ExternalRecord(
        source="arxiv", title=title or None, authors=[a for a in authors if a],
        year=year, journal="arXiv", doi=doi, url=link, raw={},
    )


def _parse_feed(xml_text: str) -> list[ExternalRecord]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    return [_parse_entry(e) for e in root.findall("a:entry", _NS)]


async def lookup_id(client: httpx.AsyncClient, arxiv_id: str) -> Optional[ExternalRecord]:
    text = await http_client.get_text(client, _BASE, params={"id_list": arxiv_id, "max_results": 1})
    records = _parse_feed(text) if text else []
    return records[0] if records else None


async def search_title(client: httpx.AsyncClient, title: str, rows: int = 5) -> list[ExternalRecord]:
    safe = re.sub(r'[":\\]', " ", title)[:200]
    text = await http_client.get_text(
        client, _BASE, params={"search_query": f"ti:{safe}", "max_results": rows},
    )
    if text is None:
        return None
    return _parse_feed(text)
