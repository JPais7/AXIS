"""Explicit case configuration; never infer biological policy from a gene name."""

import json
from importlib import resources
from typing import Any


def reference_case(name: str) -> dict[str, Any]:
    """Read a named profile, independently of immutable source manifests."""
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"
    if not name or any(c not in allowed for c in name):
        raise ValueError("invalid case profile name")
    raw = resources.files("axis").joinpath(f"resources/cases/{name}.json").read_text()
    value: dict[str, Any] = json.loads(raw)
    if value.get("schema_version") != 1:
        raise ValueError("unsupported case profile version")
    return value
