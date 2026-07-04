"""verification/citation_matcher.py — Stage 4.

In-text ↔ bibliography consistency: cited-not-listed, listed-not-cited,
duplicates (fuzzy-title groups ≥0.92), numbering gaps / overshoots,
author-year mismatches ("Smith cited for 2020 but bibliography only has
2018"), formatting issues. Handles year suffixes (2023b) and mixed styles.

Operates on NORMALIZED references and is cleanly separated from external
verification.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import ConsistencyReport, NormalizedReference

_DUPLICATE_TITLE_THRESHOLD = 0.92


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _surname(name: str) -> str:
    name = name.strip()
    if "," in name:
        return _norm(name.split(",")[0])
    parts = name.split()
    return _norm(parts[-1]) if parts else ""


def _base_year(year_str: str) -> str:
    return re.sub(r"[a-z]$", "", year_str.strip())


# Words that carry no distinguishing power in an organisational name.
_ORG_STOPWORDS = frozenset(
    "the of for and a an department ministry office bureau agency commission "
    "committee council institute institution association society organization "
    "organisation national international federal state government".split()
)


def _is_org_author(author: str) -> bool:
    """A personal author looks like 'Surname, F.' / 'Surname, First'. Anything
    else with multiple capitalised words and no leading 'Surname,' is treated
    as organisational (e.g. 'Department for Work and Pensions')."""
    a = author.strip()
    if re.match(r"^[A-ZÀ-Ö][\w'’\-]+,\s*[A-Z]", a):     # "Surname, F." / "Surname, First"
        return False
    # Multi-word capitalised phrase → organisational.
    return len(a.split()) >= 2


def _significant_tokens(norm_name: str) -> set[str]:
    """Distinctive lowercase tokens of an organisation name (stopwords dropped)."""
    return {t for t in norm_name.split() if t and t not in _ORG_STOPWORDS}


def check_consistency(
    refs: list[NormalizedReference],
    intext: list[dict],
) -> ConsistencyReport:
    report = ConsistencyReport()

    # Index references by FIRST-author surname -> set of (base) years present.
    # Organisational authors (e.g. "Department for Work and Pensions") have no
    # surname, so index them separately by their full normalised name and by
    # their significant tokens, and match in-text citations by token overlap.
    ref_surnames_years: dict[str, set[str]] = {}
    org_refs: list[tuple[str, set[str], object]] = []   # (norm_name, tokens, ref)
    for ref in refs:
        if not (ref.authors and ref.year):
            continue
        first = ref.authors[0]
        if _is_org_author(first):
            name = _norm(first)
            org_refs.append((name, _significant_tokens(name), ref))
        else:
            s = _surname(first)
            if s:
                ref_surnames_years.setdefault(s, set()).add(str(ref.year))

    cited_ref_indices: set[int] = set()
    cited_numbers: set[int] = set()

    for cite in intext:
        if cite.get("style") == "numbered":
            cited_numbers.add(cite["number"])
            continue

        # 'lead' is the first-author surname from the extractor; re-normalise it
        # the same way reference surnames are normalised (strip accents/hyphens)
        # so both sides compare identically.
        lead = _norm(cite.get("lead") or "")
        if not lead:
            lead = _surname(re.split(r"\s+(?:and|&|et)\s+", cite.get("author", ""))[0])
        year = _base_year(cite.get("year", ""))
        if not lead:
            continue

        # Personal-author match first.
        if lead in ref_surnames_years:
            years = ref_surnames_years[lead]
            if year and year not in years:
                report.year_mismatches.append(
                    f"{cite.get('author', lead)} cited for {cite.get('year')} "
                    f"but bibliography only has {', '.join(sorted(years))}"
                )
            for ref in refs:
                if ref.authors and not _is_org_author(ref.authors[0]) \
                        and _surname(ref.authors[0]) == lead and (not year or str(ref.year) == year):
                    cited_ref_indices.add(ref.index)
            continue

        # Organisational-author match: the citation phrase (possibly truncated,
        # e.g. "Work and Pensions" for "Department for Work and Pensions") shares
        # its significant tokens with, or is a substring of, an org reference.
        cite_phrase = _norm(cite.get("author") or lead)
        cite_tokens = _significant_tokens(cite_phrase)
        matching_org_refs = []
        for name, tokens, ref in org_refs:
            if not cite_tokens:
                break
            overlap = cite_tokens & tokens
            if (cite_phrase and cite_phrase in name) or (len(overlap) >= 2 and overlap == cite_tokens):
                matching_org_refs.append(ref)

        if matching_org_refs:
            org_years = {str(r.year) for r in matching_org_refs}
            if year and year not in org_years:
                report.year_mismatches.append(
                    f"{cite.get('author', lead)} cited for {cite.get('year')} "
                    f"but bibliography only has {', '.join(sorted(org_years))}"
                )
            for ref in matching_org_refs:
                if not year or str(ref.year) == year:
                    cited_ref_indices.add(ref.index)
            continue

        report.cited_not_listed.append(f"{cite.get('author', lead)} ({cite.get('year')})")

    # Numbered style handling
    numbered_refs = {r.ref_number: r for r in refs if r.ref_number is not None}
    if numbered_refs:
        max_listed = max(numbered_refs)
        listed_numbers = set(numbered_refs)
        for n in cited_numbers:
            if n > max_listed:
                report.numbering_overshoots.append(n)
            elif n not in listed_numbers:
                report.numbering_gaps.append(n)
            else:
                cited_ref_indices.add(numbered_refs[n].index)
        # Gaps in the list itself
        for n in range(1, max_listed + 1):
            if n not in listed_numbers and n not in report.numbering_gaps:
                report.numbering_gaps.append(n)
        report.numbering_gaps.sort()
        report.numbering_overshoots.sort()

    # Listed but never cited. Report the number the user sees in the
    # bibliography (ref_number for numbered styles, else positional index).
    if intext:                                   # only meaningful if we found in-text citations at all
        for ref in refs:
            if ref.index not in cited_ref_indices:
                report.listed_not_cited.append(ref.ref_number or ref.index)

    # Duplicates by fuzzy title
    titled = [(r.index, _norm(r.title)) for r in refs if r.title]
    used: set[int] = set()
    for i, (idx_a, ta) in enumerate(titled):
        if idx_a in used or not ta:
            continue
        group = [idx_a]
        for idx_b, tb in titled[i + 1:]:
            if idx_b in used or not tb:
                continue
            if ta == tb or SequenceMatcher(None, ta, tb).ratio() >= _DUPLICATE_TITLE_THRESHOLD:
                group.append(idx_b)
                used.add(idx_b)
        if len(group) > 1:
            used.update(group)
            report.duplicates.append(sorted(group))

    # Formatting issues
    styles = {c.get("style") for c in intext}
    if len(styles) > 1:
        report.formatting_issues.append("Mixed citation styles (author-year AND numbered) used in the same document.")
    numbered_count = sum(1 for r in refs if r.ref_number is not None)
    if 0 < numbered_count < len(refs):
        report.formatting_issues.append("Reference list mixes numbered and unnumbered entries.")

    return report
