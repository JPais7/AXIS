# AXIS release checklist

Status on 2 August 2026: **ready to tag version 0.1.0**. Version 1.0.0
remains conditional on external validation and the remaining gates below.

## Completed locally

- [x] Apache 2.0 license and copyright notice
- [x] citation metadata
- [x] contribution, support, security and conduct guidance
- [x] explicit scientific-use policy
- [x] synthetic offline demonstration distributed with the package
- [x] checksum and deliberate-tampering test for the demonstration
- [x] Windows, Linux and macOS continuous-integration definition
- [x] 138 automated tests passing locally
- [x] wheel built locally with the packaged demo verified at 9/9 checks
- [x] local Git repository initialized on the `main` branch
- [x] trackable-file audit: 201 files and no file above 5 MB
- [x] synthetic demo benchmark completed over 10 local repetitions
- [x] Ruff and strict mypy checks passing
- [x] DDX24 frozen reproduction with 25/25 checks
- [x] first formal AXIS methods-manuscript draft

## Required before tagging 1.0.0

- [x] create the public GitHub repository at `JPais7/AXIS`
- [x] add a private security and conduct contact
- [x] enable and observe the first successful CI run on all three systems
- [x] install a built wheel in a clean environment and run `axis demo`
- [ ] ask an independent person to install and execute the demonstration
- [ ] record runtime and peak memory for the demo and frozen case study
- [ ] complete the predeclared comparison with alternative workflows
- [x] archive the tagged release and add its DOI to `CITATION.cff`
- [x] obtain author approval for joint authorship and copyright
- [ ] obtain final author approval of the exact public repository contents

The version in `pyproject.toml` remains `0.1.0` until these release gates are
met. Passing local checks is necessary but is not external portability.
