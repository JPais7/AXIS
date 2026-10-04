"""Epistemic boundary of computational results (release-blocking, tested).

A computational output is an AXIS-generated observation or inference with explicit
method provenance. It can never be an experimental result or a source assertion, and
prioritization never turns a molecule into an "active" one.
"""

import re
from typing import Any

ALLOWED_CLASSES = ("axis_observation", "axis_inference")
FORBIDDEN_CLASSES = (
    "experimental_result",
    "source_assertion",
    "accepted_experimental_evidence",
)
REQUIRED_PROVENANCE = (
    "method",
    "tool",
    "tool_version",
    "parameters",
    "input_sha256",
    "output_sha256",
)
# Wording that would assert more than a computation can support.
OVERCLAIM = re.compile(
    r"\b(is active|are active|validated binder|confirmed hit|lead compound|"
    r"drug candidate|therapeutic molecule|binds (?:to )?ERAP|inhibits ERAP|"
    r"is selective|demonstrated selectivity|experimentally validated)\b",
    re.IGNORECASE,
)
# Negations that legitimately appear in boundary statements.
ALLOWED_CONTEXT = re.compile(
    r"\b(not|no|nor|never|without|cannot|neither|nothing)\b", re.IGNORECASE
)


class EpistemicError(ValueError):
    """A computational record tried to claim more than computation can support."""


def validate_observation(observation: dict[str, Any]) -> None:
    cls = observation.get("epistemic_class")
    if cls in FORBIDDEN_CLASSES:
        raise EpistemicError(
            f"a computational observation cannot be {cls}: "
            "it cannot be experimental evidence"
        )
    if cls not in ALLOWED_CLASSES:
        raise EpistemicError(f"unknown epistemic class {cls!r} for a computation")
    if observation.get("experimental") is not False:
        raise EpistemicError(
            "a computational observation must declare experimental=false"
        )
    missing = [k for k in REQUIRED_PROVENANCE if k not in observation]
    if missing:
        raise EpistemicError(
            f"observation lacks method provenance: {', '.join(missing)}"
        )


def overclaims(text: str) -> list[str]:
    """Phrases asserting activity/binding/selectivity not established by computation."""
    found = []
    for match in OVERCLAIM.finditer(text):
        start = max(
            text.rfind(". ", 0, match.start()), text.rfind("\n\n", 0, match.start())
        )
        if not ALLOWED_CONTEXT.search(text[start + 1 : match.start()]):
            found.append(match.group(0))
    return found
