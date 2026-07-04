"""verification/models.py — shared dataclasses for the external verification pipeline.

One typed contract between all stages; no ad-hoc dict shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NormalizedReference:
    """A bibliography entry parsed into structured fields (Stage 2 output)."""
    index: int
    raw_text: str
    authors: list[str] = field(default_factory=list)
    title: Optional[str] = None
    journal: Optional[str] = None
    conference: Optional[str] = None
    publisher: Optional[str] = None
    year: Optional[int] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    arxiv_id: Optional[str] = None
    ref_number: Optional[int] = None          # for numbered styles [1], 1.
    type_guess: str = "article"               # article | book | chapter | conference | report | web | preprint
    extraction_confidence: float = 0.0        # 0..1 — how confidently we parsed the entry


@dataclass
class ExternalRecord:
    """A candidate record returned by an external scholarly source."""
    source: str                                # crossref | openalex | semantic_scholar | pubmed | arxiv
    title: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    publisher: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class MatchResult:
    """Outcome of comparing a NormalizedReference against an ExternalRecord."""
    matched: bool = False
    score: float = 0.0                         # weighted, renormalised similarity 0..1
    record: Optional[ExternalRecord] = None
    field_scores: dict = field(default_factory=dict)
    strategy: Optional[str] = None             # doi | arxiv_id | exact_title | title_author | domain_fallback | fuzzy


@dataclass
class VerifiedReference:
    """Stage 3 output — one reference, fully judged."""
    reference: NormalizedReference
    match: MatchResult = field(default_factory=MatchResult)
    verdict: str = "unverified"                # verified | likely_verified | suspect | fabricated | unverified
    confidence: float = 0.0
    issues: list[str] = field(default_factory=list)
    providers_tried: list[str] = field(default_factory=list)
    recommendation: Optional[str] = None
    doi_resolves: Optional[bool] = None        # None = not checked / inconclusive
    url_alive: Optional[bool] = None


@dataclass
class ConsistencyReport:
    """Stage 4 output — in-text ↔ bibliography consistency."""
    cited_not_listed: list[str] = field(default_factory=list)
    listed_not_cited: list[int] = field(default_factory=list)      # reference indices
    duplicates: list[list[int]] = field(default_factory=list)      # groups of reference indices
    numbering_gaps: list[int] = field(default_factory=list)
    numbering_overshoots: list[int] = field(default_factory=list)  # cited numbers beyond the list
    year_mismatches: list[str] = field(default_factory=list)
    formatting_issues: list[str] = field(default_factory=list)


@dataclass
class ClaimResult:
    """Stage 5 output — one claim-like sentence and the evidence found."""
    sentence: str
    verdict: str = "No Evidence Found"         # Supported | Partially Supported | Contradicted | No Evidence Found
    evidence: list[ExternalRecord] = field(default_factory=list)


@dataclass
class DocumentStats:
    pages: int = 0
    words: int = 0
    figures: int = 0
    tables: int = 0
    reference_count: int = 0
    intext_citation_count: int = 0


@dataclass
class VerificationReport:
    """Stage 6 aggregate — everything the UI / exports consume."""
    stats: DocumentStats = field(default_factory=DocumentStats)
    references: list[VerifiedReference] = field(default_factory=list)
    consistency: ConsistencyReport = field(default_factory=ConsistencyReport)
    claims: list[ClaimResult] = field(default_factory=list)
    reference_quality: float = 0.0             # 0..100
    citation_quality: float = 0.0
    evidence_quality: float = 0.0
    overall_quality: float = 0.0
    recommendations: list[str] = field(default_factory=list)
