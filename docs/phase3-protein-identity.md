# Phase 3.1 — reproducible protein identity

Identity is infrastructure, not disease evidence. A gene, protein, isoform and
provider snapshot are separate immutable objects. No provider metadata is turned
into Claims. Existing disease-evidence traversal remains unchanged.

## Model and persistence

`axis/domain/protein.py` defines frozen ProteinIdentity, ProteinIsoform,
GeneProteinMapping, SourceSnapshot and MappingStatus objects. Protein keys include
namespace, accession and immutable snapshot identity, never display names.
An isoform is a separate record; sequence, length, checksum and version may be
unknown together. The displayed entry sequence has its own provider version;
that version is not invented as an isoform-specific sequence version.

Additive migration `005_target_identity.sql` leaves 001–004 unchanged. EvidenceStore
owns the connection and TargetRepository. Identity keys, source ancestry, gene
references and explicit project memberships are relational with foreign keys;
complete validated immutable records are stored as JSON payloads. No update/delete
API is provided. Storage and service imports use the existing transaction boundary.

The old discovery gene entities do not carry a taxon. Ingestion requires an explicit
expected taxon and checks the provider primary gene field against the project gene
identifier, not its display label. HGNC/HGNC-symbol mappings require human taxon
9606. This initial resolver supports primary gene symbols, not arbitrary identifier
crosswalks, historical symbols or ambiguous multi-gene assignments. Mapping verified
means this source-backed identity relation only, not independent therapeutic review.

## Adapter and sequence integrity

`axis/sources/uniprot.py` validates primary accessions before requesting UniProt JSON.
Network access is explicit, time bounded and never part of GET/page rendering.
HTTP/network errors propagate before persistence. Parsing validates accession,
taxon, required identity fields and provider sequence length. Optional names,
versions and release are unknown if absent. SourceSnapshot records the raw-byte
SHA-256, retrieval, canonical request URL, importer version and release if captured.

Normalize sequences by uppercasing and removing whitespace. Accepted letters are
the twenty standard amino acids plus B, X, Z, J, U and O. Reject empty sequences,
FASTA headers, numbers, gaps, stop characters and punctuation. SHA-256 covers the
normalized ASCII sequence. Stored sequence objects must already be normalized and
match both length and digest. No alignment or variant inference is performed.

## Conflict and history policy

Exact frozen replay is idempotent. Reusing an internal ID for different payload
raises RecordConflictError. A changed sequence checksum, entry sequence version or
taxon under the same namespace/accession is **rejected**, leaving the old identity
and all tables untouched. This slice deliberately has no sequence-update approval
workflow. A refresh with unchanged biological identity may create a new immutable
retrieval snapshot and identity record; both remain accessible by accession and
explicit project membership. The old record is never replaced. No implicit latest
record selection is made.

All writes in one ingestion are transactional; provider parsing/checksum/taxon
failures occur before writes. Raw live responses are checksummed, but not archived
to a file automatically; the pinned frozen package is the reproducible reference.

## Frozen ERAP1 package

`axis/resources/targets/erap1/uniprot/v1` includes original JSON, manifest, manifest
SHA-256 and README. Manifest bytes pin raw response bytes. Package resources are
included in wheels and read through importlib.resources, not checkout-relative paths.
The download verified Q9NZ08, ERAP1, Homo sapiens/9606, 941 aa, entry sequence v3
and record v218. Canonical displayed isoform Q9NZ08-1 is imported; Q9NZ08-2 is
annotated with no imported sequence. Provider release and isoform-specific sequence
versions are unknown. Retrieval uses download completion file timestamp, seconds.

```sh
axis --database identity.duckdb discovery import-erap1
axis --database identity.duckdb target import-package --project AXIS-DD-ERAP1-CURATED-001
axis --database identity.duckdb target show Q9NZ08
axis --database identity.duckdb target verify Q9NZ08
axis --database identity.duckdb serve
```

The server requires schema 5 to have been initialized explicitly before read-only
serving. Stop any server owning a database before attempting CLI migration/import.
Use `--directory` to import an explicitly selected frozen directory.
`target verify` checks persisted sequence integrity; it does not establish authenticity
or refetch the provider. Frozen imports independently verify manifest and raw bytes.

Live ingestion is a separate operation:

```sh
axis --database identity.duckdb target import-uniprot Q9NZ08 --project AXIS-DD-ERAP1-CURATED-001 --taxon 9606
```

## Read API and workspace

All routes enforce explicit project membership:

- `GET /api/projects/{project}/targets` (bounded page).
- `GET /api/projects/{project}/targets/{identity_id}`.
- Suffixes `/protein`, `/isoforms`, `/provenance` on the identity detail route.

Identity IDs must be URL-encoded. These are persisted read projections only.
Target / Protein is part of the existing workspace: separate Gene, Protein,
Isoform and Source regions; residue-numbered monospaced sequence; copy control
and status; length, versions and SHA-256; provenance drawer using existing modal
focus/Escape behavior; return to disease evidence. Empty indexed structure/chemical
sections explicitly do not imply absence from science.

## Extension boundary

Future relation: ProteinIdentity → explicit ProteinConstruct → Structure →
ChainInstance → ResidueMapping → BindingSite. Constructs should reference an isoform
and carry ranges, substitutions, indels, tags, actual construct sequence/checksum
and independent provenance. Do not equate PDB chains with the canonical sequence.
Variants, rsIDs, substitutions and allotypes require separate evidenced mappings.
No construct/variant database or PDB/chemistry integration is implemented here;
these additive concepts do not require changing the immutable identity records.

Phase 2 release candidate remains unaccepted and scientific expert review pending.
Phase 3.1 implementation was explicitly authorized despite that administrative gate.
