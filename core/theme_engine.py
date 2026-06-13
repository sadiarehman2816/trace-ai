"""
TRACE-AI — Step 0b: Theme Discovery Engine

Generates candidate research themes directly from the uploaded document(s),
so the user does not have to supply themes manually.

GOLDEN PRINCIPLE:
  Themes emerge from data.
  Findings emerge from evidence.
  Claims emerge from verified findings.

Approach (offline, deterministic — no model download required):
  1. Collect all chunk text from the index.
  2. Extract candidate key-phrases (noun-ish 1-3 word n-grams) ranked by TF-IDF.
  3. Generate Top-N raw candidate themes.
  4. Remove weak themes (low score / too generic / stopword-only).
  5. Merge near-duplicate themes (high token overlap).
  6. Output a final shortlist (default 4-6 themes).

This module's `discover_themes` is the seam where a Claude-powered theme
discovery (LIVE mode) can be substituted for richer, more natural themes.
"""

import re
from sklearn.feature_extraction.text import TfidfVectorizer

# Domain-agnostic generic words that make poor standalone themes
GENERIC_TERMS = {
    "report", "study", "data", "table", "figure", "section", "page", "chapter",
    "introduction", "conclusion", "summary", "results", "analysis", "method",
    "methods", "findings", "discussion", "appendix", "reference", "references",
    "number", "percent", "percentage", "total", "average", "year", "years",
    "however", "therefore", "overall", "based", "using", "include", "including",
    "various", "different", "several", "many", "also", "well", "within",
    # common tabular/CSV column-header words (so themes aren't polluted by them)
    "interview", "quote", "category", "respondent", "participant", "id",
    "row", "column", "code", "theme", "comment", "response", "answer", "name",
}

# Single broad nouns that are too generic to be a theme on their own (Problem #2).
# Rejected unless they appear as part of a longer, more specific phrase.
BROAD_SINGLE_NOUNS = {
    "households", "household", "people", "respondents", "respondent",
    "individuals", "individual", "residents", "resident", "persons", "person",
    "adults", "children", "families", "family", "group", "groups",
}


def _clean_candidate(phrase: str) -> str:
    """Title-cases a candidate phrase for display."""
    return " ".join(w.capitalize() for w in phrase.split())


