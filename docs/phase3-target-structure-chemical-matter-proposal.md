# Phase 3 design preparation — Target Structure & Chemical Matter

**Conditional architecture draft, not an implementation approval.** Phase 2 visual
acceptance is still blocked. Final endorsement and any implementation must wait
for those gates and separate approval. This document proposes future contracts;
no adapter, chemistry schema, compound ingestion or structure analysis is added.
It does not answer which chemical interventions work for ERAP1.

## Product question and boundary

Future AXIS should let a scientist trace experimentally supported target
perturbation through protein identity, construct, structure/site evidence,
chemical identity, assay measurement and selectivity, then separately inspect
any link to cellular or disease-relevant biology. The presence of a structure,
bound ligand or biochemical potency must not imply a therapeutic mechanism.

Retain EvidenceStore/DuckDB repositories, immutable records, explicit source
provenance, read-first projections, typed assessments and independent questions.
New typed records would complement Claim, not replace it. Any future persistence
change needs additive migrations after 004, reviewed separately. A Claim can
express a sourced relationship; it should not absorb a whole compound/assay record.

## 1. Identity contracts

| Future object | Proposed identity boundary | Required distinction |
| --- | --- | --- |
| Gene | Namespace-aware gene accession, organism/taxon | A symbol is a label, not an unqualified universal identity |
| Protein | UniProt primary accession plus taxon and versioned sequence reference | Gene→protein mapping is sourced; not synonymous identity |
| Isoform | Explicit isoform accession, parent protein, exact sequence checksum/version | Canonical sequence is not silently substituted |
| ProteinConstruct | Immutable AXIS ID with exact sequence, residue range/mapping, substitutions, tags and provenance | An assay/structure construct may differ from the biological isoform |
| Structure | Provider-qualified record ID and record revision/snapshot | Coordinate model is separate from protein and construct |
| ChainInstance | Structure/model identifier plus mmCIF label asym ID, retaining author asym ID | Instance differs from polymer entity and sequence |
| BindingSite | Structure/chain/residue mapping or protein-reference mapping, evidence and revision | Sites across structures require reviewed mapping; no spatial proximity shortcut |
| LigandInstance | Structure/model, non-polymer instance, component ID, residue/alt-location identifiers | A coordinate instance is not a normalized compound identity |
| Compound | Provider accession plus exact chemical representation/version | Preserve stereochemistry, salts, mixtures and parent relationships |
| SubstanceRecord | Provider/depositor record and sample metadata | Substance/sample identity remains separate from normalized compound |

