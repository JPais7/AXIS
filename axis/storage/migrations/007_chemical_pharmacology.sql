CREATE TABLE compound_identities (
 id VARCHAR PRIMARY KEY,
 source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
 payload JSON NOT NULL
);
CREATE TABLE compound_external_identifiers (
 id VARCHAR PRIMARY KEY,
 compound_id VARCHAR NOT NULL REFERENCES compound_identities(id),
 namespace VARCHAR NOT NULL,
 external_id VARCHAR NOT NULL,
 mapping_status VARCHAR NOT NULL,
 source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
 payload JSON NOT NULL
);
CREATE UNIQUE INDEX resolved_chemical_identifier ON compound_external_identifiers
 (namespace, external_id, mapping_status, compound_id);
CREATE TABLE chemical_forms (
 id VARCHAR PRIMARY KEY,
 compound_id VARCHAR NOT NULL REFERENCES compound_identities(id),
 source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
 payload JSON NOT NULL
);
CREATE TABLE assays (
 id VARCHAR PRIMARY KEY,
 target_gene VARCHAR NOT NULL,
 protein_identity_id VARCHAR REFERENCES protein_identities(id),
 protein_construct_id VARCHAR REFERENCES protein_constructs(id),
 source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
 payload JSON NOT NULL
);
CREATE TABLE bioactivity_measurements (
 id VARCHAR PRIMARY KEY,
 compound_id VARCHAR NOT NULL REFERENCES compound_identities(id),
 assay_id VARCHAR NOT NULL REFERENCES assays(id),
 endpoint VARCHAR NOT NULL,
 source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
 payload JSON NOT NULL
);
CREATE TABLE selectivity_assessments (
 id VARCHAR PRIMARY KEY,
 compound_id VARCHAR NOT NULL REFERENCES compound_identities(id),
 primary_measurement_id VARCHAR REFERENCES bioactivity_measurements(id),
 comparison_measurement_id VARCHAR REFERENCES bioactivity_measurements(id),
 payload JSON NOT NULL
);
CREATE TABLE project_pharmacology (
 project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
 protein_identity_id VARCHAR NOT NULL REFERENCES protein_identities(id),
 compound_id VARCHAR NOT NULL REFERENCES compound_identities(id),
 PRIMARY KEY(project_id, protein_identity_id, compound_id)
);
CREATE TABLE project_pharmacology_measurements (
 project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
 protein_identity_id VARCHAR NOT NULL REFERENCES protein_identities(id),
 measurement_id VARCHAR NOT NULL REFERENCES bioactivity_measurements(id),
 PRIMARY KEY(project_id, protein_identity_id, measurement_id)
);
