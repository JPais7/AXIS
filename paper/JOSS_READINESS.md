# JOSS submission readiness

Assessment date: 2 August 2026

This checklist follows the current JOSS submission and review criteria. It is a
readiness record, not evidence that the manuscript has been submitted.

## Blocking gate

- [ ] **More than six months of public, active development.** The repository
  became public on 2 August 2026. Do not submit before 2 February 2027, and only
  then if the public commit history shows genuine development across the
  interval. A repository dump or artificial commits do not satisfy this gate.

## Required software criteria

- [x] Public source repository where users can browse code and propose changes.
- [x] OSI-approved Apache License 2.0.
- [x] Clear research application.
- [x] Python package and command-line entry point.
- [x] Locked dependencies and installation instructions.
- [x] Automated test suite.
- [x] Continuous integration on Linux, macOS, and Windows with Python 3.12.
- [x] Contribution, conduct, security, support, and citation guidance.
- [x] Archived software record with DOI.
- [ ] Demonstrate continuing maintenance through issues, releases, and genuine
  changes during the six-month public-history period.
- [ ] Obtain at least one documented external installation or research use if
  possible. This is not a substitute for the six-month gate, but strengthens
  the research-impact case.

## Paper criteria

- [x] `paper.md` with JOSS YAML metadata.
- [x] Paper length within the 750-1,750-word target at preparation time.
- [x] Non-specialist summary and statement of need.
- [x] State-of-the-field comparison with related tools.
- [x] Software design and verification evidence.
- [x] Specific research impact statement.
- [x] Transparent AI usage disclosure.
- [x] Limitations and acknowledgements.
- [x] `paper.bib` with key methods, related tools, and the software archive.
- [x] Publication figure stored in the repository and referenced by the paper.
- [ ] João Pais and Diana Koshman approve the final text and authorship.
- [ ] Add ORCID identifiers if the authors have them.
- [ ] Reconfirm affiliation wording, funding, and competing-interest statements.
- [ ] Compile with the current Open Journals toolchain immediately before
  submission and inspect the resulting PDF.

## Release immediately before submission

- [ ] Resolve all substantive open issues intended for the submitted version.
- [ ] Run the complete tests and cross-platform CI.
- [ ] Create a stable semantic-version tag; do not describe a development build
  as the reviewed release.
- [ ] Archive that exact tag in Zenodo and replace `archive_doi` in `paper.md`
  with the version-specific DOI if the current DOI does not identify it.
- [ ] Confirm that installation and the synthetic demonstration work from the
  archived release on a clean computer.
- [ ] Submit through JOSS only after every blocking item above is satisfied.

## Current decision

**Not ready to submit on 2 August 2026.** The package is prepared so that it can
evolve with the software, but submission now would fail the mandatory public
development-history gate.
