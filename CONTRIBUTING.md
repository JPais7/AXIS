# Contributing to AXIS

AXIS welcomes corrections, tests, documentation and carefully scoped analysis
features. Scientific correctness and traceability take priority over feature
count.

## Before contributing

1. Open an issue describing the scientific question, evidence role and expected
   behavior.
2. Do not add identifiable participant data, restricted datasets, credentials
   or large raw files.
3. State whether generated or AI-assisted material was used and how it was
   checked.
4. Keep discovery, validation, sensitivity, mechanistic and treatment-response
   evidence distinct.

## Development checks

Use Python 3.12 and install the locked development environment. Before opening
a change, run:

```shell
pytest -q
ruff check axis tests
mypy axis
axis demo
```

Every behavior change should include a test. Changes to frozen evidence must
update checksums deliberately and explain why the scientific claim remains
valid. Never weaken a guardrail merely to make a dataset pass.

## Review

Contributions are reviewed for code quality, scientific validity, provenance,
privacy, test coverage and compatibility with the declared research question.
Submission does not guarantee acceptance.
