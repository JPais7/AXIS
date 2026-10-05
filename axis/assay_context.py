"""Target-agnostic contracts for curated, inference-scoped assay limitations.

These contracts do NOT compute ratios, infer inheritance, change admission or
turn phenotype into engagement. Adjudication is supplied explicitly by a
source-linked registry. Quantitative selectivity and decision rules stay intact.
"""

from dataclasses import dataclass
from typing import Literal

Comparability = Literal[
    "COMPARABLE",
    "PARTIALLY_COMPARABLE",
    "NOT_COMPARABLE",
    "INSUFFICIENT_METHOD_INFORMATION",
]
STATUSES = frozenset(
    {
        "COMPARABLE",
        "PARTIALLY_COMPARABLE",
        "NOT_COMPARABLE",
        "INSUFFICIENT_METHOD_INFORMATION",
    }
)


@dataclass(frozen=True)
class ScopedLimitation:
    missing_fields: tuple[str, ...]
    affected_inference: str
    blocks_current_decision: bool
    reason: str
    blocking_rule: str | None = None

    def __post_init__(self) -> None:
        if not self.missing_fields or not self.affected_inference or not self.reason:
            raise ValueError("a limitation needs fields, inference and justification")
        if self.blocks_current_decision and not self.blocking_rule:
            raise ValueError(
                "a global blocker requires an explicit decision dependency"
            )

    @property
    def classification(self) -> str:
        return (
            "DECISION_BLOCKER" if self.blocks_current_decision else "LOCAL_LIMITATION"
        )


@dataclass(frozen=True)
class CuratedComparison:
    family: str
    status: Comparability
    inference: str
    source_registry: str
    condition: str | None = None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError("unrecognized curated comparability category")
        if not self.family or not self.inference or not self.source_registry:
            raise ValueError("comparability requires scope and a source registry")
