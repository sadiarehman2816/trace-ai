"""
TRACE-AI — Evidence Quality Filter & Blacklist

Two jobs:
  1. Reject low-value 'metadata' spans (annex/table/figure/footnote references)
     before they become evidence — these carry no analytical value.
  2. Provide a blacklist of noise phrases that should never appear as themes
     (document titles, table labels, generic structural words).

Also classifies an evidence span by type (statistical / quote / policy /
trend / limitation) for the Evidence Type Labels feature.
"""

import re

# Phrases that mark a span as metadata, not a finding. If a span is *dominated*
# by these (i.e. it's basically a pointer to a table/figure/source), reject it.
METADATA_MARKERS = (
    "see annex", "see table", "see figure", "annex table", "annex tables",
    "underlying data", "data are presented", "presented in annex",
    "base:", "bases:", "note:", "notes:", "source:", "sources:",
    "figure ", "table ", "fig.", "chart ",
)

# Phrases/words that should never be surfaced as a theme.
THEME_BLACKLIST = {
    "annex", "annex table", "table", "tables", "figure", "figures", "chart",
    "base", "bases", "note", "notes", "source", "sources",
    "english housing survey", "headline report", "report", "survey",
    "chapter", "section", "appendix", "document", "documents",
    "data", "dataset", "statistics", "respondent", "respondents",
    "underlying data", "underlying data presented", "acknowledgements",
    "contents", "references", "bibliography", "introduction", "methodology",
    "glossary", "foreword", "summary",
}

# Substrings that disqualify a theme outright (Problem A): if any appears
# anywhere in a candidate theme, it's a structural/reference artefact, not a
# research theme.
THEME_REJECT_SUBSTRINGS = (
    "underlying data", "annex", "appendix", "acknowledgement", "contents",
    "references", "bibliography", "table", "figure", "presented",
)


def is_low_quality_span(text: str) -> bool:
    """
    Minimum sentence-quality rule. Rejects spans that can't carry analytical
    value as standalone evidence:
      - fewer than 8 words
      - numeric/label fragments (e.g. "14 private renters.")
      - no verb (incomplete sentence / sentence fragment)
    Returns True if the span should be REJECTED.
    """
    if not text:
        return True
    t = text.strip()
    words = re.findall(r"[A-Za-z0-9%]+", t)

    # Too short to be a finding (threshold from config)
    from config.thresholds import MIN_SPAN_WORDS
    if len(words) < MIN_SPAN_WORDS:
        return True

    # Mostly a number + a short noun phrase ("14 private renters.")
    if re.match(r"^[\d,\.]+\s+\w+(\s+\w+){0,3}\.?$", t):
        return True

    # Must contain at least one verb-like token to be a complete statement.
    # A whitelist of verbs is fragile (always misses some, e.g. "worsened",
    # "varies"), so we detect verbs structurally: common auxiliaries/irregulars,
    # OR any word with a typical verb inflection (-ed, -es, - s, -ing) that isn't
    # an obvious plural noun. This generalises to unseen verbs.
    lower = t.lower()
    aux_irregular = (r"\b(is|are|was|were|be|been|being|has|have|had|do|does|did|"
                     r"rose|fell|grew|grown|made|found|saw|seen|ran|run|"
                     r"will|would|can|could|may|might|must|should|shall)\b")
    if re.search(aux_irregular, lower):
        pass  # has a verb
    elif re.search(r"\b\w+(?:ed|ing)\b", lower):
        pass  # inflected verb form present
    elif re.search(r"\b\w{3,}(?:es|s)\b", lower) and re.search(
            r"\b(rise|rises|fall|falls|increase|increases|decrease|decreases|"
            r"vary|varies|differ|differs|account|accounts|report|reports|"
            r"remain|remains|include|includes|exceed|exceeds|face|faces|"
            r"show|shows|need|needs|live|lives|worsen|worsens|improve|improves)\b", lower):
        pass  # present-tense verb present
    else:
        return True  # no verb-like token -> sentence fragment

    return False


