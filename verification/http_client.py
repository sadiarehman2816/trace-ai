"""verification/http_client.py — cross-cutting HTTP concerns, once.

Disk cache (7-day TTL), retry + exponential backoff (honours Retry-After),
per-host rate limiting, polite User-Agent with mailto. Provider clients stay
parse-only. A failure returns None — the pipeline never stops on a provider.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx

CACHE_DIR = Path(os.environ.get("TRACE_AI_CACHE_DIR", ".api_cache"))
CACHE_TTL_SECONDS = 7 * 24 * 3600
MAILTO = os.environ.get("TRACE_AI_MAILTO", "contact@iasrd.com")
USER_AGENT = f"TRACE-AI/2.0 (https://iasrd.com; mailto:{MAILTO})"

# Per-host minimum interval between requests (seconds).
_HOST_INTERVALS = {
    "api.semanticscholar.org": 1.1,   # unauthenticated S2 ≈ 1 req/s
    "export.arxiv.org": 3.0,          # arXiv asks for 1 req / 3 s
    "eutils.ncbi.nlm.nih.gov": 0.4,   # ≤3 req/s without key
    "api.crossref.org": 0.1,
    "api.openalex.org": 0.1,
    "doi.org": 0.2,
}
_DEFAULT_INTERVAL = 0.2
_MAX_RETRIES = 3
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)

_host_locks: dict[str, asyncio.Lock] = {}
_host_last_request: dict[str, float] = {}


def _cache_key(method: str, url: str, params: Optional[dict]) -> Path:
    blob = json.dumps({"m": method, "u": url, "p": params or {}}, sort_keys=True)
    return CACHE_DIR / (hashlib.sha256(blob.encode()).hexdigest() + ".json")


def _cache_read(path: Path) -> Optional[dict]:
    try:
        if path.exists() and (time.time() - path.stat().st_mtime) < CACHE_TTL_SECONDS:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _cache_write(path: Path, payload: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


async def _respect_rate_limit(host: str) -> None:
    lock = _host_locks.setdefault(host, asyncio.Lock())
    interval = _HOST_INTERVALS.get(host, _DEFAULT_INTERVAL)
    async with lock:
        last = _host_last_request.get(host, 0.0)
        wait = last + interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _host_last_request[host] = time.monotonic()


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    use_cache: bool = True,
) -> Optional[dict]:
    """GET a JSON endpoint. Returns the parsed body, or None on any failure."""
    key = _cache_key("GET", url, params)
    if use_cache:
        cached = _cache_read(key)
        if cached is not None:
            return cached

    host = httpx.URL(url).host or ""
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}

    for attempt in range(_MAX_RETRIES):
        await _respect_rate_limit(host)
        try:
            resp = await client.get(url, params=params, headers=hdrs, timeout=_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if use_cache:
                    _cache_write(key, data)
                return data
            if resp.status_code == 404:
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt)
                await asyncio.sleep(min(delay, 30))
                continue
            return None
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            await asyncio.sleep(2 ** attempt)
    return None


async def get_text(
    client: httpx.AsyncClient,
    url: str,
    params: Optional[dict] = None,
    use_cache: bool = True,
) -> Optional[str]:
    """GET a text endpoint (arXiv Atom XML). Returns body text, or None."""
    key = _cache_key("GET-TEXT", url, params)
    if use_cache:
        cached = _cache_read(key)
        if cached is not None:
            return cached.get("text")

    host = httpx.URL(url).host or ""
    for attempt in range(_MAX_RETRIES):
        await _respect_rate_limit(host)
        try:
            resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT)
            if resp.status_code == 200:
                if use_cache:
                    _cache_write(key, {"text": resp.text})
                return resp.text
            if resp.status_code == 404:
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except httpx.HTTPError:
            await asyncio.sleep(2 ** attempt)
    return None


async def head_resolves(client: httpx.AsyncClient, url: str) -> Optional[bool]:
    """HEAD a URL. True = resolves, False = definitively broken, None = inconclusive.

    Timeouts / network errors return None — never reported as 'broken', so a
    network blip can't produce a false accusation.
    """
    host = httpx.URL(url).host or ""
    await _respect_rate_limit(host)
    try:
        resp = await client.head(
            url, headers={"User-Agent": USER_AGENT},
            timeout=_TIMEOUT, follow_redirects=True,
        )
        if resp.status_code < 400:
            return True
        if resp.status_code in (404, 410):
            return False
        if resp.status_code in (403, 405):   # HEAD blocked ≠ broken
            return None
        return None
    except httpx.HTTPError:
        return None


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True)
