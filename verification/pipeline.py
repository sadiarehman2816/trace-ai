"""verification/pipeline.py — orchestrator.

verify_document() is sync and Streamlit-safe: it spawns its own event loop,
or a worker thread if a loop is already running.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from . import citation_matcher, claim_verifier, external_verifier, http_client
from . import reference_extractor, reference_normalizer, verification_report
from .models import VerificationReport


async def verify_document_async(
    text: str,
    pages: int = 0,
    check_urls: bool = False,
    check_claims: bool = False,
    concurrency: int = 4,
    progress: Optional[Callable[[int, int], None]] = None,
) -> VerificationReport:
    raw_refs, intext, stats = reference_extractor.extract(text, pages)
    refs = reference_normalizer.normalize_all(raw_refs)

    async with http_client.make_client() as client:
        verified = await external_verifier.verify_all(
            client, refs, check_urls=check_urls, concurrency=concurrency, progress=progress,
        )
        claims = []
        if check_claims:
            claims = await claim_verifier.verify_claims(client, text)

    consistency = citation_matcher.check_consistency(refs, intext)
    return verification_report.build_report(stats, verified, consistency, claims)


def verify_document(
    text: str,
    pages: int = 0,
    check_urls: bool = False,
    check_claims: bool = False,
    concurrency: int = 4,
    progress: Optional[Callable[[int, int], None]] = None,
) -> VerificationReport:
    """Sync wrapper. Safe to call from Streamlit."""
    coro = verify_document_async(
        text, pages=pages, check_urls=check_urls, check_claims=check_claims,
        concurrency=concurrency, progress=progress,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # A loop is already running (some Streamlit setups) — run in a worker thread.
    result: dict = {}

    def _runner():
        result["report"] = asyncio.run(coro)

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    return result["report"]
