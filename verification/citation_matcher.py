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


def check_consistency(
    refs: list[NormalizedReference],
    intext: list[dict],
) -> ConsistencyReport:
    report = ConsistencyReport()

    # Index references by FIRST-author surname -> set of (base) years present.
    ref_surnames_years: dict[str, set[str]] = {}
    for ref in refs:
        if ref.authors and ref.year:
            s = _surname(ref.authors[0])
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

        if lead not in ref_surnames_years:
            report.cited_not_listed.append(f"{cite.get('author', lead)} ({cite.get('year')})")
            continue

        years = ref_surnames_years[lead]
        if year and year not in years:
            report.year_mismatches.append(
                f"{cite.get('author', lead)} cited for {cite.get('year')} "
                f"but bibliography only has {', '.join(sorted(years))}"
            )
        # Mark matching refs as cited (first-author surname + year).
        for ref in refs:
            if ref.authors and _surname(ref.authors[0]) == lead and (
                not year or str(ref.year) == year
            ):
                cited_ref_indices.add(ref.index)

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

    # Listed but never cited
    if intext:                                   # only meaningful if we found in-text citations at all
        for ref in refs:
            if ref.index not in cited_ref_indices:
                report.listed_not_cited.append(ref.index)

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