def _stem(word: str) -> str:
    """Lightweight stemmer so variants collapse: rented/renters/renter -> rent,
    housing/houses -> hous, buyers/buying -> buy. Crude but effective for the
    'Social Rented / Social Renters' duplicate-theme problem."""
    w = word.lower()
    for suf in (" ers", "ing", "ed", "es", "ers", "er", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    return w


def _token_set(phrase: str) -> set:
    """Return the set of lowercase content tokens (>2 chars) in a phrase."""
    return {w for w in re.findall(r"[a-z]+", phrase.lower()) if len(w) > 2}


def _stem_set(phrase: str) -> set:
    """Token set after stemming — used for duplicate detection."""
    return {_stem(w) for w in re.findall(r"[a-z]+", phrase.lower()) if len(w) > 2}


def _is_weak(phrase: str) -> bool:
    """Weak = empty, all-generic, blacklisted, or single very short token."""
    # Blacklist check (document titles, table labels, structural words)
    try:
        from core.quality_filter import is_blacklisted_theme
        if is_blacklisted_theme(phrase):
            return True
    except Exception:
        pass

    toks = _token_set(phrase)
    if not toks:
        return True
    if toks <= GENERIC_TERMS:
        return True
    if not (toks - GENERIC_TERMS):
        return True
    # Problem #2: reject a theme that is a single broad noun (e.g. "Households",
    # "People") with no qualifier — too generic to be a research theme.
    content_toks = toks - GENERIC_TERMS
    if len(content_toks) == 1 and content_toks <= BROAD_SINGLE_NOUNS:
        return True
    return False


def _merge_duplicates(themes: list[str], overlap_threshold: float = None) -> list[str]:
    """Merge near-duplicate/overlapping themes (stem-aware); keep the most specific."""
    if overlap_threshold is None:
        from config.thresholds import THEME_MERGE_THRESHOLD
        overlap_threshold = THEME_MERGE_THRESHOLD
    """
    Merges near-duplicate / overlapping themes. Two themes merge if their token
    sets overlap (Jaccard >= threshold) OR if one shares its core word with the
    other (e.g. 'Social Renters' / 'Social Rented Sector' / 'Social Rented' all
    collapse to one). The longer/more specific phrase is kept.
    """
    kept = []
    for theme in themes:
        t_tokens = _stem_set(theme)
        merged = False
        for i, existing in enumerate(kept):
            e_tokens = _stem_set(existing)
            if not t_tokens or not e_tokens:
                continue
            inter = t_tokens & e_tokens
            jacc = len(inter) / len(t_tokens | e_tokens)
            non_generic_shared = inter - {_stem(g) for g in GENERIC_TERMS}
            shares_core = (len(inter) >= 2 or t_tokens <= e_tokens
                           or e_tokens <= t_tokens or len(non_generic_shared) >= 1)
            if jacc >= overlap_threshold or shares_core:
                if len(_token_set(theme)) > len(_token_set(existing)):
                    kept[i] = theme
                merged = True
                break
        if not merged:
            kept.append(theme)
    return kept


def discover_themes(index_json: dict,
                    top_n_raw: int = None,
                    final_count: int = None,
                    client=None) -> list[str]:
    """
    Two-stage theme discovery:

      STAGE 1 — Keyword clusters:
        Rank candidate key-phrases (1-3 word n-grams) by TF-IDF across the
        document(s), boosting multi-word phrases (they make better themes).

      STAGE 2 — Theme synthesis:
        Remove weak/generic candidates, drop phrases that are subsets of
        stronger ones, merge near-duplicates, and shortlist the final
        human-readable themes.

    GOLDEN PRINCIPLE: themes emerge from the data.
    `client` is reserved for LIVE-mode Claude synthesis (richer phrasing).
    """
    from config.thresholds import THEME_TOP_N_RAW, THEME_FINAL_COUNT
    if top_n_raw is None:
        top_n_raw = THEME_TOP_N_RAW
    if final_count is None:
        final_count = THEME_FINAL_COUNT

    chunks = index_json.get("chunks", [])
    texts = [c["text"] for c in chunks if c.get("text")]
    if not texts:
        return []

    # ---- STAGE 1: keyword clusters (TF-IDF ranked phrases) ----
    try:
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 3),
            min_df=1,
            max_features=400,
        )
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        return []

    scores = matrix.sum(axis=0).A1
    vocab = vectorizer.get_feature_names_out()

    # Boost multi-word phrases (better themes than lone words)
    boosted = []
    for phrase, score in zip(vocab, scores):
        wc = len(phrase.split())
        weight = 0.6 if wc == 1 else (1.4 if wc == 2 else 1.6)
        boosted.append((phrase, score * weight, wc))
    ranked = sorted(boosted, key=lambda x: x[1], reverse=True)

    # ---- STAGE 2: theme synthesis (filter, dedupe, merge, shortlist) ----
    raw_candidates = []
    seen = set()
    for phrase, _bscore, wc in ranked:
        if _is_weak(phrase):
            continue
        key = frozenset(_token_set(phrase))
        if key in seen:
            continue
        # drop phrases that are subsets of an already-kept (stronger) phrase
        if any(key <= frozenset(_token_set(c)) for c, _w in raw_candidates):
            continue
        seen.add(key)
        raw_candidates.append((_clean_candidate(phrase), wc))
        if len(raw_candidates) >= top_n_raw:
            break

    # Prefer multi-word themes; fall back to single words only if needed
    multi = [c for c, wc in raw_candidates if wc >= 2]
    single = [c for c, wc in raw_candidates if wc == 1]
    ordered = multi + single

    merged = _merge_duplicates(ordered)
    raw_themes = merged[:max(final_count * 2, 10)]  # keep extra for synthesis

    # ---- STAGE 3 (LIVE only): Claude theme synthesis ----
    # In LIVE mode, hand the raw keyword clusters to Claude to synthesise clean,
    # researcher-friendly theme names (e.g. "Housing Affordability" instead of
    # "Demand Exceeds Supply"). Offline, return the cleaned raw themes.
    if client is not None and raw_themes:
        from config.feature_flags import is_enabled
        if is_enabled("llm_theme_synthesis"):
            from models.theme_synthesis import synthesise_themes
            synthesised = synthesise_themes(raw_themes, texts, client, final_count)
            if synthesised:
                return synthesised[:final_count]

    return raw_themes[:final_count]


