# Phase 3.3 — chemical identity and contextual pharmacology

This layer answers what representation was reported, what target material and
assay were used, and what was measured. It does not select a drug or therapeutic
direction. Existing disease claims and the Q9NZ08/3QNF identity chain are unchanged.

## Identity, forms and transformations

`CompoundIdentity` is keyed by a stable identifier, not a name or potency.
Aliases and `CompoundExternalIdentifier` mappings have separate namespaces and
resolved/unresolved/rejected states. Reusing a resolved identifier for another
identity raises a conflict. No fuzzy name matching, parent merging, salt stripping,
tautomer selection or unspecified-stereo assignment occurs.

`ChemicalForm` distinguishes parent, salt, solvate, mixture, stereoisomer,
racemate, prodrug, isotopologue and unspecified material. A parent reference does
not merge identities. Measurements can explicitly reference a tested form;
the reference package leaves that pointer unresolved because tested counterions,
solvation and batch-specific substance identity are not established.

RDKit 2025.9.3 is an isolated Python dependency used for validated SMILES,
canonical/isomeric SMILES, InChI/Key, formula, molecular weight, charge and 2D SVG.
It avoids adding a second chemistry runtime to the browser. Original SMILES,
software version, parameters, input/output and identity/depiction SHA-256 remain
available. Stereo features are inspected, not assigned. The frozen importer rejects
an incompatible toolkit version or an unjustified fully explicit stereo label.
Compound 1 retains an unspecified double bond; its stereo status is unknown.
Compounds 2/3 have no detected stereogenic features in their stored representations.
`resolved` refers to the source molecular representation/connectivity, not an
independently verified, fully specified tested substance.

## Assays and measurements

`Assay` separates biochemical activity, binding, target engagement, cellular
activity, cellular phenotype, disease-relevant phenotype, other and unknown.
Target gene, reported accession, taxon, material description, exact optional
protein/construct keys, substrate, detection, system and `MeasurementCondition`
records persist separately from measurements. Exact keys are validated against
the protein snapshot and construct ownership. A recombinant enzyme name does not
map its variants/tagged preparation to the displayed canonical protein or 3QNF.
Unreported fields stay null. Construct mapping is unknown throughout this package.

`BioactivityMeasurement` preserves endpoint, original string/value/unit/operator,
uncertainty, replicate count when justified, source/locator, and optional provider
pChEMBL with its own snapshot. Values are finite; concentration potencies must be
positive. Percentage noise/activation values are preserved, including negatives.
Supported numeric units are M/mM/uM/µM/μM/nM, percent and fold; unsupported numeric
units are rejected rather than interpreted. Qualitative/missing values remain null.

Operators `=`, `<`, `<=`, `>`, `>=`, `~` survive ingestion. AXIS converts only
concentration units to nM with an explicit factor/transformation, checking overflow.
Percentages and folds are not concentrations. IC50, EC50, AC50, Ki and Kd are not
interconverted. pChEMBL is provider normalization, not a replacement experiment.

Each experiment retains its identifier. Different assays are never deduplicated
by compound/target/endpoint; conflicting values are never averaged. The measurement
detail reports bounded potential disagreements for the same compound/assay/endpoint,
not a judgement that either experiment is wrong. No median/best/global potency.

## Conservative selectivity v1

`SelectivityAssessment` retains both input IDs, targets, status, rationale and
computation. The repository rechecks the assessment against its persisted inputs.
Missing comparison data → Not assessed. Incompatible or incompletely specified
inputs → Not directly comparable. No opaque score or inferred therapeutic advantage.

A ratio requires the same chemical identity and explicitly matched tested form,
same IC50/Ki/Kd endpoint, compatible concentrations, exact resolved constructs,
same taxon, biochemical/binding category, format, source series, substrate,
detection and system. Conditions must include matching known buffer, pH,
temperature, substrate/enzyme concentration and incubation time. This intentionally
conservative first version does not certify comparability from a shared gene name.
Activation/phenotype endpoints are not inhibitory selectivity inputs.

