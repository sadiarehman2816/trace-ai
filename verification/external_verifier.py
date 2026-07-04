"""verification/external_verifier.py — Stage 3, the core.

Search strategy per reference:
  ① DOI (Crossref → OpenAlex → S2 → PubMed)
  ② arXiv ID
  ③ exact title (Crossref → OpenAlex → S2)
  ④ title + first author (Crossref)
  ⑤ PubMed / arXiv domain fallbacks
  ⑥ fuzzy best-of over all collected candidates

Weighted similarity: title 0.42, authors 0.22, DOI 0.14, year 0.12,
journal 0.07, publisher 0.03 — renormalised over the fields the reference
actually has, so a DOI-less book isn't penalised for a field it never claimed.
A DOI mismatch multiplies the score ×0.75 (strong negative signal).

Field-mismatch issues are only computed for ACCEPTED matches — comparing
against a rejected near-miss produces spurious author_mismatch noise.
Provider search coroutines are built lazily (factories) to avoid un-awaited
coroutine warnings on early accept.
"""

from __future__ import annotations

import asyncio
import re
from difflib import SequenceMatcher
from typing import Awaitable, Callable, Optional

import httpx

from . import (
    arxiv_client,
    crossref_client,
    doi_validator,
    openalex_client,
    pubmed_client,
    semantic_scholar_client,
)
from .models import ExternalRecord, MatchResult, NormalizedReference, VerifiedReference

# --- Similarity weights (renormalised over present fields) ------------------
WEIGHTS = {
    "title": 0.42,
    "authors": 0.22,
    "doi": 0.14,
    "year": 0.12,
    "journal": 0.07,
    "publisher": 0.03,
}
DOI_MISMATCH_PENALTY = 0.75

ACCEPT_THRESHOLD = 0.72          # a match at/above this is accepted
VERIFIED_THRESHOLD = 0.88
LIKELY_THRESHOLD = 0.72
SUSPECT_THRESHOLD = 0.45

