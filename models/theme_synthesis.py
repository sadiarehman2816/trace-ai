"""
TRACE-AI — AI Theme Synthesis (models/theme_synthesis.py)

LIVE-mode only: turns deterministic keyword clusters into clean,
researcher-friendly theme names using Claude. Isolated from the deterministic
theme engine (DO #9) — the rule engine still decides which themes to *use*; this
only proposes nicer phrasing (DO #10, AI suggests).
"""

import re
import json as _json


def synthesise_themes(raw_themes, texts, client, final_count):
    """
    Asks Claude to convert keyword clusters into clean research themes.
    Returns a list of theme strings, or None on any failure (caller falls back
    to the deterministic clusters).
    """
    if client is None or not raw_themes:
        return None

    sample = " ".join(texts[:20])[:4000]
    system = (
        "You are a research analyst. Given keyword clusters extracted from a "
        "document and a text sample, produce a short list of clean, "
        "researcher-friendly THEMES (noun phrases like 'Housing Affordability', "
        "'Energy Efficiency', 'Rental Pressures'). Do NOT include document titles, "
        "table/figure/annex references, or structural words. "
        f"Return ONLY a JSON array of {final_count} theme strings, nothing else."
    )
    user = (f"Keyword clusters: {', '.join(raw_themes)}\n\n"
            f"Text sample:\n{sample}\n\n"
            f"Return {final_count} clean themes as a JSON array.")
    try:
        resp = client.messages.create(
            model="claude-opus-4-8", max_tokens=512,
            system=system, messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        text = re.sub(r"```json|```", "", text).strip()
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            themes = _json.loads(m.group(0))
            return [str(t).strip() for t in themes if str(t).strip()]
    except Exception:
        return None
    return None
