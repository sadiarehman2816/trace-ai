"""JSON export (outputs/json_export.py). Excludes internal-only keys."""

import json

_INTERNAL_KEYS = {"pdf_path_map"}


def to_json(result: dict) -> str:
    """Serialise a result dict to a JSON string, excluding internal-only keys."""
    export = {k: v for k, v in result.items() if k not in _INTERNAL_KEYS}
    return json.dumps(export, indent=2, ensure_ascii=False)
