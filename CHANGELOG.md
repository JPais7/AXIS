# Changelog

All notable changes to AXIS are documented in this file. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Updated citation, manuscript and project links to the version-specific AXIS
  0.2.0 Zenodo DOI and the public `axis-bio` PyPI distribution.
- Advanced the development version after the immutable 0.2.0 publication.

## [0.2.0] - 2026-08-02

### Added

- Collision-safe `axis-bio` package metadata and a trusted-publishing workflow
  that verifies a clean wheel before publishing it to PyPI.
- Native-limma validation across four GEO cohorts, including a covariate-adjusted
  contrast, an offline regression guard and a publication-ready figure.
- Public `axis benchmark` command for repeated, offline measurement of the
  synthetic demonstration, with aggregate JSON and per-run TSV outputs.
- Independent installation-validation protocol and structured GitHub report.
- Guarded synthetic workflow-comparison package with separate blinded evaluator
  materials, coordinator reference, two-reviewer ratings and article tables.
- Scoped comparison v2 separates real-accession differential expression from
  synthetic evidence governance and prohibits cross-scope rankings.

## [0.1.0] - 2026-08-02

### Added

- Auditable ingestion and cataloguing of public biomedical studies.
- Participant-aware bulk, RNA-seq and single-cell analysis workflows.
- Cross-study recurrence ranking, meta-analysis and sensitivity analysis.
- Genetic, mechanistic, structural and pharmacological target assessment.
- Frozen DDX24 case-study reproduction with integrity checks.
- Synthetic offline demonstration runnable with `axis demo`.
- Reproducibility, publication and scientific-governance documentation.
- Automated testing on Linux, macOS and Windows with Python 3.12.

### Scientific scope

AXIS 0.1.0 generates auditable research hypotheses. Its outputs are not
clinical recommendations and do not establish causality, efficacy or safety.

[Unreleased]: https://github.com/JPais7/AXIS/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/JPais7/AXIS/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/JPais7/AXIS/releases/tag/v0.1.0