def truncate_at_metadata_marker(text: str) -> str:
    """
    HARD truncation: cut the text at the FIRST occurrence of any metadata marker
    (Figure, Table, Annex, Appendix, Source:, Note:). Everything from the marker
    onward is discarded. This is the simplest, most aggressive guarantee that no
    metadata reference can survive — used as the first step of cleaning.

    Example:
      "...social rented sector, Figure 1.9 and Annex Table 1.6."
      -> "...social rented sector,"   (then punctuation is tidied later)
    """
    if not text:
        return text

    # First metadata marker as a whole word (case-insensitive).
    marker = re.search(
        r"\b(?:see\s+)?(?:annex|appendix|figure|fig\.?|table|chart)\b"
        r"|\b(?:source|notes?|bases?)\s*:",
        text,
        flags=re.IGNORECASE,
    )
    if marker:
        before = text[: marker.start()]
        after = text[marker.start():]
        # Only hard-truncate if BEFORE the marker there is already a substantive
        # clause (>=4 words). This handles the common "valid sentence, Figure X"
        # case. If there's little before the marker (e.g. "As shown in Appendix
        # B, real content..."), don't truncate — let strip_metadata_references
        # remove just the reference and keep the real content.
        before_words = re.findall(r"[A-Za-z0-9%]+", before)
        if len(before_words) >= 4:
            text = before
        # else: leave text unchanged; gentler stripping runs next.

    # Tidy trailing connectors/punctuation left dangling ("..., and", "...,")
    text = re.sub(r"[\s,;:.\-]*(?:\band\b|\bor\b)?\s*$", "", text).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def clean_evidence_text(text: str) -> str:
    """
    Full evidence-hygiene cleaner (audit Steps 1-3). Operates sentence-by-sentence:
      1. Split the span into individual sentences.
      2. Drop any sentence that is dominated by a metadata reference.
      3. Within a kept sentence, truncate/remove the metadata clause.
    Returns the cleaned, joined prose (may be empty if nothing survives).
    """
    if not text:
        return ""

    # Split into sentences (simple, robust)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = []
    for sent in sentences:
        s = sent.strip()
        if not s:
            continue
        # Drop sentences that are essentially a Source:/Note:/Base: line
        if re.match(r"^(source|notes?|bases?)\s*:", s, flags=re.IGNORECASE):
            continue
        # STEP A — hard truncate at the first metadata marker (most aggressive
        # guarantee). Then STEP B — strip any residual inline references.
        s = truncate_at_metadata_marker(s)
        cleaned = strip_metadata_references(s)
        # Remove any leading punctuation/whitespace left after stripping a
        # lead-in clause (e.g. "As shown in Appendix B, X" -> ", X" -> "X")
        cleaned = re.sub(r"^[\s,;:.\-]+", "", cleaned).strip()
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
        # If the sentence was ONLY a metadata reference, it's now empty -> drop
        if not cleaned or len(re.sub(r"[^a-z0-9]", "", cleaned.lower())) < 3:
            continue
        # If a metadata reference still survives, drop this sentence (safety)
        if contains_metadata_reference(cleaned):
            continue
        kept.append(cleaned)

    return " ".join(kept).strip()


