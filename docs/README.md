# Documentation map

## Current entry points

- [Scientific state: ERAP1 × axSpA](erap1-current-scientific-state.md): authoritative
  current summary, derived from the frozen reassessment, not older phase narratives.
- [Architecture and case boundaries](repository-architecture.md).
- [Consolidation audit and promotion conditions](axis-repository-consolidation-2026.md).
- [Independent installation](independent-installation-validation.md).
- [Scientific policy](../SCIENTIFIC_POLICY.md): evidence and review boundaries.
- [Developer setup](../README.md#development).
- [Decision Engine](phase3-experimental-decision-engine.md),
  [results loop](phase36-experimental-results-loop.md),
  [computational discovery](phase38-computational-discovery.md),
  [chemical learning](phase39-chemical-learning.md).

## Offline scientific reproduction

From a checkout with Python 3.12 and the project installed:

```shell
PYTHONPATH=. python scripts/audit_axis_consolidation.py
python -m pytest tests/test_consolidation.py tests/test_erap1_bradshaw_reassessment.py
```

The first command verifies all pre-existing resources, commercial v1 and benchmark
bytes against the pre-refactor reference and executes the actual frozen decision
reassessment. It needs neither the original licensed PDFs nor a network connection.
Do not use `--capture` on a candidate: it is restricted to the exact golden commit.

## Historical archive policy

The [file-level inventory](consolidation/2026/repository-inventory.json) designates
19 narratives/one-off authoring utilities as ARCHIVE. This is a **logical archive**:
zero paths are moved or deleted. Frozen manifests, historical imports, test fixtures,
and existing links continue to resolve. ARCHIVE means “not the current status entry
point”, not “disposable” or “scientifically false”. Earlier blocked reassessments
describe the access state at their time; the current summary describes the later
legitimate full-text resolution.

Old phase reports and DDX24 document-authoring scripts remain historical records.
They must not be read as descriptions of current ERAP1 decisions. Case-specific
reproduction scripts remain active compatibility interfaces and are not archived
merely because they name ERAP1.
