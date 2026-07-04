"""verification/claim_verifier.py — Stage 5 (optional, off by default).

Extracts claim-like sentences (stats/findings language), searches
OpenAlex + Semantic Scholar by keywords, and returns conservative verdicts —
metadata search proves relevant literature EXISTS, not that it agrees, so the
human decides. Consistent with TRACE-AI's rule-engine-decides principle.
"""

from __future__ import annotations

import re

import httpx

from . import openalex_client, semantic_scholar_client
from .models import ClaimResult

_CLAIM_HINTS = re.compile(
    r"\b(significant(ly)?|increase[ds]?|decrease[ds]?|reduc(es|ed|tion)|correlat\w+|"
    r"associat\w+|evidence|found that|show(s|ed|n)? that|demonstrat\w+|"
    r"\d{1,3}(\.\d+)?\s*%|p\s*[<=>]\s*0?\.\d+)\b",
    re.IGNORECASE,
)
_STOPWORDS = frozenset(
    "the a an and or of to in on for with that this these those is are was were be been "
    "has have had it its as by from at we our their there which who whom not no than "
    "found show shown showed that significantly significant evidence".split()
)


def extract_claims(body_text: str, max_claims: int = 10) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", body_text)
    claims = []
    for s in sentences:
        s = s.strip()
        if 60 <= len(s) <= 400 and _CLAIM_HINTS.search(s):
            claims.append(re.sub(r"\s+", " ", s))
        if len(claims) >= max_claims:
            break
    return claims


def _keywords(sentence: str, n: int = 8) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", sentence)
    picked = []
    for w in words:
        lw = w.lower()
        if lw in _STOPWORDS or lw in picked:
            continue
        picked.append(lw)
        if len(picked) >= n:
            break
    return " ".join(picked)


async def verify_claim(client: httpx.AsyncClient, sentence: str) -> ClaimResult:
    query = _keywords(sentence)
    result = ClaimResult(sentence=sentence)
    if not query:
        return result
    try:
        oa = await openalex_client.search_title(client, query, rows=3)
    except Exception:
        oa = []
    try:
        s2 = await semantic_scholar_client.search_title(client, query, rows=3)
    except Exception:
        s2 = []
    evidence = (oa or []) + (s2 or [])
    result.evidence = evidence[:5]
    if len(evidence) >= 3:
        result.verdict = "Partially Supported"   # literature exists; agreement not established
    elif evidence:
        result.verdict = "Partially Supported"
    else:
        result.verdict = "No Evidence Found"
    return result


async def verify_claims(client: httpx.AsyncClient, body_text: str, max_claims: int = 10) -> list[ClaimResult]:
    out = []
    for sentence in extract_claims(body_text, max_claims):
        out.append(await verify_claim(client, sentence))
    return out