UniProt documents stable primary accessions, supporting a source-qualified protein
identity. Isoform/sequence and construct references should be retained as additional
versioned objects rather than equated by gene name. [UniProt accession documentation](https://www.uniprot.org/help/accession_numbers).

mmCIF distinguishes molecular instances and entities; author chain identifiers
must be preserved alongside the label identifiers. Keep both rather than merging
chains under a bare letter. [wwPDB mmCIF user guide](https://mmcif.k8s.wwpdb.org/docs/user-guide/guide.html).

PubChem distinguishes deposited substance information from normalized compound
structures. Store SID/depositor identity and CID compound identity separately;
do not use synonym matching as an automatic chemical equivalence assertion.
[PubChem data organization](https://pubchem.ncbi.nlm.nih.gov/docs/).

Every cross-reference should record source, mapping method, exact identifiers,
sequence/structure version where relevant and an unresolved/verified status.
Do not overload the existing DRUG EntityRef to represent all nine identity levels.
Future enum additions, if needed, must preserve every existing serialized value.

## 2. Structure provenance

Proposed `StructureRecord`: provider ID, revision, primary reference, retrieval
timestamp, raw-file SHA-256, importer/version, coordinate format, model count,
construct and chain references, reported method, experimental/predicted/unknown
origin and original validation metadata. Experimental structures retain the
reported experimental method and method-specific quality information. Unknown
method values stay unknown. Predicted models retain model provider, method/version,
template/sequence inputs when available and original confidence/uncertainty data;
never relabel them as experiments or convert confidence into binding evidence.

Residue mappings must handle missing segments, insertions, alternate conformations,
mutations, isoform numbering and constructs. Preserve original author numbering
and explicit mapping to reference sequence. A chain mapped to ERAP1 does not
automatically establish that every construct is equivalent to full-length ERAP1.

## 3. Binding sites and ligand evidence

Proposed `BindingSiteAssessment`: site ID, relevant construct/chain/residue set,
source-backed evidence claim(s), classification, reasoning and provenance.
Classification vocabulary: catalytic, orthosteric, allosteric, regulatory,
protein_interface, unknown. These are assessed attributes, not a mutually
exclusive geometric inference. Preserve author terminology separately; a site
may have multiple independently supported labels.

Use distinct relation types for observed ligand coordinates, experimentally
supported binding, biochemical inhibition, site-directed perturbation and a
proposed binding mode. Co-crystallization alone must not be presented as proof
of inhibitory function; unobserved sites must not be assigned from shape alone.
No docking, pocket prediction or molecular dynamics belongs in the first slice.

## 4. Bioactivity measurements

Proposed immutable `BioactivityMeasurement` references compound/substance,
assay, precise target/construct, source activity ID and source document. Preserve:

- Original endpoint type (IC50, Ki, Kd, EC50 or other), relation/operator, numeric
  value as a decimal/string, unit, original reported text and uncertainty/replicates;
- target identity/construct/organism, assay system and reported conditions:
  substrate, concentration, time, pH, temperature and other available fields;
- original provider fields, validity flags, censored limits and missing data;
- source document, database record/release, retrieval/import version and raw checksum.

Standardized values may be an additional deterministic transformation with unit
conversion provenance; they must never overwrite originals. Keep `>`, `<`, `>=`,
`<=`, approximate and unknown relations. Preserve missing values instead of treating
them as zero. IC50/Ki/Kd/EC50 are different measurement types, not interchangeable
potency values. No automatic conversion between types or median across incompatible
assays. A p-scale, if later displayed, remains a derived view with its formula and
eligibility rules, not an authoritative replacement.

ChEMBL's schema exposes separate assay, activity, target, compound and document
relationships and measurement relation/value/unit fields. Use those original
relationships rather than reducing an activity to compound+number.
[ChEMBL schema documentation](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/schema-questions-and-sql-examples).

## 5. Selectivity without an arbitrary score

Show ERAP1, ERAP2 and LNPEP/IRAP measurements side-by-side, retaining exact target
identifiers, construct/system, endpoint/operator/value/unit, assay conditions and
source. A missing off-target measurement means not assessed, not selective.
Alias mappings such as LNPEP/IRAP require a sourced identity mapping rather than
textual name merging.

Only a separately requested, transparent ratio calculation could compare matched
measurements of the same endpoint type and compatible assay context. State the
matching rule, numerator/denominator, original values and censoring; incompatible
contexts produce “not comparable”. Censored values yield bounds, not a fabricated
exact ratio. No cross-assay or clinical selectivity ranking should be generated.

## 6. Separate evidence layers and disease translation

Assay context explicitly distinguishes purified-enzyme/biochemical, target binding,
cellular target engagement, cellular phenotype and disease-relevant phenotype.
Link measurements to source assertions at the appropriate layer. A biochemical
measurement does not automatically become cellular activity, target engagement,
disease benefit or strategy support. Cross-layer links require their own Claim,
context and EvidenceAssessment/MechanisticAssessment with reasoning.

The current ERAP1 source corpus remains unchanged. Future compound-to-disease
links should point to reviewed relevant claims and perturbations; absent linkage
should remain “No direct evidence identified in this curated corpus”.

## 7. End-to-end provenance and import architecture

Proposed traversal:

`Compound/Substance → source Activity record → Assay → exact Target/Construct →
source Document → database Release/Snapshot → retrieval URI/time/hash → importer
version → preserved original measurement → optional normalized projection →
Claim/assessment → disease-context question`.

Adapter responsibilities: retrieve an explicitly selected bounded dataset, cache
raw records, verify identifiers, capture source release/snapshot and return typed
import records. Repository/services perform transactional validation and immutable
insertion. Presentation renders bounded DTOs and drawer ancestry. No browser SQL,
automatic enrichment on startup or hidden source refresh.

Future adapters may cover UniProt identity, PDB/mmCIF structures, ChEMBL assays/
activities and PubChem chemical identity. SourceKind presently has no dedicated
values for those databases; any future additions require a reviewed additive
contract change, not disguising the database as GEO or an AI source. Adapter
provenance is distinct from the primary publication and any AXIS interpretation.

## 8. Smallest independently testable first implementation slice

After Phase 2 acceptance and separate approval: **one pinned UniProt protein
identity snapshot linked to the existing ERAP1 gene**, imported explicitly and
displayed read-only with accession, organism, sequence/version/checksum, source
provenance and verified/unknown mapping status. No structures or compounds yet.

Acceptance: offline reproducibility; exact source/sequence preservation; gene
versus protein/isoform distinction; immutable conflicts; missing/ambiguous mappings
remain unresolved; project isolation; source drawer; installed-wheel resources;
all existing tests/types/lint and manual visual review. This establishes the
identity foundation before importing a single experimental structure/chain/
construct snapshot as a separately reviewed second slice. No chemistry adapter,
ranking or therapeutic conclusion is implied by either slice.