def strip_metadata_references(text: str) -> str:
    """
    Removes inline metadata references (Figure 1.9, Annex Table 1.6, see Table 4,
    Appendix B, etc.) from an otherwise valid sentence, instead of rejecting the
    whole sentence. This stops 'fake authority' noise from leaking into evidence
    while keeping the real analytical content.

    Example:
      "...1% in the social rented sector, Figure 1.9 and Annex Table 1.6."
      -> "...1% in the social rented sector."
    """
    if not text:
        return text

    cleaned = text

    # Numbered OR lettered structural references, with optional leading "see".
    # Matches "Figure 1.9", "Annex Table 1.6", "Appendix B", "Annex A".
    ref = (r"(?:see\s+)?(?:annex\s+tables?|annexe?s?|appendix|appendices|figures?|fig\.?|tables?|charts?)"
           r"\s*(?:\d+(?:\.\d+)*[a-z]?|[A-Z]\b)")

    # 0) Remove "Source: ...", "Note: ...", "Notes: ..." trailing clauses
    cleaned = re.sub(r"[,;.]?\s*(?:source|notes?|bases?)\s*:\s*.*$", ".", cleaned,
                     flags=re.IGNORECASE)

    # 1) Remove whole parentheticals that are just a reference: "(see Table 4.2)"
    cleaned = re.sub(r"\(\s*" + ref + r"\s*\)", "", cleaned, flags=re.IGNORECASE)

    # 2) Remove trailing lead-in phrases: "as shown in Figure 3", "as set out in Table 4"
    cleaned = re.sub(r",?\s*as (?:shown|set out|presented|illustrated|reported) in\s+" + ref,
                     "", cleaned, flags=re.IGNORECASE)

    # 3) Remove "<connector> <ref>" trailing/embedded groups (handles
    #    "Figure 1.9 and Annex Table 1.6" chains)
    cleaned = re.sub(r"[,;(]?\s*(?:and\s+|,\s*)?" + ref + r"\s*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:and|,)\s+" + ref, "", cleaned, flags=re.IGNORECASE)

    # 4) Clean up leftovers: empty parens, stray brackets
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s*[()]\s*", " ", cleaned)

    # Tidy whitespace and dangling punctuation
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([.,;])", r"\1", cleaned)
    cleaned = re.sub(r"[,;]\s*\.", ".", cleaned)
    cleaned = re.sub(r"\s*[,;]\s*$", "", cleaned).strip()
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def contains_metadata_reference(text: str) -> bool:
    """
    Post-filter safety net (Step 3). Returns True if a span STILL contains a
    numbered structural reference (Figure 1.9, Annex Table 1.6, Appendix B,
    Page 14, etc.) after stripping — such a span should be rejected outright.
    This is the last line of defence so no 'fake authority' noise reaches
    scoring, confidence, or theme synthesis.
    """
    if not text:
        return False
    # Use original case so "Appendix B" (capital letter ref) is detectable,
    # but match case-insensitively for the keyword part.
    ref = (r"(?i)\b(?:see\s+)?(?:annex\s+tables?|annexe?s?|appendix|appendices|figures?|fig\.?|tables?|charts?|page)"
           r"\s*(?:\d+(?:\.\d+)*[a-z]?|[A-Z]\b)")
    if re.search(ref, text):
        return True
    # Trailing structural labels
    if re.search(r"\b(?:source|notes?|bases?)\s*:", text, flags=re.IGNORECASE):
        return True
    return False


def is_metadata_span(text: str) -> bool:
    """
    Returns True if a span is essentially a metadata/structural pointer rather
    than a substantive finding (so it should be rejected as evidence).
    """
    if not text:
        return True
    t = text.lower().strip()

    # Starts with a structural label -> metadata
    if re.match(r"^(base|bases|note|notes|source|sources)\s*[:.]", t):
        return True

    # Contains a numbered table/figure/annex reference like "annex table 1.6",
    # "figure 1.9", "table 4.2" — strong metadata signal.
    if re.search(r"\b(annex\s+table|annex|figure|table|chart|fig\.?)\s*\d", t):
        # Allow it only if it's a long analytical sentence that merely cites
        # a table in passing; reject short pointer-only spans.
        if len(t.split()) <= 16:
            return True

    # Dominated by annex/table/figure references and little else
    marker_hits = sum(1 for m in METADATA_MARKERS if m in t)
    if marker_hits >= 1 and len(t.split()) <= 14:
        has_analytical = bool(re.search(r"\b(increase|decrease|rose|fell|grew|"
                                        r"declined|higher|lower|proportion|"
                                        r"percent|%|million|estimated|compared)\b", t))
        if not has_analytical:
            return True

    return False


def is_chart_or_ocr_noise(text: str) -> bool:
    """
    Problem B: detects chart-axis text and OCR noise that isn't a real sentence.
    Rejects if:
      - more than 40% of tokens are numbers/percentages
      - it's a run of numbers (chart axis like "0 10 20 30 40 50")
      - the same percentage/number repeats several times
      - no finite verb is present in a number-heavy string
    """
    if not text:
        return True
    tokens = text.split()
    if not tokens:
        return True

    # Count numeric-ish tokens (123, 12%, 1.5, 40)
    numeric = [tok for tok in tokens if re.fullmatch(r"[£$]?\d+(?:[.,]\d+)?%?", tok)]
    numeric_ratio = len(numeric) / len(tokens)

    # Rule 1: >40% numeric tokens -> chart/table noise
    if numeric_ratio > 0.40:
        return True

    # Rule 2: a run of >=4 consecutive numbers (axis ticks: "0 10 20 30 40 50")
    consec = 0
    for tok in tokens:
        if re.fullmatch(r"\d+%?", tok):
            consec += 1
            if consec >= 4:
                return True
        else:
            consec = 0

    # Rule 3: same number/percentage repeated >=3 times
    if numeric:
        from collections import Counter
        most = Counter(numeric).most_common(1)[0][1]
        if most >= 3:
            return True

    # Rule 4: number-heavy (>25%) AND no finite verb -> not a sentence
    if numeric_ratio > 0.25 and is_low_quality_span(text):
        return True

    return False