_MEDICAL_HINTS = re.compile(
    r"\b(patient|clinical|health|medical|disease|therapy|treatment|nursing|care home|epidemiolog)\w*",
    re.IGNORECASE,
)
_CS_HINTS = re.compile(
    r"\b(neural|machine learning|deep learning|algorithm|artificial intelligence|computer|arxiv)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Field similarity
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _title_sim(a: Optional[str], b: Optional[str]) -> Optional[float]:
    if not a or not b:
        return None
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return None
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _surname(name: str) -> str:
    name = name.strip()
    if "," in name:
        return _norm(name.split(",")[0])
    parts = name.split()
    return _norm(parts[-1]) if parts else ""


def _authors_sim(a: list[str], b: list[str]) -> Optional[float]:
    if not a or not b:
        return None
    sa = {s for s in (_surname(x) for x in a) if s}
    sb = {s for s in (_surname(x) for x in b) if s}
    if not sa or not sb:
        return None
    overlap = len(sa & sb)
    return overlap / max(1, min(len(sa), len(sb)))


def _year_sim(a: Optional[int], b: Optional[int]) -> Optional[float]:
    if a is None or b is None:
        return None
    diff = abs(a - b)
    if diff == 0:
        return 1.0
    if diff == 1:                 # online-first vs print year
        return 0.7
    return 0.0


def _container_sim(a: Optional[str], b: Optional[str]) -> Optional[float]:
    if not a or not b:
        return None
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return None
    if na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def score_match(ref: NormalizedReference, rec: ExternalRecord) -> MatchResult:
    """Weighted similarity, renormalised over the fields the reference has."""
    field_scores: dict[str, float] = {}
    total_weight = 0.0
    weighted = 0.0
    doi_mismatch = False

    checks: list[tuple[str, Optional[float]]] = [
        ("title", _title_sim(ref.title, rec.title)),
        ("authors", _authors_sim(ref.authors, rec.authors)),
        ("year", _year_sim(ref.year, rec.year)),
        ("journal", _container_sim(ref.journal or ref.conference, rec.journal)),
        ("publisher", _container_sim(ref.publisher, rec.publisher)),
    ]

    if ref.doi:
        if rec.doi:
            same = _norm(ref.doi) == _norm(rec.doi)
            checks.append(("doi", 1.0 if same else 0.0))
            if not same:
                doi_mismatch = True
        # record has no DOI → field not comparable, skip (no penalty)

    for name, sim in checks:
        if sim is None:
            continue
        w = WEIGHTS[name]
        total_weight += w
        weighted += w * sim
        field_scores[name] = round(sim, 3)

    score = (weighted / total_weight) if total_weight > 0 else 0.0
    if doi_mismatch:
        score *= DOI_MISMATCH_PENALTY

    return MatchResult(
        matched=score >= ACCEPT_THRESHOLD,
        score=round(score, 3),
        record=rec,
        field_scores=field_scores,
    )


# ---------------------------------------------------------------------------
# Issue detection (accepted matches only) + verdicts
# ---------------------------------------------------------------------------

def detect_issues(ref: NormalizedReference, vr: VerifiedReference) -> list[str]:
    issues: list[str] = []

    if not ref.title and not ref.authors:
        issues.append("incomplete_reference")
    elif not ref.title or not ref.year:
        issues.append("incomplete_reference")

    if ref.doi and not doi_validator.is_valid_syntax(ref.doi):
        issues.append("invalid_doi_syntax")
    if vr.doi_resolves is False:
        issues.append("doi_does_not_resolve")
    if vr.url_alive is False:
        issues.append("broken_url")

    m = vr.match
    if m.matched and m.record:
        fs = m.field_scores
        if "doi" in fs and fs["doi"] == 0.0:
            issues.append("doi_mismatch")
        if "year" in fs and fs["year"] == 0.0:
            issues.append("wrong_year")
        if "authors" in fs and fs["authors"] < 0.5:
            issues.append("author_mismatch")
        if ref.type_guess == "article" and not ref.journal:
            issues.append("missing_journal")
    return issues


def decide_verdict(vr: VerifiedReference, providers_reachable: bool) -> tuple[str, float]:
    """Verdicts (research-integrity safe terminology):
      verified               — strong external match
      likely_verified        — high-confidence match, minor differences
      ambiguous_match        — a match exists but confidence is insufficient,
                               or several plausible matches exist
      not_externally_verified— no acceptable record found in the searched
                               sources (NOT a claim the reference is fake)
      not_checked            — skipped, providers unavailable, or timed out
    """
    m = vr.match
    score = m.score if m.record else 0.0

    if m.matched and score >= VERIFIED_THRESHOLD and "doi_mismatch" not in vr.issues:
        return "verified", score
    if m.matched and score >= LIKELY_THRESHOLD:
        return "likely_verified", score
    if score >= SUSPECT_THRESHOLD:
        return "ambiguous_match", score

    if not providers_reachable:
        return "not_checked", score
    # Grey literature / books routinely absent from scholarly indexes — do not
    # escalate their absence.
    if vr.reference.type_guess in ("web", "report") and not vr.reference.doi:
        return "not_checked", score
    return "not_externally_verified", score


def recommendation_for(vr: VerifiedReference) -> str:
    v = vr.verdict
    if v == "verified":
        return "No action needed."
    if v == "likely_verified":
        return "Match found with minor differences — confirm the flagged fields."
    if v == "ambiguous_match":
        return ("A possible external match was found, but the metadata does not match "
                "with sufficient confidence. Manual review recommended.")
    if v == "not_externally_verified":
        return ("No acceptable external record was found in the searched sources. "
                "Manual verification is recommended. Many books and grey-literature "
                "items are simply not indexed, so absence here does not by itself "
                "indicate a problem with the reference.")
    return ("Verification was not completed for this reference (source type, provider "
            "availability, or timeout). Check manually.")


# ---------------------------------------------------------------------------
# Search strategy
# ---------------------------------------------------------------------------

SearchFactory = Callable[[], Awaitable]


async def _first_accept(
    ref: NormalizedReference,
    factories: list[tuple[str, str, SearchFactory]],
    candidates: list[MatchResult],
    providers_tried: list[str],
    responded: list[bool],
) -> Optional[MatchResult]:
    """Run factories in order; return first accepted match. Factories are
    built lazily so an early accept leaves no un-awaited coroutines.

    Reachability: a provider that returns a LIST (even empty) or a record
    responded — 'searched, found nothing' is evidence, unlike a None failure."""
    for strategy, provider, factory in factories:
        providers_tried.append(provider)
        try:
            result = await factory()
        except Exception:
            result = None
        if isinstance(result, list) or result is not None:
            responded.append(True)
        records = result if isinstance(result, list) else ([result] if result else [])
        for rec in records:
            m = score_match(ref, rec)
            m.strategy = strategy
            candidates.append(m)
            if m.matched:
                return m
    return None


async def verify_reference(
    client: httpx.AsyncClient,
    ref: NormalizedReference,
    check_urls: bool = False,
) -> VerifiedReference:
    vr = VerifiedReference(reference=ref)
    candidates: list[MatchResult] = []
    responded: list[bool] = []
    tried = vr.providers_tried

    # ① DOI lookups
    if ref.doi:
        m = await _first_accept(ref, [
            ("doi", "crossref", lambda: crossref_client.lookup_doi(client, ref.doi)),
            ("doi", "openalex", lambda: openalex_client.lookup_doi(client, ref.doi)),
            ("doi", "semantic_scholar", lambda: semantic_scholar_client.lookup_doi(client, ref.doi)),
            ("doi", "pubmed", lambda: pubmed_client.lookup_doi(client, ref.doi)),
        ], candidates, tried, responded)
        if m:
            vr.match = m
        vr.doi_resolves = await doi_validator.resolves(client, ref.doi)

    # ② arXiv ID
    if not vr.match.matched and ref.arxiv_id:
        m = await _first_accept(ref, [
            ("arxiv_id", "arxiv", lambda: arxiv_client.lookup_id(client, ref.arxiv_id)),
        ], candidates, tried, responded)
        if m:
            vr.match = m

    # ③ exact title
    if not vr.match.matched and ref.title:
        m = await _first_accept(ref, [
            ("exact_title", "crossref", lambda: crossref_client.search_bibliographic(client, ref.title)),
            ("exact_title", "openalex", lambda: openalex_client.search_title(client, ref.title)),
            ("exact_title", "semantic_scholar", lambda: semantic_scholar_client.search_title(client, ref.title)),
        ], candidates, tried, responded)
        if m:
            vr.match = m

    # ④ title + first author
    if not vr.match.matched and ref.title and ref.authors:
        first_author = _surname(ref.authors[0])
        m = await _first_accept(ref, [
            ("title_author", "crossref",
             lambda: crossref_client.search_title_author(client, ref.title, first_author)),
        ], candidates, tried, responded)
        if m:
            vr.match = m

    # ⑤ domain fallbacks
    if not vr.match.matched and ref.title:
        blob = ref.raw_text
        factories: list[tuple[str, str, SearchFactory]] = []
        if _MEDICAL_HINTS.search(blob):
            factories.append(("domain_fallback", "pubmed",
                              lambda: pubmed_client.search(client, ref.title)))
        if _CS_HINTS.search(blob):
            factories.append(("domain_fallback", "arxiv",
                              lambda: arxiv_client.search_title(client, ref.title)))
        if factories:
            m = await _first_accept(ref, factories, candidates, tried, responded)
            if m:
                vr.match = m

    # ⑥ fuzzy best-of over everything collected
    if not vr.match.matched and candidates:
        best = max(candidates, key=lambda c: c.score)
        if best.strategy is None:
            best.strategy = "fuzzy"
        vr.match = best

    # Optional plain-URL liveness
    if check_urls and ref.url:
        vr.url_alive = await doi_validator.url_alive(client, ref.url)

    providers_reachable = bool(responded) or bool(vr.match.record) or vr.doi_resolves is not None
    vr.issues = detect_issues(ref, vr)
    vr.verdict, vr.confidence = decide_verdict(vr, providers_reachable)
    vr.recommendation = recommendation_for(vr)
    return vr


async def verify_all(
    client: httpx.AsyncClient,
    refs: list[NormalizedReference],
    check_urls: bool = False,
    concurrency: int = 4,
    progress: Optional[Callable[[int, int], None]] = None,
) -> list[VerifiedReference]:
    sem = asyncio.Semaphore(concurrency)
    done = 0
    results: list[Optional[VerifiedReference]] = [None] * len(refs)

    async def worker(i: int, ref: NormalizedReference):
        nonlocal done
        async with sem:
            results[i] = await verify_reference(client, ref, check_urls=check_urls)
        done += 1
        if progress:
            try:
                progress(done, len(refs))
            except Exception:
                pass

    await asyncio.gather(*(worker(i, r) for i, r in enumerate(refs)))
    return [r for r in results if r is not None]
