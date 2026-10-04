CREATE TABLE source_snapshots (
    id VARCHAR PRIMARY KEY,
    provider VARCHAR NOT NULL,
    provider_record_id VARCHAR NOT NULL,
    raw_content_checksum VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE protein_identities (
    id VARCHAR PRIMARY KEY,
    namespace VARCHAR NOT NULL,
    accession VARCHAR NOT NULL,
    source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
    payload JSON NOT NULL,
    UNIQUE(namespace, accession, source_snapshot_id)
);
CREATE TABLE protein_isoforms (
    id VARCHAR PRIMARY KEY,
    protein_identity_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
    accession VARCHAR NOT NULL,
    payload JSON NOT NULL,
    UNIQUE(protein_identity_id, accession)
);
CREATE TABLE gene_protein_mappings (
    id VARCHAR PRIMARY KEY,
    gene_kind VARCHAR NOT NULL CHECK(gene_kind = 'gene'),
    gene_namespace VARCHAR NOT NULL,
    gene_entity_id VARCHAR NOT NULL,
    protein_identity_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
    payload JSON NOT NULL,
    FOREIGN KEY(gene_kind, gene_namespace, gene_entity_id)
        REFERENCES entities(kind, namespace, identifier)
);
CREATE TABLE project_protein_identities (
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    protein_identity_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    mapping_id VARCHAR NOT NULL REFERENCES gene_protein_mappings(id),
    PRIMARY KEY(project_id, protein_identity_id)
);
