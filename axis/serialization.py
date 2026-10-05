"""Canonical JSON shared by existing versioned scientific contracts.

Do not change Unicode, separators or fallback behavior without versioning every
dependent digest. This is serialization, not scientific normalization.
"""

import json


def canonical_json(value: object) -> str:
    """Preserve the historical sort/separators/default=str contract exactly."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
