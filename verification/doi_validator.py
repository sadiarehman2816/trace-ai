"""verification/doi_validator.py — offline DOI syntax check + live resolution.

Timeout returns None, never reported as 'broken' — no false accusations on
network blips."""

from __future__ import annotations

import re
from typing import Optional

import httpx

from . import http_client

_DOI_SYNTAX = re.compile(r"^10\.\d{4,9}/\S+$")


def is_valid_syntax(doi: str) -> bool:
    return bool(_DOI_SYNTAX.match(doi.strip()))


async def resolves(client: httpx.AsyncClient, doi: str) -> Optional[bool]:
    """True = doi.org resolves it, False = definitively not found, None = inconclusive."""
    if not is_valid_syntax(doi):
        return False
    return await http_client.head_resolves(client, f"https://doi.org/{doi}")


async def url_alive(client: httpx.AsyncClient, url: str) -> Optional[bool]:
    return await http_client.head_resolves(client, url)
