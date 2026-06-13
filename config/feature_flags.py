"""
TRACE-AI — Feature Flags (config/feature_flags.py)

Toggles for optional / premium capabilities (DO #4). Turning a feature off here
disables it everywhere without touching logic. This keeps the core verification
engine stable while features can be rolled out or held back.

Why flags: TRACE-AI is a research-integrity platform; we want to ship the
trustworthy core and gate newer/heavier features behind explicit switches
rather than half-wiring them into the pipeline.
"""

FEATURE_FLAGS = {
    # Theme discovery (auto-generate themes from documents)
    "auto_theme": True,

    # PDF highlight viewer (click evidence -> see highlighted page)
    "pdf_highlight": True,

    # Multi-format inputs
    "input_docx": True,
    "input_csv": True,
    "input_xlsx": True,
    "input_url": True,

    # Exports
    "export_json": True,
    "export_docx": True,
    "export_xlsx": True,

    # Evidence-quality features
    "evidence_quality_filter": True,   # reject metadata/fragment spans
    "evidence_type_labels": True,      # 📊 / 🗣 / 📜 / etc.
    "definition_downweight": True,     # definitions score lower than findings

    # Confidence features
    "source_diversity_bonus": True,    # cross-source corroboration bonus

    # LIVE-mode AI synthesis (requires ANTHROPIC_API_KEY)
    "llm_theme_synthesis": True,

    # --- HYBRID MODE POLICY (trust boundary) -------------------------------
    # These define exactly where the LLM is permitted to act. They are wired
    # into the engine; flipping them does not silently move logic.
    #
    # The LLM may ONLY generate/rename/merge abstract themes. It must NEVER
    # select evidence, assign confidence, modify scores, or override
    # verification. Those four are hard-locked to deterministic code regardless
    # of these flags.
    "llm_evidence_selection": False,   # HARD-LOCKED off — do not enable
    "llm_adversarial_review": False,   # HARD-LOCKED off — do not enable
    "llm_confidence": False,           # HARD-LOCKED off — do not enable
    "llm_scoring": False,              # HARD-LOCKED off — do not enable
}


def is_enabled(flag: str) -> bool:
    """Returns True if a feature flag is on. Unknown flags default to False."""
    return bool(FEATURE_FLAGS.get(flag, False))
