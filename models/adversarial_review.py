"""
TRACE-AI v0.1 — Steps 3 & 5: Claude-powered Evidence Selection + Adversarial Review

Step 3 (Hard Evidence Lock):
  Claude is shown ONLY the Top-K pre-retrieved spans (closed set) and must
  select which span_id(s) support the theme. It cannot invent text, IDs, or
  pages — it can only choose from the provided list. Any returned ID outside
  the provided set is discarded by code.

Step 5 (Structured Adversarial Review):
  For each selected span, Claude acts as a skeptical auditor and answers three
  fixed YES/NO questions. The mapping from answers -> result is deterministic
  (done in code, not by the model).

Both steps support a MOCK MODE (no API key / offline) so the full pipeline can
be tested deterministically. In production, set ANTHROPIC_API_KEY and the real
Claude calls are used.
"""

import os
import json
import re

MODEL = "claude-opus-4-8"


# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------
def _get_client():
    """Returns an Anthropic client if a key is available, else None (mock mode)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=api_key)
    except Exception:
        return None


def _call_claude(client, system_prompt: str, user_prompt: str) -> str:
    """Single non-streaming call returning concatenated text content."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _extract_json(text: str):
    """Strip markdown fences and parse the first JSON object/array found."""
    cleaned = re.sub(r"```json|```", "", text).strip()
    # Try direct parse first
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Fall back to locating the first {...} or [...] block
    match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# STEP 3 — Hard Evidence Lock (span selection from closed set)
# ---------------------------------------------------------------------------
SELECTION_SYSTEM = (
    "You are an evidence-selection component in a research verification system. "
    "You will be given a THEME and a numbered list of candidate text spans, each "
    "with a span_id. Your ONLY job is to select which span_id(s), if any, directly "
    "support the theme. RULES: (1) You may ONLY choose span_ids from the provided "
    "list. (2) Do NOT invent, paraphrase, or quote any text. (3) If none of the "
    "spans support the theme, return an empty list. (4) Be conservative: only "
    "select a span if it genuinely supports the theme. "
    'Respond ONLY with JSON of the form {"selected_span_ids": ["...", "..."]} and nothing else.'
)


def select_spans(theme: str, candidate_spans: list[dict], client=None) -> list[str]:
    """
    Step 3. Returns a list of selected span_ids (subset of candidate span_ids).
    candidate_spans: list of {span_id, text, ...} from Step 1-2 retrieval.

    HYBRID MODE: evidence selection is ALWAYS deterministic. The LLM is never
    allowed to choose evidence — that would let an AI influence which facts
    enter the verification pipeline. The `client` argument is intentionally
    ignored here; it remains in the signature only for interface compatibility.
    """
    if not candidate_spans:
        return []

    # Deterministic keyword-overlap selection (never LLM, even in LIVE mode).
    return _mock_select_spans(theme, candidate_spans)


def _mock_select_spans(theme: str, candidate_spans: list[dict]) -> list[str]:
    """Deterministic stand-in for Claude selection (offline testing)."""
    stop = {
        "the", "a", "an", "of", "to", "in", "on", "and", "or", "for", "with",
        "is", "are", "this", "that", "by", "as", "at", "from", "impact",
        "outcomes", "report",
    }
    theme_words = {w for w in re.findall(r"[a-z]+", theme.lower()) if w not in stop and len(w) > 2}

    selected = []
    for s in candidate_spans:
        span_words = set(re.findall(r"[a-z]+", s["text"].lower()))
        overlap = theme_words & span_words
        # Select if it shares at least one meaningful theme word
        if overlap:
            selected.append(s["span_id"])
    return selected