def is_blacklisted_theme(theme: str) -> bool:
    """Returns True if a candidate theme is a blacklisted noise phrase."""
    if not theme:
        return True
    t = theme.lower().strip()
    if t in THEME_BLACKLIST:
        return True
    # Problem A: reject if any disqualifying substring appears anywhere
    # (e.g. "Underlying Data Presented", "Annex Table", "References").
    for bad in THEME_REJECT_SUBSTRINGS:
        if bad in t:
            return True
    # Any token-set that is entirely blacklist words
    tokens = set(re.findall(r"[a-z]+", t))
    blacklist_tokens = set()
    for phrase in THEME_BLACKLIST:
        blacklist_tokens |= set(phrase.split())
    if tokens and tokens <= blacklist_tokens:
        return True
    # Contains a hard structural word as the head
    if re.search(r"\b(annex|figure|table|appendix)\b", t):
        return True
    # Starts with a structural/metadata word
    if re.match(r"^(base|bases|note|notes|source|sources|figure|table)\b", t):
        return True
    return False


# ---------------------------------------------------------------------------
# Evidence Type Labels
# ---------------------------------------------------------------------------
def classify_evidence_type(text: str, source_document: str = "") -> dict:
    """
    Classifies an evidence span into a human-friendly type with an icon.
      Statistical finding / Interview quote / Policy statement / Trend / Limitation
    """
    t = (text or "").lower()

    # Limitation / caveat language
    if re.search(r"\b(limitation|caveat|caution|should not be|cannot be|"
                 r"not statistically significant|small sample|may not)\b", t):
        return {"label": "Limitation", "emoji": "⚠️"}

    # Definition / descriptive framing (not a finding)
    if re.search(r"\b(is defined as|are defined as|defined as|refers to|"
                 r"is the|are those|as with chapter|this chapter|this section|"
                 r"in this report|means that|is a measure of|describes|"
                 r"is a means-tested|is a type of|is a form of|is a benefit|"
                 r"is a scheme|is a category|is an? \w+ (?:benefit|payment|"
                 r"scheme|allowance|measure|indicator|status|tenure)|"
                 r"includes (?:households|people|those|anyone|all)|"
                 r"comprises|consists of|encompasses|is categorised|"
                 r"are categorised|is classified|are classified)\b", t):
        return {"label": "Definition", "emoji": "📜"}

    # Trend language
    if re.search(r"\b(increase|increased|decrease|decreased|rose|fell|grew|"
                 r"declined|trend|over time|year on year|compared to|"
                 r"since \d{4})\b", t):
        # If it also has hard numbers, it's a statistical trend
        if re.search(r"\d|\bpercent\b|%|\bmillion\b|\bthousand\b", t):
            return {"label": "Statistical trend", "emoji": "📈"}
        return {"label": "Trend", "emoji": "📈"}

    # Statistical finding (numbers/percentages)
    if re.search(r"\d+(\.\d+)?\s*(%|percent)|\b\d{3,}\b|\bmillion\b|\bbillion\b", t):
        return {"label": "Statistical finding", "emoji": "📊"}

    # Interview quote — tabular/qualitative source, or quoted speech
    if source_document.lower().endswith((".csv", ".xlsx", ".xls")) or '"' in (text or ""):
        return {"label": "Interview quote", "emoji": "🗣️"}

    # Policy statement
    if re.search(r"\b(policy|government|legislation|standard|regulation|"
                 r"strategy|scheme|act|reform|must|should|requirement)\b", t):
        return {"label": "Policy statement", "emoji": "📄"}

    # Default
    return {"label": "General statement", "emoji": "📝"}