The quotient is comparison/primary. Exact/exact gives a point ratio. Opposite
censoring directions give a lower or upper bound with strict/inclusive flags;
same-direction censoring or approximation does not give an identifiable ratio.
Synthetic tests demonstrate 10 nM versus 1000 nM (=100×) and versus >10000 nM
(>1000×). Those values are NOT inserted into the curated vertical.

The reference package produces 18 contextual assessments: four Not assessed and
14 Not directly comparable, with no numerical ratios. ERAP2 uses a different
substrate/concentration, IRAP is mouse LNPEP, and exact assay constructs/forms and
some conditions are unresolved. The paper's reported selectivity language is not
silently promoted to an AXIS-calculated ratio. Not assessed means no usable
comparison imported here, not necessarily no published counter-screen.

## Frozen reference and source decisions

Three molecules, seven assays, fifteen measurements. Primary anchor:
[Maben et al., DOI 10.1021/acs.jmedchem.9b00293](https://pubs.acs.org/doi/10.1021/acs.jmedchem.9b00293).
Structures were checked against synthesis schemes and chemistry descriptions;
tables, methods and locators were checked in the author-hosted PDF.

ChEMBL release 37 was evaluated as a structured cross-reference, not as the
original experiment. The selected extract preserves its uncorrected records:

- Compound 2: CHEMBL4456470 represents a guanidine, while Scheme 2 and synthesis
  support a urea. That cross-reference is rejected; a manually transcribed source
  structure is formula-checked. No ChEMBL potency/pChEMBL is transferred to it.
- ChEMBL IRAP records point to an IL-1 receptor antagonist target. The paper
  identifies mouse Q8C129; the erroneous mapping is not imported.
- Some off-target operators disagree with the primary tables. Source >200 µM
  limits are preserved, never converted to exact or provider <= values.
- Compound 1's numeric off-target bounds are omitted pending reconciliation.
- Compounds 2/3 cellular measurements are antigen-presentation phenotypes in
  engineered HeLa/model MHC-I assays, not direct engagement, HLA-B27 or axSpA efficacy.

`axis/resources/pharmacology/erap1/v1` contains checksummed identities, identifiers,
forms, assays, measurements, provider extract and curation audit. Manifest/SHA pins
the package. ChEMBL selected data are attributed separately under CC BY-SA 3.0;
see [provider terms](https://chembl.gitbook.io/chembl-interface-documentation/about).
The copyrighted ACS PDF/images are not redistributed; URL/raw SHA and manual
factual extracts/locators are retained. Provider timestamps are curation-session
timestamps with explicitly documented per-request precision limitations.

No PubChem enrichment, source-backed chemical series or SAR inference was needed.
DG013A claims remain immutable; it is not imported or called selective. No ligand
bridge is asserted; waters, zinc and glycans remain structural observations.

## Import and read-only workspace

After explicitly importing the curated project and protein package:

```sh
axis --database axis.duckdb pharmacology import-package \
  --project AXIS-DD-ERAP1-CURATED-001 --protein '<imported protein ID>'
axis --database axis.duckdb serve
```

The additive migration is `007_chemical_pharmacology.sql`; migrations 001–006 are
unaltered. Import is atomic, immutable and replayable. Project/protein membership
and explicit measurement links isolate collections and drill-downs.

Read routes follow `/api/projects/{project}/targets/{protein}` with `/compounds`,
`/assays`, `/measurements`, `/selectivity`, `/{id}` and `/{id}/provenance` suffixes.
Collections use limit 1–100 and offset 0–100000. Compound/endpoint/target/category/
source filters are supported for applicable collections; unsupported combinations
are rejected. GET never starts retrieval. The dedicated ChEMBL adapter's retrieval
is explicit and separate from frozen/manual parsing.

Target → Chemistry → compound identity/forms/provenance; Pharmacology → each
measurement → exact reported material/context/source; Selectivity → independent
panel inputs and traceable assessment. Textual SMILES and values accompany graphics.
Compound details include a bounded identity graph with tested-in/produced/
has-measurement/reported-target/compares edges, never treats-axSpA.
UI windows are bounded; larger collections use API/UI pagination, not corpus loading.

Independent chemical/expert review and experimental validation remain necessary.
Next recommendation only: cellular pharmacology and disease-relevant engagement.
No Phase 3.4, docking, molecular generation, QSAR or ranking is implemented.