# ---------------------------------------------------------------------------
# STEP 5 — Structured Adversarial Review (3 fixed YES/NO questions)
# ---------------------------------------------------------------------------
ADVERSARIAL_SYSTEM = (
    "You are a SKEPTICAL AUDITOR in a research verification system. Default to "
    "rejection. You will be given a THEME and a single text SPAN. Answer exactly "
    "three questions, each strictly YES or NO:\n"
    "Q1 (support): Does this span DIRECTLY support the theme?\n"
    "Q2 (extrapolation): Is the theme's claim EXTRAPOLATED BEYOND what the span "
    "literally states?\n"
    "Q3 (context): Is the span's original context PRESERVED (i.e. it is not "
    "cherry-picked or misleading when read on its own)?\n"
    'Respond ONLY with JSON of the form {"q1": "YES/NO", "q2": "YES/NO", "q3": "YES/NO"} '
    "and nothing else."
)


def adversarial_review(theme: str, span_text: str, client=None) -> dict:
    """
    Step 5. Returns {"q1":..., "q2":..., "q3":..., "result": "Pass/Weak/Reject"}.

    HYBRID MODE: adversarial review is ALWAYS deterministic. The LLM is never
    allowed to judge whether evidence supports a claim — that judgement is the
    heart of verification and must stay rule-based and reproducible. The Q1/Q2/Q3
    answers come from code heuristics; the result mapping is deterministic. The
    `client` argument is ignored here and kept only for interface compatibility.
    """
    answers = _mock_adversarial(theme, span_text)
    answers["result"] = _map_adversarial_result(answers)
    return answers


def _map_adversarial_result(a: dict) -> str:
    """
    Deterministic mapping per the locked spec:
      Q1=YES, Q2=NO,  Q3=YES -> Pass
      Q1=YES, (Q2=YES) or (Q3=NO) -> Weak
      Q1=NO -> Reject
    """
    q1 = a.get("q1", "NO") == "YES"
    q2_extrapolated = a.get("q2", "YES") == "YES"
    q3_context = a.get("q3", "NO") == "YES"

    if not q1:
        return "Reject"
    if not q2_extrapolated and q3_context:
        return "Pass"
    return "Weak"


def _mock_adversarial(theme: str, span_text: str) -> dict:
    """
    Deterministic stand-in for Claude's adversarial review (offline testing).
    Heuristic:
      - Q1 YES if the span shares >=1 meaningful theme word.
      - Q2 (extrapolated) YES if the theme has meaningful words NOT present in the
        span (i.e. the theme reaches beyond the span).
      - Q3 (context preserved) YES if the span is a reasonably complete sentence.
    """
    stop = {
        "the", "a", "an", "of", "to", "in", "on", "and", "or", "for", "with",
        "is", "are", "this", "that", "by", "as", "at", "from", "impact",
        "outcomes", "report",
    }
    theme_words = {w for w in re.findall(r"[a-z]+", theme.lower()) if w not in stop and len(w) > 2}
    span_words = set(re.findall(r"[a-z]+", span_text.lower()))

    overlap = theme_words & span_words
    missing = theme_words - span_words

    q1 = "YES" if overlap else "NO"
    # If most theme words are missing from the span, it's an overreach
    q2 = "YES" if (theme_words and len(missing) > len(overlap)) else "NO"
    # Context preserved if span looks like a full sentence (ends with terminal punct, reasonable length)
    q3 = "YES" if (len(span_text) > 25 and span_text.strip()[-1:] in ".!?") else "NO"

    return {"q1": q1, "q2": q2, "q3": q3}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    client = _get_client()
    mode = "LIVE (Claude API)" if client else "MOCK (offline deterministic)"
    print(f"Mode: {mode}\n")

    spans = [
        {"span_id": "c0001_s01", "text": "Affordable housing demand exceeds supply across most regions of England."},
        {"span_id": "c0001_s04", "text": "Social housing waiting lists continue to increase year on year."},
        {"span_id": "c0002_s01", "text": "Investment in regional rail links increased by 12 percent."},
    ]

    print("STEP 3 — select_spans for theme 'Housing Affordability':")
    sel = select_spans("Housing Affordability", spans, client)
    print("  selected:", sel)

    print("\nSTEP 5 — adversarial_review for each selected span:")
    for sid in sel:
        text = next(s["text"] for s in spans if s["span_id"] == sid)
        rev = adversarial_review("Housing Affordability", text, client)
        print(f"  {sid}: {rev}")
