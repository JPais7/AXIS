# Phase 3.2 — Experimental structure identity

## Scientific boundary

A PDB entry is an experimentally observed molecular object, not a synonym for
a gene, canonical protein, disease conformation or therapeutic target validation.
AXIS explicitly preserves:

ProteinIdentity → ProteinConstruct → ExperimentalStructure → ChainInstance
→ ResidueMapping → pinned ProteinIdentity, with SourceSnapshot provenance.

The structure projection also exposes an identity_graph containing these nodes
and represented_by, observed_in, contains, maps_to and sourced_from edges.
These are structural identity relations, not disease/mechanism/effect claims;
the existing disease-evidence graph and its 14 curated claims are unchanged.

ExperimentalStructure has structure_origin (experimental or predicted).
The Phase 3.2 importer creates only experimental records and rejects theoretical
model records. There is no AlphaFold import or pocket prediction.

## Provider and parser

Primary bytes come from the official wwPDB/RCSB ecosystem, in mmCIF format.
Gemmi **0.7.5** parses mmCIF categories, quoted text and loops. It replaces
fragile regular-expression parsing and is pinned in Python dependencies/lockfile.
Provider acquisition, parsing, mapping, storage and API projections are separate.

The adapter accepts explicit uppercase legacy four-character PDB identifiers.
Live acquisition is a separate CLI operation; GET routes never fetch from PDB.
The parser preserves entry identity, method, resolution/unknown, dates, revision,
experimental conditions, source organism, expression host, chain/entity sequences,
cross-references, sequence differences, polymer scheme and atom numbering.

Supported slice: one coordinate model, L-polypeptide chains, explicit source taxon
and UniProt cross-reference, authoritative equal-span sequence mapping segments.
All protein chains must correspond to the selected pinned protein. Mixed-protein
complexes, ensembles, missing anchors and unresolved cross-reference ambiguity
fail safely; they are not silently reduced to one convenient chain.
Atom residue names must agree with the polymer scheme, and atom author numbering
must be consistent within a structural sequence position.

## Constructs and numbering

ProteinConstruct records the deposited sequence, checksum, mapped canonical range,
expression system, source-supported tags/substitution classification and unknown
fusion details. The canonical-isoform link is explicitly an AXIS inference from
the Phase 3.1 canonical sequence checksum, not a PDB isoform assertion.

Keep four numbering systems distinct:

| Position | Meaning | 3QNF chain A example |
|---|---|---|
| canonical_position | Pinned Q9NZ08 sequence, one-based | 46 (P) |
| construct_position | Deposited entity sequence, one-based | 52 |
| structural_sequence_position | mmCIF label_seq_id | 52 |
| author_residue_number + insertion_code | Provider author coordinate identifier | 46, no insertion |

Chain label_asym_id and auth_asym_id are retained separately even when equal.
NGL matching uses both identifiers plus author number and insertion code; author
residue number is never used as canonical mapping by equality.

## Deterministic mapping

provider-segment-projection v1 uses _struct_ref_seq anchors, _struct_ref identity,
_pdbx_poly_seq_scheme and _atom_site. Provider anchors are checked against the
imported entity and pinned protein sequences. Segment spans must match, positions
must lie in bounds, segments must not overlap, and anchored identity must be at
least 95%. Wrong taxon, accession or sequence fails before persistence.

No alignment is computed. Unequal-span/ambiguous mappings need a later explicitly
versioned mapping strategy; this implementation does not guess through them.
Separate supported segments can describe gaps. Internal unrepresented canonical
positions are classified deletion; terminal positions not covered by the deposited
construct are not_in_construct. These are correspondence classifications, not
unsupported claims about experimental processing.

Classifications include exact_match, unresolved_coordinate, mapping_mismatch,
source_reported_substitution, engineered_substitution, insertion, deletion and
not_in_construct. Ambiguous and unmapped are reserved states; ambiguous imports
currently fail rather than producing accepted correspondences.

Identity and coordinate presence are separate. An exact deposited sequence
position without occupied atoms is unresolved_coordinate, not absent from the
construct. Substituted positions preserve substitution classification even if
coordinates are missing. Atom occupancy must be positive to count as represented.

Each chain stores algorithm/version, software/importer/parser, provider categories,
threshold/segments, pinned protein identity, input sequence hashes, output mapping
hash and coverage. Coverage is descriptive, not an opaque structure-quality score.

## Observed components

ObservedStructureComponent preserves component code, label/auth context, author
number/insertion, provider name/type, observed atom count and source snapshot.
Water and source-described single-atom ions are labelled conservatively;
other components remain other_component. Not every HETATM is called a ligand.
Raw coordinates remain available to inspect these observations.

No component is automatically promoted to a Compound, inhibitor, selective binder
or drug. No catalytic mechanism is inferred from proximity. Binding-site/pocket
prediction and functional site classification are not implemented.

