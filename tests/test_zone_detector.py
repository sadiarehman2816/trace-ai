"""tests/test_zone_detector.py — validates Zone Detector v1 against the spec.

Run: python tests/test_zone_detector.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verification import zone_detector as zd

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def zone_of(text, pages=None):
    """Detect and return {line_text: zone} for single-line lookups."""
    return {z.text.strip(): z.zone for z in zd.detect_zones(text, pages)}


# ---------------------------------------------------------------------------
# Spec test cases 1-5
# ---------------------------------------------------------------------------

print("== Spec cases ==")

# Case 2: running header (all-caps short line, with page structure)
pages = [
    {"page_number": 1, "lines": ["1538 THE AMERICAN ECONOMIC REVIEW", "Real body sentence one here.", "More body text follows here."]},
    {"page_number": 2, "lines": ["1539 THE AMERICAN ECONOMIC REVIEW", "Body continues on the second page.", "Yet more analysis appears here now."]},
    {"page_number": 3, "lines": ["1540 THE AMERICAN ECONOMIC REVIEW", "Third page body text is present.", "Concluding remarks are written here."]},
]
zmap = {z.text.strip(): z.zone for z in zd.detect_zones("", pages)}
check("Case 2: all-caps running head -> header_footer",
      zmap.get("1538 THE AMERICAN ECONOMIC REVIEW") == "header_footer", str(zmap))

# Case 3: OCR junk
z = zone_of("Id Trn Oid\nThis is a normal body sentence about welfare systems.")
check("Case 3: 'Id Trn Oid' -> noise", z.get("Id Trn Oid") == "noise", str(z))

# Case 4: real content -> body
check("Case 4: real content -> body",
      z.get("This is a normal body sentence about welfare systems.") == "body", str(z))

# Case 5: bibliography entry -> references
doc5 = "References\n\nO'Neil, C. (2016) Weapons of Math Destruction. Crown Publishing.\n"
z5 = zone_of(doc5)
check("Case 5: bibliography entry -> references",
      z5.get("O'Neil, C. (2016) Weapons of Math Destruction. Crown Publishing.") == "references", str(z5))

# Case 1: DOI line -> metadata (outside references) / references (inside)
z1a = zone_of("DOI: 10.1000/xyz\nSome body text here for context.")
check("Case 1a: DOI line outside references -> metadata",
      z1a.get("DOI: 10.1000/xyz") == "metadata", str(z1a))
z1b = zone_of("References\n\nDOI: 10.1000/xyz\n")
check("Case 1b: DOI line inside references -> references (override)",
      z1b.get("DOI: 10.1000/xyz") == "references", str(z1b))

# ---------------------------------------------------------------------------
# Design rules
# ---------------------------------------------------------------------------

print("== Design rules ==")

# Rule A: no deletion — every input line present in output
src = "Line one\nDOI: 10.1/x\nId Trn Oid\nReferences\nSmith, J. (2020). A title. Journal, 1(1), 1-9."
zoned = zd.detect_zones(src)
check("Rule A: no deletion (line count preserved)",
      len(zoned) == len(src.split("\n")), f"{len(zoned)} vs {len(src.split(chr(10)))}")

# Rule B: conservative noise — an ordinary short sentence is NOT noise
z_amb = zone_of("The system failed.")
check("Rule B: ordinary short line is NOT noise",
      z_amb.get("The system failed.") != "noise", str(z_amb))

# Rule D: determinism — same input twice gives identical labels
a = [(z.zone, z.confidence) for z in zd.detect_zones(src)]
b = [(z.zone, z.confidence) for z in zd.detect_zones(src)]
check("Rule D: deterministic (identical output on repeat)", a == b)

# Default: ambiguous body
z_def = zone_of("Algorithmic surveillance reshapes welfare decision-making processes.")
check("Default: normal prose -> body",
      z_def.get("Algorithmic surveillance reshapes welfare decision-making processes.") == "body")

# ---------------------------------------------------------------------------
# Precedence & consumers
# ---------------------------------------------------------------------------

print("== Precedence & consumers ==")

# references > metadata already tested (Case 1b). Test header_footer vs body:
z_pg = zone_of("Page 5")
check("Page number line -> header_footer", z_pg.get("Page 5") == "header_footer", str(z_pg))

# Degraded mode (no pages): repeated line becomes pseudo-header with lower confidence.
# Use a mixed-case line so ONLY the pseudo-repeat signal fires (not the all-caps heuristic).
blob = "Common header line here\nBody a.\nCommon header line here\nBody b.\nCommon header line here\nBody c."
zoned_blob = zd.detect_zones(blob)
hdr = [z for z in zoned_blob if z.text.strip() == "Common header line here"]
check("Degraded mode: repeated line -> header_footer (pseudo)",
      all(z.zone == "header_footer" for z in hdr) and len(hdr) == 3, str([(z.zone, z.confidence) for z in hdr]))
check("Degraded mode: single pseudo-repeat signal has weak confidence (<=0.5)",
      all(z.confidence <= 0.5 for z in hdr), str([z.confidence for z in hdr]))

# Consumer helpers
zoned2 = zd.detect_zones("References\n\nSmith, J. (2020). Title. Journal, 1(1), 1-9.\n")
refs_text = zd.zone_text(zoned2, "references")
check("Consumer: zone_text extracts references", "Smith, J. (2020)" in refs_text, refs_text)

body_only = zd.zone_text(zd.detect_zones("Id Trn Oid\nReal welfare policy analysis sentence."), "body")
check("Consumer: body excludes OCR noise",
      "Id Trn Oid" not in body_only and "Real welfare" in body_only, body_only)

# Blocks grouping
blocks = zd.group_blocks(zd.detect_zones("A body line.\nB body line.\nReferences\nSmith (2020)."))
check("Blocks: contiguous same-zone grouped", any(b["zone"] == "references" for b in blocks), str(blocks))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
