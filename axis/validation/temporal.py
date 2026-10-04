"""Temporal availability, cutoffs, filtered snapshots and fingerprints (pure).

Eligibility uses the first date a source was publicly accessible, never the
nominal publication year. Unknown or uncertain availability never enters a window.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from axis.domain.validation import ELIGIBLE_KINDS

RECORD_KINDS = (
    "experiments",
    "assessments",
    "readouts",
    "biochemical_measurements",
    "selectivity",
    "compounds",
    "gaps",
)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class TemporalCutoff:
    """Immutable decision date T: sources accessible on or before it are visible."""

    cutoff_id: str
    date: date
    rationale: str

    @staticmethod
    def parse(cutoff_id: str, day: str, rationale: str) -> "TemporalCutoff":
        return TemporalCutoff(cutoff_id, date.fromisoformat(day), rationale)


def source_eligibility(
    availability: dict[str, Any], source: str, cutoff: TemporalCutoff
) -> tuple[bool, str]:
    entry = availability.get(source)
    if entry is None:
        return False, "source_not_in_availability_table"
    kind = entry.get("availability_kind", "unknown")
    day = entry.get("first_publicly_accessible_date")
    if kind not in ELIGIBLE_KINDS or not day:
        return False, "availability_unknown_or_uncertain"
    if date.fromisoformat(day) > cutoff.date:
        return False, "record_after_cutoff"
    return True, "available_on_or_before_cutoff"


def rid(item: Any) -> str:
    """Record identifier: compounds are plain ids, every other record has ``id``."""
    return str(item if isinstance(item, str) else item["id"])


def source_of(record_sources: dict[str, str], kind: str, record: Any) -> str | None:
    return record_sources.get(f"{kind}:{rid(record)}")


UNDATED = ("availability_unknown_or_uncertain", "source_not_in_availability_table")


def _bucket(
    availability: dict[str, Any],
    source: str | None,
    cutoff: TemporalCutoff,
    horizon: date | None,
) -> tuple[str, str]:
    if not source:
        return "undated", "source_not_in_availability_table"
    ok, reason = source_eligibility(availability, source, cutoff)
    if ok:
        return "window", reason
    if reason in UNDATED:
        return "undated", reason
    day = date.fromisoformat(availability[source]["first_publicly_accessible_date"])
    if horizon is not None and day > horizon:
        return "beyond_horizon", "after_the_declared_horizon"
    return "future", reason


def partition(
    records: dict[str, Any],
    record_sources: dict[str, str],
    availability: dict[str, Any],
    cutoff: TemporalCutoff,
    horizon: date | None = None,
    excluded_sources: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    """Split a full evidence set into (window, future, per-record decisions).

    A record whose source cannot be shown available at T never enters the window.
    Records whose availability is unknown or uncertain are *undated*: they enter
    neither the window nor the revealed future, because their position relative to
    T cannot be established. Records after the declared horizon are excluded from
    the future set as well.
    """
    window: dict[str, Any] = {
        k: ([] if isinstance(v, list) else v) for k, v in records.items()
    }
    future: dict[str, Any] = {
        k: ([] if isinstance(v, list) else v) for k, v in records.items()
    }
    decisions: list[dict[str, str]] = []

    def place(kind: str, item: Any, key: str) -> None:
        source = record_sources.get(key)
        if source in excluded_sources:
            bucket, reason = "excluded", "excluded_by_case_design"
        else:
            bucket, reason = _bucket(availability, source, cutoff, horizon)
        if bucket == "window":
            target = window
        elif bucket == "future":
            target = future
        else:
            target = None
        if target is not None:
            if kind == "structure_ids":
                target[kind].append(item)
            else:
                target[kind].append(item)
        decisions.append(
            {
                "record": key,
                "source": source or "",
                "decision": bucket,
                "reason": reason,
            }
        )

    for kind in RECORD_KINDS:
        for item in records[kind]:
            place(kind, item, f"{kind}:{rid(item)}")
    # Project scaffolding (strategy identifiers) is design-time context rather
    # than literature evidence; it stays in every window and is disclosed.
    window["strategy_ids"] = list(records.get("strategy_ids", []))
    window["structure_ids"] = []
    future["structure_ids"] = []
    for structure in records.get("structure_ids", []):
        place("structure_ids", structure, f"structure_ids:{structure}")
    return window, future, decisions


def merge(window: dict[str, Any], future: dict[str, Any]) -> dict[str, Any]:
    """Window plus revealed evidence (T+1). Only the runner's reveal step calls this."""
    merged: dict[str, Any] = {}
    for key, value in window.items():
        extra = future.get(key, [])
        merged[key] = list(value) + list(extra) if isinstance(value, list) else value
    return merged


def snapshot_fingerprint(
    window: dict[str, Any], cutoff: TemporalCutoff, availability_digest: str
) -> str:
    return digest(
        {
            "cutoff": cutoff.date.isoformat(),
            "availability": availability_digest,
            "window": window,
        }
    )


def record_ids(records: dict[str, Any]) -> list[str]:
    ids = [f"{k}:{rid(r)}" for k in RECORD_KINDS for r in records.get(k, [])]
    ids += [f"structure_ids:{s}" for s in records.get("structure_ids", [])]
    return sorted(ids)
