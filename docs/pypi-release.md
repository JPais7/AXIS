# Publishing AXIS on PyPI

AXIS uses `axis-bio` as its distribution name. The shorter `axis` name is
already owned by an unrelated PyPI project. Installing `axis-bio` still
provides the `axis` Python module and command-line program.

## One-time trusted-publishing setup

1. Sign in to PyPI and create the `axis-bio` project using an initial manual
   upload, or create a pending trusted publisher for a new project.
2. Configure a trusted publisher with these exact values:
   - owner: `JPais7`
   - repository: `AXIS`
   - workflow: `publish-pypi.yml`
   - environment: `pypi`
3. In the GitHub repository, create an environment named `pypi`. Add required
   reviewers if publication should require a manual approval.

No PyPI password or API token is stored in GitHub. The workflow requests a
short-lived identity token only for the publication job.

## Release procedure

1. Replace the development version in `pyproject.toml` with the intended
   release version and update `CHANGELOG.md` and `CITATION.cff`.
2. Run the complete local checks and confirm that CI passes.
3. Commit the release metadata and create the matching Git tag and GitHub
   release, for example `v0.2.0`.
4. Publishing the GitHub release starts the `Publish Python package` workflow.
   It builds the wheel and source archive, checks their metadata, installs the
   wheel in a clean environment, runs `axis demo`, and only then publishes.
5. Download the release from PyPI on a clean machine and confirm:

   ```shell
   python -m pip install axis-bio
   axis demo
   ```

Running the workflow manually performs the build and verification but cannot
publish. This makes it safe to test before creating a release.

## Safety rule

Never reuse a version number. PyPI releases are immutable. If publication
fails after a file has been accepted, increment the version before retrying.