## Persistence and offline replay

Migration 006_structure_identity.sql adds protein_constructs,
experimental_structures (including raw coordinate BLOB), structure_chains,
residue_mappings, observed_structure_components and project_structures.
Migrations 001–005 are unchanged. StructureRepository owns structural SQL and
immutable conflict checks. The whole source/construct/chain/mapping/component/link
import is transactional.

Frozen package: axis/resources/structures/erap1/3qnf/v1/.
It contains unmodified structure.cif, manifest.json, manifest.sha256 and README.
Checksums and importer/mapping versions are verified before replay.
Raw checksum or protein checksum mismatch fails; no automatic source refresh.
Live retrieval creates a timestamped snapshot rather than overwriting a frozen
record. Stop the server before CLI writes to its database.

Example (the protein id printed by target import-package is passed explicitly):

```sh
axis --database structure.duckdb discovery import-erap1
axis --database structure.duckdb target import-package --project AXIS-DD-ERAP1-CURATED-001
axis --database structure.duckdb structure import-package --project AXIS-DD-ERAP1-CURATED-001 --protein 'PROTEIN_ID_PRINTED_ABOVE'
axis --database structure.duckdb serve --port 8768
```

For the bundled Phase 3.1 snapshot the full protein ID is:

```text
protein:uniprot:Q9NZ08:159efd863655a143aaaa821e7efab2334a1d7fd606d49586ea86bec2f9e14b65:2026-10-03T17:28:00+00:00
```

Explicit network operation, not needed for frozen reproduction:

```sh
axis --database structure.duckdb structure import-pdb 3QNF --project AXIS-DD-ERAP1-CURATED-001 --protein 'PROTEIN_ID'
```

## Read-only API

URL-encode both snapshot identifiers. Base:
`/api/projects/{project}/targets/{protein}/structures`.
GET base returns the paginated list; /{structure} returns identity/constructs/
chains/coverage/components/snapshot/identity_graph. Further routes: /chains,
/mapping, /provenance, /coordinates. Coordinates are JSON containing mmCIF text,
format and raw SHA-256. Every route verifies project and target membership.
Wrong-project/target/unknown identifiers fail; no source requests occur on reads.

## Workspace and 3D viewer

Target / Protein → View imported experimental structures → 3QNF.
The list supports multiple imported structures. Detail includes construct and
chain disclosures, chain selector, descriptive coverage, numbered residue buttons,
canonical-position lookup, all numbering systems, source/mapping drawer and a
return link to project disease evidence.

NGL **2.5.0** was selected for mature mmCIF, cartoon rendering, chain colouring,
atom picking, offline Blob loading and straightforward small-app integration.
Mol* was considered; its broader application/plugin model was not required for
this single-entry reference slice. No custom molecular renderer was built.

The NGL module is dynamically imported only after Load local 3D viewer; coordinate
text is then read from the local API, never downloaded from a remote PDB endpoint.
Cartoons distinguish chains; non-water components use ball-and-stick.
Sequence selection highlights matching occupied atoms; picking an atom updates
chain selector, mapping text and sequence group. Unmapped components show
Canonical mapping unavailable. Missing coordinates clear the highlight.
Left drag rotates, wheel zooms and NGL right drag pans; explicit Pan left/right
buttons provide keyboard-accessible translation. Reset restores initial rotation
and recentres/refits the molecular object. ResizeObserver and disposal prevent
viewer leakage on navigation.

All scientific facts are textual and remain available if WebGL initialization
fails. Browser-only graphics accessibility is limited; the canvas is not the sole
source of scientific information. Source provenance uses the existing modal
drawer with keyboard dismissal and focus restoration.

The lazy viewer chunk is about 1.30 MB / 362 KB gzip, versus 43.6 KB / 13.8 KB
gzip for the main application JS. Vite reports its >500 KB warning; this is
disclosed, not suppressed. Upstream NGL declarations reference unbundled third-party
types, so skipLibCheck is enabled; AXIS application TypeScript remains strict.
The browser observed an upstream THREE legacy-lighting deprecation warning,
not a rendering error. No security policy was relaxed.

## Limits and next phase

3QNF represents one experimental state, not the disease structure of ERAP1.
Coordinate absence does not establish protein abundance, gene inhibition,
deletion, cleavage or disease relevance. Coverage does not imply quality,
druggability, efficacy, selectivity or clinical validity.

Phase 3.3 should independently model CompoundIdentity → Assay →
BioactivityMeasurement → exact target/construct, retaining units, assay conditions,
source and uncertainty. Only explicit evidence should link these objects to
ObservedStructureComponent. Chemistry ingestion, docking, MD and ranking remain
outside Phase 3.2.

See the implementation report for executed checks and outstanding validation.
